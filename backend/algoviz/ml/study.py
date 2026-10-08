"""
Edge study
==========

Does the model have an edge, and under which label definition and training
window? (implementation-plan §11 W5 and §12 W1–W3; the protocol, fixed before
the deciding data existed, is `docs/edge-study-protocol.md`). The served
pipeline end to end:

- Samples come from the engine's own bookkeeping (`MLEngine.ingest_bar`): the
  same feature vectors, rolling medians and session splits as served. Feature
  vectors do not depend on the labels, so they are built once. Each label
  definition then relabels them with the served `barrier_bps` and
  `triple_barrier`, never across a session gap, as the engine does.
- Each configuration is evaluated as served. The engine refits every 600
  samples, so for each evaluation block of 600 samples the study fits the
  served recipe on the configuration's training window, which ends one horizon
  before the block (no training label reaches into it), and predicts the block.
  Development: 8 blocks evenly spaced in each quarter of the earlier 75 % of the
  samples. Holdout: every block of the rest. A block is scored against the
  class prior of its training window and against the trailing prior; a
  quarter pools its blocks.
- Configurations: every label definition with all features and the served
  training window, then, for the three best, two feature ablations and three
  training variants (1 h and 4 h windows, and recency weights with a 1 h
  half-life on the served window).
- Selection is kept honest. The configuration with the best development edge
  over the better prior is scored once on the untouched later part, and a rule
  fixed in advance decides.

**Rule (pre-registered).** Adopt a configuration only if it beats both priors
(its edge over the better of the class prior and the trailing prior is
positive) in at least 3 development quarters and on the holdout, and only with
at least 7 days of bars collected after the protocol was frozen (`FREEZE_MS`).
Bars from before the freeze shaped the protocol, so they only explore. The rule
first tested the trailing prior alone; at long horizons that was the weaker
baseline, so it was amended to both (E9, 2026-10-07), before the deciding data
existed.
"""

from __future__ import annotations

import math
import tempfile
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

import numpy as np

from algoviz.config import Settings
from algoviz.db import async_session
from algoviz.market.bars import SESSION_GAP_MS, Bar
from algoviz.ml.engine import MLEngine
from algoviz.ml.features import FEATURE_NAMES, SCALED_FEATURES
from algoviz.ml.labels import barrier_bps, triple_barrier
from algoviz.ml.train import block_log_losses, fit_model

HORIZONS_S = (5, 15, 30, 60, 120)
BARRIER_KS = (0.5, 1.0, 2.0)
FLOORS_BPS = (0.5, 1.0, 2.0, 4.0)
ALL_FEATURES = "all features"
ABLATIONS: dict[str, tuple[str, ...]] = {
    ALL_FEATURES: (),
    "without hour of day": ("hour_sin", "hour_cos"),
    "without scaled quantities": SCALED_FEATURES,
}
REFINE_TOP = 3  # the label definitions, best first, the ablations and variants run on
DEV_SHARE = 0.75  # the earlier part, explored; the rest is the holdout, scored once
BLOCK = 600  # samples per evaluation block: the served model refits this often
HGB_BINS = 255  # HistGradientBoostingClassifier's default max_bins
QUARTERS = 4
BLOCKS_PER_QUARTER = 8
MIN_QUARTERS_BEATING = 3
MIN_DAYS = 7.0  # E7: with fewer days of deciding bars the study reports but decides nothing
FREEZE_MS = 1_791_471_300_000  # 2026-10-08 14:55 UTC: the protocol was fixed; later bars decide


@dataclass(frozen=True, slots=True)
class LabelSpec:
    horizon_s: int  # bars are 1 s, so also the horizon in bars
    barrier_k: float
    floor_bps: float

    def __str__(self) -> str:
        return f"{self.horizon_s} s · k {self.barrier_k:g} · floor {self.floor_bps:g} bps"


@dataclass(frozen=True, slots=True)
class Variant:
    """How a training window is drawn: its length in samples, and recency weights."""

    name: str
    window: int | None = None  # None: the served `ML_MAX_SAMPLES`
    half_life_s: float | None = None  # sample weights halve with every half-life of age


SERVED = Variant("served window")
VARIANTS = (
    SERVED,
    Variant("1 h window", window=3_600),
    Variant("4 h window", window=14_400),
    Variant("served window, 1 h half-life", half_life_s=3_600.0),
)


def label_grid() -> list[LabelSpec]:
    return [LabelSpec(h, k, f) for h in HORIZONS_S for k in BARRIER_KS for f in FLOORS_BPS]


def split_at_freeze(bars: Sequence[Bar]) -> tuple[list[Bar], list[Bar]]:
    """The bars from before the protocol freeze (exploratory) and from it on (deciding)."""
    return [b for b in bars if b.ts_ms < FREEZE_MS], [b for b in bars if b.ts_ms >= FREEZE_MS]


@dataclass(slots=True)
class Samples:
    """Feature vectors of every bar with a full lookback, and what their labels are made of."""

    X: np.ndarray  # (samples, features)
    rows: np.ndarray  # each sample's bar index
    ts_ms: np.ndarray  # each sample's bar open time
    closes: list[float]  # every bar's close
    vol_bps: list[float | None]  # every bar's volatility (it scales the barrier)
    session_end: np.ndarray  # per bar: one past the last bar of its session
    n_bars: int
    sessions: int
    span_ms: tuple[int, int]  # the first and last bar's open time
    _labels: dict[LabelSpec, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    @property
    def days(self) -> float:
        """Days of bars (not the calendar span: gaps between sessions don't count)."""
        return self.n_bars / 86_400

    def labels(self, spec: LabelSpec) -> tuple[np.ndarray, np.ndarray]:
        """The samples `spec` can label and their classes; no horizon reaches across a gap."""
        if spec in self._labels:
            return self._labels[spec]
        keep = np.zeros(len(self.rows), dtype=bool)
        y = np.zeros(len(self.rows), dtype=int)
        h = spec.horizon_s
        for k, i in enumerate(self.rows.tolist()):
            if i + h >= self.session_end[i]:
                continue
            barrier = barrier_bps(self.vol_bps[i], spec.horizon_s, spec.barrier_k, spec.floor_bps)
            lab = triple_barrier(self.closes, i, h, barrier)
            if lab is not None:
                keep[k] = True
                y[k] = lab.cls
        self._labels[spec] = (keep, y[keep])
        return self._labels[spec]


def build_samples(bars: Sequence[Bar], cfg: Settings) -> Samples:
    """Run the bars through the engine's bookkeeping, as served, and keep its feature vectors."""
    with tempfile.TemporaryDirectory(prefix="algoviz-study-") as tmp:
        study_cfg = cfg.model_copy(
            update={
                "ML_MODEL_DIR": Path(tmp),
                "ML_HORIZON_S": min(HORIZONS_S),  # the shortest horizon labels the most bars
                "ML_MAX_SAMPLES": len(bars) + 1,
            }
        )
        ml = MLEngine(bars[0].symbol, study_cfg, async_session, persist=False)
        for bar in bars:
            ml.ingest_bar(bar, live=False)
        X, _, ts = ml.training_set()
    index = {b.ts_ms: i for i, b in enumerate(bars)}
    session_end = np.empty(len(bars), dtype=int)
    start, sessions = 0, 0
    for i in range(1, len(bars) + 1):
        if i == len(bars) or bars[i].ts_ms - bars[i - 1].ts_ms > SESSION_GAP_MS:
            session_end[start:i] = i
            start, sessions = i, sessions + 1
    return Samples(
        X=X,
        rows=np.array([index[int(t)] for t in ts], dtype=int),
        ts_ms=np.asarray(ts, dtype=np.int64),
        closes=[b.close for b in bars],
        vol_bps=[b.volatility_bps for b in bars],
        session_end=session_end,
        n_bars=len(bars),
        sessions=sessions,
        span_ms=(bars[0].ts_ms, bars[-1].ts_ms),
    )


# ── Evaluation as served ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Score:
    """Mean log-loss over scored samples: the model's, and each prior's."""

    n_test: int
    log_loss: float
    prior_log_loss: float  # the class prior of each block's training window
    trailing_prior_log_loss: float

    @property
    def edge(self) -> float:
        """Log-loss improvement over the better of the two priors."""
        return min(self.prior_log_loss, self.trailing_prior_log_loss) - self.log_loss

    @staticmethod
    def pool(parts: Sequence[Score]) -> Score:
        n = sum(p.n_test for p in parts)
        weights = np.array([p.n_test for p in parts]) / n
        lls = np.array([[p.log_loss, p.prior_log_loss, p.trailing_prior_log_loss] for p in parts])
        ll, prior, trailing = (float(v) for v in weights @ lls)
        return Score(n, ll, prior, trailing)


def training_rows(start: int, horizon: int, window: int) -> np.ndarray:
    """A block's training window: it ends one horizon before the block, so no label reaches in."""
    end = max(0, start - horizon)
    return np.arange(max(0, end - window), end)


def bin_codes(X_fit: np.ndarray, X_other: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Each feature replaced by its bin among `HGB_BINS` unweighted quantiles of
    `X_fit`, the edges an unweighted fit would use. With no more distinct values
    than bins, HGB bins weighted data at midpoints; otherwise it computes every
    edge as a weighted percentile, which made a weighted fit 5 to 17 times slower.
    Recency weights then shape the trees and the calibration, not the bin edges.
    """
    q = np.linspace(0, 100, HGB_BINS + 1)[1:-1]
    edges = np.percentile(X_fit, q, axis=0, method="averaged_inverted_cdf")
    codes = [
        np.column_stack([np.searchsorted(edges[:, j], X[:, j]) for j in range(X.shape[1])])
        for X in (X_fit, X_other)
    ]
    return codes[0].astype(np.float64), codes[1].astype(np.float64)


def recency_weights(ts_ms: np.ndarray, rows: np.ndarray, half_life_s: float) -> np.ndarray:
    """Weights that halve with every `half_life_s` of age, the newest training sample at 1."""
    age_s = (ts_ms[rows[-1]] - ts_ms[rows]) / 1000
    return np.power(0.5, age_s / half_life_s)


def score_block(
    X: np.ndarray,
    y: np.ndarray,
    ts_ms: np.ndarray,
    block: tuple[int, int],
    horizon: int,
    *,
    window: int,
    half_life_s: float | None,
    min_train: int,
    seed: int,
) -> Score | None:
    """Refit as served on the block's training window, then score the block (None: too little)."""
    tr = training_rows(block[0], horizon, window)
    if len(tr) < min_train or len(np.unique(y[tr])) < 2:
        return None
    X_tr, X_te, weights = X[tr], X[block[0] : block[1]], None
    if half_life_s is not None:
        weights = recency_weights(ts_ms, tr, half_life_s)
        X_tr, X_te = bin_codes(X_tr, X_te)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model, _ = fit_model(X_tr, y[tr], horizon, seed, sample_weight=weights)
    ll, prior, trailing = block_log_losses(model, X_te, y, tr, np.arange(*block), horizon)
    return Score(block[1] - block[0], ll, prior, trailing)


def development_blocks(
    n_dev: int, horizon: int, min_train: int, per_quarter: int = BLOCKS_PER_QUARTER
) -> list[list[tuple[int, int]]]:
    """
    Per quarter of the development samples that have a training window's worth of
    history, `per_quarter` evenly spaced blocks of up to `BLOCK` samples.
    """
    first = min_train + horizon
    if n_dev - first < QUARTERS * per_quarter:
        return []
    quarters = []
    for lo, hi in pairwise(np.linspace(first, n_dev, QUARTERS + 1).astype(int).tolist()):
        step = (hi - lo) // per_quarter
        size = min(BLOCK, step)
        quarters.append([(lo + k * step, lo + k * step + size) for k in range(per_quarter)])
    return quarters


def holdout_blocks(n_dev: int, n: int, horizon: int) -> list[tuple[int, int]]:
    """Every block of the later part, after an embargo of one horizon."""
    return [(s, min(s + BLOCK, n)) for s in range(n_dev + horizon, n, BLOCK)]


@dataclass(slots=True)
class ConfigResult:
    spec: LabelSpec
    ablation: str
    n: int  # labelled samples, development and holdout
    flat_share: float
    quarters: list[Score]  # development, each pooling its blocks
    variant: Variant = SERVED

    @property
    def name(self) -> str:
        return f"{self.spec} ({self.ablation}, {self.variant.name})"

    @property
    def edges(self) -> list[float]:
        """Log-loss improvement over the better of the two priors, per development quarter."""
        return [q.edge for q in self.quarters]

    @property
    def mean_edge(self) -> float:
        return float(np.mean(self.edges)) if self.edges else -math.inf

    @property
    def beating(self) -> int:
        return sum(e > 0 for e in self.edges)

    @property
    def mean_edge_vs_prior(self) -> float:
        return float(np.mean([q.prior_log_loss - q.log_loss for q in self.quarters]))

    @property
    def mean_edge_vs_trailing(self) -> float:
        return float(np.mean([q.trailing_prior_log_loss - q.log_loss for q in self.quarters]))


def _design(
    samples: Samples, spec: LabelSpec, ablation: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    keep, y = samples.labels(spec)
    drop = set(ABLATIONS[ablation])
    cols = [j for j, name in enumerate(FEATURE_NAMES) if name not in drop]
    return samples.X[keep][:, cols], y, samples.ts_ms[keep]


def evaluate(
    samples: Samples,
    spec: LabelSpec,
    ablation: str = ALL_FEATURES,
    variant: Variant = SERVED,
    *,
    cap: int,
    min_train: int,
    seed: int = 7,
    per_quarter: int = BLOCKS_PER_QUARTER,
) -> ConfigResult:
    """One configuration's development quarters (none if it labels too little)."""
    X, y, ts = _design(samples, spec, ablation)
    n_dev = int(len(y) * DEV_SHARE)
    flat = float((y == 1).mean()) if len(y) else 0.0
    quarters = []
    for blocks in development_blocks(n_dev, spec.horizon_s, min_train, per_quarter):
        scored = [
            score
            for block in blocks
            if (
                score := score_block(
                    X,
                    y,
                    ts,
                    block,
                    spec.horizon_s,
                    window=variant.window or cap,
                    half_life_s=variant.half_life_s,
                    min_train=min_train,
                    seed=seed,
                )
            )
            is not None
        ]
        if scored:
            quarters.append(Score.pool(scored))
    return ConfigResult(spec, ablation, len(y), flat, quarters, variant)


def holdout(
    samples: Samples, result: ConfigResult, *, cap: int, min_train: int, seed: int = 7
) -> Score | None:
    """Score a configuration once, on every block of the later part."""
    X, y, ts = _design(samples, result.spec, result.ablation)
    n_dev = int(len(y) * DEV_SHARE)
    scored = [
        score
        for block in holdout_blocks(n_dev, len(y), result.spec.horizon_s)
        if (
            score := score_block(
                X,
                y,
                ts,
                block,
                result.spec.horizon_s,
                window=result.variant.window or cap,
                half_life_s=result.variant.half_life_s,
                min_train=min_train,
                seed=seed,
            )
        )
        is not None
    ]
    return Score.pool(scored) if scored else None


VerdictKind = Literal["exploratory", "preliminary", "too_few", "no_holdout", "no_edge", "adopt"]


@dataclass(frozen=True, slots=True)
class Verdict:
    kind: VerdictKind
    reason: str

    @property
    def adopt(self) -> bool:
        return self.kind == "adopt"


def decide(best: ConfigResult, held: Score | None, days: float, *, deciding: bool) -> Verdict:
    """The pre-registered rule."""
    if not deciding:
        return Verdict(
            "exploratory",
            "exploratory: bars from before the protocol was frozen; nothing is decided",
        )
    if days < MIN_DAYS:
        return Verdict(
            "preliminary",
            f"preliminary: {days:.2f} days of bars, the rule needs {MIN_DAYS:g}; nothing is decided",
        )
    if held is None:
        return Verdict("no_holdout", "no holdout to score; nothing is decided")
    summary = (
        f"{best.name} beat both priors in {best.beating} of {len(best.quarters)} development "
        f"quarters, and the better prior by {held.edge:+.4f} nats on the holdout"
    )
    if best.beating >= MIN_QUARTERS_BEATING and held.edge > 0:
        return Verdict("adopt", f"adopt: {summary}")
    return Verdict("no_edge", f"no edge: {summary}")


@dataclass(slots=True)
class StudyReport:
    samples: Samples
    results: list[ConfigResult]
    best: ConfigResult | None
    holdout: Score | None
    verdict: Verdict
    deciding: bool
    protocol: str | None  # the protocol document's digest


def run_study(
    bars: Sequence[Bar],
    cfg: Settings,
    *,
    deciding: bool,
    specs: Sequence[LabelSpec] | None = None,
    protocol: str | None = None,
    seed: int = 7,
    per_quarter: int = BLOCKS_PER_QUARTER,
    progress: Callable[[ConfigResult], None] | None = None,
) -> StudyReport:
    """
    The study on `bars`. Only a run on bars from after the freeze (`deciding`) can
    adopt anything; `per_quarter` other than the protocol's is for tests.
    """
    samples = build_samples(bars, cfg)
    # Training windows as large as the served model's, no larger; no fit on fewer
    # samples than the engine would train on.
    limits = {"cap": cfg.ML_MAX_SAMPLES, "min_train": cfg.ML_MIN_DATA_POINTS, "seed": seed}
    results: list[ConfigResult] = []

    def run(spec: LabelSpec, ablation: str = ALL_FEATURES, variant: Variant = SERVED) -> None:
        result = evaluate(samples, spec, ablation, variant, per_quarter=per_quarter, **limits)
        results.append(result)
        if progress is not None:
            progress(result)

    for spec in specs or label_grid():
        run(spec)
    ranked = sorted((r for r in results if r.quarters), key=lambda r: r.mean_edge, reverse=True)
    for r in ranked[:REFINE_TOP]:
        for ablation in ABLATIONS:
            if ablation != ALL_FEATURES:
                run(r.spec, ablation)
        for variant in VARIANTS:
            if variant != SERVED:
                run(r.spec, variant=variant)
    scored = [r for r in results if r.quarters]
    if not scored:
        verdict = Verdict("too_few", "too few labelled samples for any configuration")
        return StudyReport(samples, results, None, None, verdict, deciding, protocol)
    best = max(scored, key=lambda r: r.mean_edge)
    held = holdout(samples, best, **limits)
    verdict = decide(best, held, samples.days, deciding=deciding)
    return StudyReport(samples, results, best, held, verdict, deciding, protocol)


def render(report: StudyReport) -> str:
    """The report as Markdown: the data, the verdict, the holdout and every configuration."""
    s = report.samples
    first, last = (
        datetime.fromtimestamp(t / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M") for t in s.span_ms
    )
    freeze = datetime.fromtimestamp(FREEZE_MS / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M")
    kind = "deciding (from the freeze on)" if report.deciding else "exploratory (before the freeze)"
    lines = [
        "# Edge study",
        "",
        f"- Data, {kind}: {s.n_bars:,} bars ({s.days:.2f} days of bars) in {s.sessions} "
        f"session{'s' if s.sessions != 1 else ''}, "
        f"{first} to {last} UTC; {len(s.rows):,} samples with a full lookback.",
        f"- Protocol: `docs/edge-study-protocol.md`"
        f"{f' (sha256 {report.protocol})' if report.protocol else ''}, frozen {freeze} UTC.",
        f"- Evaluation as served: a refit every {BLOCK} samples; {BLOCKS_PER_QUARTER} blocks in "
        f"each of {QUARTERS} development quarters (the earlier {DEV_SHARE:.0%}); every block of "
        "the holdout.",
        f"- Rule, fixed in advance: adopt only if the model beats both the class prior and the "
        f"trailing prior in at least {MIN_QUARTERS_BEATING} development quarters and on the "
        f"holdout, with at least {MIN_DAYS:g} days of bars from the freeze on.",
        f"- **Verdict: {report.verdict.reason}.**",
    ]
    if report.best is not None and report.holdout is not None:
        h = report.holdout
        lines.append(
            f"- Holdout ({report.best.name}): {h.n_test:,} samples, log-loss {h.log_loss:.4f} "
            f"vs class prior {h.prior_log_loss:.4f} and trailing prior "
            f"{h.trailing_prior_log_loss:.4f}."
        )
    lines += [
        "",
        "Development, best first. Edges are log-loss improvements in nats; the trailing prior "
        "is the class mix of the labels already resolved at each prediction. The rule's edge is "
        "over the better of the two priors, quarter by quarter.",
        "",
        "| Label | Features | Training | Samples | Flat | Edge vs prior | Edge vs trailing prior "
        "| Edge vs the better prior | Quarters beating both |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|",
    ]
    for r in sorted(report.results, key=lambda r: r.mean_edge, reverse=True):
        head = f"| {r.spec} | {r.ablation} | {r.variant.name} | {r.n:,} |"
        if not r.quarters:
            lines.append(f"{head} — | — | — | too few samples | — |")
            continue
        sd = float(np.std(r.edges))
        lines.append(
            f"{head} {r.flat_share:.0%} | {r.mean_edge_vs_prior:+.4f} | "
            f"{r.mean_edge_vs_trailing:+.4f} | {r.mean_edge:+.4f} ± {sd:.4f} | "
            f"{r.beating} of {len(r.quarters)} |"
        )
    return "\n".join(lines) + "\n"


def report_dict(report: StudyReport, *, generated_ms: int, top: int = 12) -> dict[str, Any]:
    """The report as JSON for the API (`EdgeStudyReport`): the verdict, the holdout, the best configurations."""
    s = report.samples

    def config(r: ConfigResult) -> dict[str, Any]:
        scored = bool(r.quarters)
        return {
            "label": str(r.spec),
            "horizon_s": r.spec.horizon_s,
            "barrier_k": r.spec.barrier_k,
            "floor_bps": r.spec.floor_bps,
            "features": r.ablation,
            "training": r.variant.name,
            "samples": r.n,
            "flat_share": round(r.flat_share, 4),
            "edge_vs_prior": round(r.mean_edge_vs_prior, 5) if scored else None,
            "edge_vs_trailing_prior": round(r.mean_edge_vs_trailing, 5) if scored else None,
            "edge": round(r.mean_edge, 5) if scored else None,
            "edge_sd": round(float(np.std(r.edges)), 5) if scored else None,
            "quarters_beating": r.beating,
            "quarters": len(r.quarters),
        }

    h = report.holdout
    ranked = sorted(
        (r for r in report.results if r.quarters), key=lambda r: r.mean_edge, reverse=True
    )
    return {
        "generated_ms": generated_ms,
        "protocol": report.protocol,
        "freeze_ms": FREEZE_MS,
        "deciding": report.deciding,
        "data": {
            "bars": s.n_bars,
            "days": round(s.days, 4),
            "sessions": s.sessions,
            "first_ms": s.span_ms[0],
            "last_ms": s.span_ms[1],
            "samples": len(s.rows),
        },
        "rule": {
            "min_quarters_beating": MIN_QUARTERS_BEATING,
            "quarters": QUARTERS,
            "min_days": MIN_DAYS,
            "block": BLOCK,
            "blocks_per_quarter": BLOCKS_PER_QUARTER,
        },
        "verdict": {"kind": report.verdict.kind, "reason": report.verdict.reason},
        "best": None if report.best is None else config(report.best),
        "holdout": None
        if h is None
        else {
            "samples": h.n_test,
            "log_loss": round(h.log_loss, 5),
            "prior_log_loss": round(h.prior_log_loss, 5),
            "trailing_prior_log_loss": round(h.trailing_prior_log_loss, 5),
            "edge": round(h.edge, 5),
        },
        "configurations": len(report.results),
        "top": [config(r) for r in ranked[:top]],
    }
