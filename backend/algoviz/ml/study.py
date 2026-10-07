"""
Edge study
==========

Does the model have an edge, and under which label definition?
(implementation-plan §11, W5). The served pipeline end to end, over a grid of
label definitions and two feature ablations:

- Samples come from the engine's own bookkeeping (`MLEngine.ingest_bar`): the
  same feature vectors, rolling medians and session splits as served. Feature
  vectors do not depend on the labels, so they are built once. Each label
  definition then relabels them with the served `barrier_bps` and
  `triple_barrier`, never across a session gap, as the engine does.
- Each configuration is scored on the earlier part of the data with the served
  recipe's walk-forward (`walk_forward`, training windows capped at the served
  sample limit), against the class prior, the trailing prior and the logistic
  baseline.
- Selection is kept honest. The configuration with the best development edge
  over the better prior is scored once on the untouched later part
  (`score_split`), and a rule fixed in advance decides.

**Rule (pre-registered).** Adopt a configuration only if it beats both priors
(its edge over the better of the class prior and the trailing prior is
positive) in at least 3 development folds and on the holdout, and only with at
least 7 days of bars (E7). Below that the study reports and decides nothing.
The rule first tested the trailing prior alone; at long horizons that was the
weaker baseline, so it was amended to both (E9, 2026-10-07), before the data
that decides existed.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from algoviz.config import Settings
from algoviz.db import async_session
from algoviz.market.bars import SESSION_GAP_MS, Bar
from algoviz.ml.engine import MLEngine
from algoviz.ml.features import FEATURE_NAMES, SCALED_FEATURES
from algoviz.ml.labels import barrier_bps, triple_barrier
from algoviz.ml.train import MIN_PER_FOLD, FoldMetrics, score_split, walk_forward

HORIZONS_S = (5, 15, 30, 60, 120)
BARRIER_KS = (0.5, 1.0, 2.0)
FLOORS_BPS = (0.5, 1.0, 2.0, 4.0)
ALL_FEATURES = "all features"
ABLATIONS: dict[str, tuple[str, ...]] = {
    ALL_FEATURES: (),
    "without hour of day": ("hour_sin", "hour_cos"),
    "without scaled quantities": SCALED_FEATURES,
}
ABLATE_TOP = 3  # the label definitions, best first, the ablations run on
DEV_SHARE = 0.75  # the earlier part, explored; the rest is the holdout, scored once
MIN_DAYS = 7.0  # E7: with fewer days of bars the study reports but decides nothing
MIN_FOLDS_BEATING = 3


@dataclass(frozen=True, slots=True)
class LabelSpec:
    horizon_s: int  # bars are 1 s, so also the horizon in bars
    barrier_k: float
    floor_bps: float

    def __str__(self) -> str:
        return f"{self.horizon_s} s · k {self.barrier_k:g} · floor {self.floor_bps:g} bps"


def label_grid() -> list[LabelSpec]:
    return [LabelSpec(h, k, f) for h in HORIZONS_S for k in BARRIER_KS for f in FLOORS_BPS]


@dataclass(slots=True)
class Samples:
    """Feature vectors of every bar with a full lookback, and what their labels are made of."""

    X: np.ndarray  # (samples, features)
    rows: np.ndarray  # each sample's bar index
    closes: list[float]  # every bar's close
    vol_bps: list[float | None]  # every bar's volatility (it scales the barrier)
    session_end: np.ndarray  # per bar: one past the last bar of its session
    n_bars: int
    sessions: int
    span_ms: tuple[int, int]  # the first and last bar's open time

    @property
    def days(self) -> float:
        """Days of bars (not the calendar span: gaps between sessions don't count)."""
        return self.n_bars / 86_400

    def labels(self, spec: LabelSpec) -> tuple[np.ndarray, np.ndarray]:
        """The samples `spec` can label and their classes; no horizon reaches across a gap."""
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
        return keep, y[keep]


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
        closes=[b.close for b in bars],
        vol_bps=[b.volatility_bps for b in bars],
        session_end=session_end,
        n_bars=len(bars),
        sessions=sessions,
        span_ms=(bars[0].ts_ms, bars[-1].ts_ms),
    )


@dataclass(slots=True)
class ConfigResult:
    spec: LabelSpec
    ablation: str
    n: int  # labelled samples, development and holdout
    flat_share: float
    folds: list[FoldMetrics]  # development walk-forward

    @property
    def edges(self) -> list[float]:
        """Log-loss improvement over the better of the two priors, per development fold."""
        return [
            min(f.prior_log_loss, f.trailing_prior_log_loss) - f.log_loss
            for f in self.folds
            if f.trailing_prior_log_loss is not None
        ]

    @property
    def mean_edge(self) -> float:
        return float(np.mean(self.edges)) if self.edges else -math.inf

    @property
    def beating(self) -> int:
        return sum(e > 0 for e in self.edges)

    @property
    def mean_edge_vs_prior(self) -> float:
        return float(np.mean([f.prior_log_loss - f.log_loss for f in self.folds]))

    @property
    def mean_edge_vs_trailing(self) -> float:
        return float(
            np.mean(
                [
                    f.trailing_prior_log_loss - f.log_loss
                    for f in self.folds
                    if f.trailing_prior_log_loss is not None
                ]
            )
        )


def _design(samples: Samples, spec: LabelSpec, ablation: str) -> tuple[np.ndarray, np.ndarray]:
    keep, y = samples.labels(spec)
    drop = set(ABLATIONS[ablation])
    cols = [j for j, name in enumerate(FEATURE_NAMES) if name not in drop]
    return samples.X[keep][:, cols], y


def evaluate(
    samples: Samples, spec: LabelSpec, ablation: str, *, max_train_size: int, seed: int = 7
) -> ConfigResult:
    """The development walk-forward of one configuration (no folds if it labels too little)."""
    X, y = _design(samples, spec, ablation)
    n_dev = int(len(y) * DEV_SHARE)
    flat = float((y == 1).mean()) if len(y) else 0.0
    folds: list[FoldMetrics] = []
    if n_dev >= MIN_PER_FOLD * 3 and len(np.unique(y[:n_dev])) >= 2:
        folds, _ = walk_forward(
            X[:n_dev], y[:n_dev], spec.horizon_s, seed=seed, max_train_size=max_train_size
        )
    return ConfigResult(spec, ablation, len(y), flat, folds)


def holdout(
    samples: Samples, result: ConfigResult, *, max_train_size: int, seed: int = 7
) -> FoldMetrics | None:
    """Score a configuration once on the later part, trained on the end of the development part."""
    X, y = _design(samples, result.spec, result.ablation)
    n_dev = int(len(y) * DEV_SHARE)
    tr = np.arange(max(0, n_dev - max_train_size), n_dev)
    te = np.arange(n_dev + result.spec.horizon_s, len(y))  # the embargo: no label reaches in
    if len(te) < MIN_PER_FOLD or len(np.unique(y[tr])) < 2:
        return None
    metrics, _ = score_split(X, y, tr, te, result.spec.horizon_s, seed=seed)
    return metrics


@dataclass(frozen=True, slots=True)
class Verdict:
    adopt: bool
    reason: str


def decide(best: ConfigResult, held: FoldMetrics | None, days: float) -> Verdict:
    """The pre-registered rule."""
    if days < MIN_DAYS:
        return Verdict(
            False,
            f"preliminary: {days:.2f} days of bars, the rule needs {MIN_DAYS:g}; nothing is decided",
        )
    if held is None or held.trailing_prior_log_loss is None:
        return Verdict(False, "no holdout to score; nothing is decided")
    edge = min(held.prior_log_loss, held.trailing_prior_log_loss) - held.log_loss
    summary = (
        f"{best.spec} ({best.ablation}) beat both priors in {best.beating} of "
        f"{len(best.folds)} development folds, and the better prior by {edge:+.4f} nats "
        "on the holdout"
    )
    if best.beating >= MIN_FOLDS_BEATING and edge > 0:
        return Verdict(True, f"adopt: {summary}")
    return Verdict(False, f"no edge: {summary}")


@dataclass(slots=True)
class StudyReport:
    samples: Samples
    results: list[ConfigResult]
    best: ConfigResult | None
    holdout: FoldMetrics | None
    verdict: Verdict


def run_study(
    bars: Sequence[Bar],
    cfg: Settings,
    *,
    specs: Sequence[LabelSpec] | None = None,
    seed: int = 7,
    progress: Callable[[ConfigResult], None] | None = None,
) -> StudyReport:
    samples = build_samples(bars, cfg)
    cap = cfg.ML_MAX_SAMPLES  # training windows as large as the served model's, no larger
    results: list[ConfigResult] = []

    def run(spec: LabelSpec, ablation: str) -> None:
        result = evaluate(samples, spec, ablation, max_train_size=cap, seed=seed)
        results.append(result)
        if progress is not None:
            progress(result)

    for spec in specs or label_grid():
        run(spec, ALL_FEATURES)
    ranked = sorted((r for r in results if r.folds), key=lambda r: r.mean_edge, reverse=True)
    for r in ranked[:ABLATE_TOP]:
        for ablation in ABLATIONS:
            if ablation != ALL_FEATURES:
                run(r.spec, ablation)
    scored = [r for r in results if r.folds]
    if not scored:
        verdict = Verdict(False, "too few labelled samples for any configuration")
        return StudyReport(samples, results, None, None, verdict)
    best = max(scored, key=lambda r: r.mean_edge)
    held = holdout(samples, best, max_train_size=cap, seed=seed)
    return StudyReport(samples, results, best, held, decide(best, held, samples.days))


def render(report: StudyReport) -> str:
    """The report as Markdown: the data, the verdict, the holdout and every configuration."""
    s = report.samples
    first, last = (
        datetime.fromtimestamp(t / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M") for t in s.span_ms
    )
    lines = [
        "# Edge study",
        "",
        f"- Data: {s.n_bars:,} bars ({s.days:.2f} days of bars) in {s.sessions} "
        f"session{'s' if s.sessions != 1 else ''}, "
        f"{first} to {last} UTC; {len(s.rows):,} samples with a full lookback.",
        f"- Rule, fixed in advance: adopt only if the model beats both the class prior and the "
        f"trailing prior in at least {MIN_FOLDS_BEATING} development folds and on the holdout, "
        f"with at least {MIN_DAYS:g} days of bars.",
        f"- **Verdict: {report.verdict.reason}.**",
    ]
    if report.best is not None and report.holdout is not None:
        h = report.holdout
        trailing = h.trailing_prior_log_loss
        lines.append(
            f"- Holdout ({report.best.spec}, {report.best.ablation}): {h.n_test:,} samples, "
            f"log-loss {h.log_loss:.4f} vs class prior {h.prior_log_loss:.4f} "
            f"and trailing prior {trailing:.4f}."
            if trailing is not None
            else f"- Holdout: {h.n_test:,} samples, log-loss {h.log_loss:.4f}."
        )
    lines += [
        "",
        "Development walk-forward, best first. Edges are log-loss improvements in nats; "
        "the trailing prior is the class mix of the labels already resolved at each prediction. "
        "The rule's edge is over the better of the two priors, fold by fold.",
        "",
        "| Label | Features | Samples | Flat | Edge vs prior | Edge vs trailing prior "
        "| Edge vs the better prior | Folds beating both |",
        "|---|---|--:|--:|--:|--:|--:|--:|",
    ]
    for r in sorted(report.results, key=lambda r: r.mean_edge, reverse=True):
        if not r.folds:
            lines.append(f"| {r.spec} | {r.ablation} | {r.n:,} | — | — | — | too few samples | — |")
            continue
        sd = float(np.std(r.edges))
        lines.append(
            f"| {r.spec} | {r.ablation} | {r.n:,} | {r.flat_share:.0%} | "
            f"{r.mean_edge_vs_prior:+.4f} | {r.mean_edge_vs_trailing:+.4f} | "
            f"{r.mean_edge:+.4f} ± {sd:.4f} | "
            f"{r.beating} of {len(r.folds)} |"
        )
    return "\n".join(lines) + "\n"
