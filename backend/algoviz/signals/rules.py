"""
Signal rules
============

Declarative, stateful rules on the streaming feature context. Each rule has
an `enter` condition and an `exit` condition (hysteresis: a rule that
activates at 2σ deactivates at 1σ, not at 1.99σ), a minimum active duration,
and a cooldown after deactivation. Rules are Pydantic models so they can be
serialised, listed through the API and — later — edited by users.

The defaults are expressed on **z-scores** and regime, so they mean the same
thing on BTC (spread ≈ 0.001 bps) and on SOL (spread ≈ 5 bps).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from algoviz.core.conditions import Cond, Condition, Group, condition_fields

Priority = Literal["high", "medium", "low"]


class SignalRule(BaseModel):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    priority: Priority = "medium"
    enter: Condition
    exit: Condition
    min_duration_s: float = Field(default=0.0, ge=0)
    cooldown_s: float = Field(default=30.0, ge=0)
    message: str = Field(max_length=300)  # str.format(**ctx)
    action: str = Field(default="", max_length=300)
    impact: str = Field(default="", max_length=300)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True

    def fields(self) -> set[str]:
        return condition_fields(self.enter) | condition_fields(self.exit)

    def render(self, ctx: dict[str, object]) -> str:
        class _Safe(dict[str, object]):
            def __missing__(self, key: str) -> str:
                return "?"

        safe = _Safe({k: (v if v is not None else float("nan")) for k, v in ctx.items()})
        try:
            return self.message.format_map(safe)
        except (ValueError, TypeError, KeyError):
            return self.message


def _c(f: str, op: str, v: float | str | list[str]) -> Cond:
    return Cond(f=f, op=op, v=v)


DEFAULT_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        id="spread_widening", name="Spread widening", priority="high",
        enter=_c("spread_z", ">", 2.0), exit=_c("spread_z", "<", 1.0), min_duration_s=2,
        message="Spread {spread_bps:.3f} bps, {spread_z:+.1f}σ above its baseline",
        action="Prefer limit orders; expect worse fills",
        impact="Market orders pay the widened spread on entry and exit",
        tags=["liquidity"],
    ),
    SignalRule(
        id="liquidity_drain", name="Liquidity draining", priority="high",
        enter=_c("liquidity_z", "<", -2.0), exit=_c("liquidity_z", ">", -1.0), min_duration_s=3,
        message="Resting depth within 10 bps is {liquidity_z:+.1f}σ below baseline ({liquidity_10bps:.1f})",
        action="Cut order sizes; slippage risk is elevated",
        impact="Large orders will walk the book",
        tags=["liquidity"],
    ),
    SignalRule(
        id="buy_flow_surge", name="Buy-flow surge", priority="medium",
        enter=_c("ofi_z", ">", 2.0), exit=_c("ofi_z", "<", 0.5),
        message="Order-flow imbalance {ofi_z:+.1f}σ: aggressive buying / bid replenishment",
        action="Short-horizon upward pressure; avoid chasing with market sells",
        impact="OFI is the most cited short-horizon predictor of the next mid move",
        tags=["flow"],
    ),
    SignalRule(
        id="sell_flow_surge", name="Sell-flow surge", priority="medium",
        enter=_c("ofi_z", "<", -2.0), exit=_c("ofi_z", ">", -0.5),
        message="Order-flow imbalance {ofi_z:+.1f}σ: aggressive selling / bid depletion",
        action="Short-horizon downward pressure; delay buys",
        impact="OFI is the most cited short-horizon predictor of the next mid move",
        tags=["flow"],
    ),
    SignalRule(
        id="bid_wall", name="Bid wall", priority="medium",
        enter=_c("imbalance_w", ">", 0.6), exit=_c("imbalance_w", "<", 0.3), min_duration_s=2,
        message="Depth-weighted imbalance {imbalance_w:+.2f}: bids dominate within 15 bps",
        action="Support below; sells may get absorbed",
        impact="Queue-weighted mid (microprice) sits above mid",
        tags=["book"],
    ),
    SignalRule(
        id="ask_wall", name="Ask wall", priority="medium",
        enter=_c("imbalance_w", "<", -0.6), exit=_c("imbalance_w", ">", -0.3), min_duration_s=2,
        message="Depth-weighted imbalance {imbalance_w:+.2f}: asks dominate within 15 bps",
        action="Resistance above; buys may get absorbed",
        impact="Queue-weighted mid (microprice) sits below mid",
        tags=["book"],
    ),
    SignalRule(
        id="vol_expansion", name="Volatility expansion", priority="high",
        enter=_c("vol_z", ">", 2.0), exit=_c("vol_z", "<", 1.0), min_duration_s=3,
        message="Volatility {volatility_bps:.1f} bps/min, {vol_z:+.1f}σ above baseline",
        action="Reduce size; widen stops",
        impact="Stop-outs cluster in expansions",
        tags=["volatility"],
    ),
    SignalRule(
        id="vol_compression", name="Volatility compression", priority="low",
        enter=_c("vol_z", "<", -1.0), exit=_c("vol_z", ">", -0.5), min_duration_s=10, cooldown_s=120,
        message="Volatility {volatility_bps:.1f} bps/min, {vol_z:+.1f}σ below baseline",
        action="Range conditions; mean-reversion tactics favoured",
        impact="Compressions precede expansions",
        tags=["volatility"],
    ),
    SignalRule(
        id="velocity_spike", name="Velocity spike", priority="high",
        enter=_c("velocity_z", ">", 2.5), exit=_c("velocity_z", "<", 1.0),
        message="Trade velocity {velocity:.1f}/s, {velocity_z:+.1f}σ above baseline",
        action="Something is happening: check for news; tighten risk",
        impact="Bursts of activity lead volatility by seconds",
        tags=["flow"],
    ),
    SignalRule(
        id="thin_tape", name="Thin tape", priority="low",
        enter=_c("velocity_z", "<", -1.5), exit=_c("velocity_z", ">", -0.5), min_duration_s=10, cooldown_s=120,
        message="Trade velocity {velocity:.1f}/s, {velocity_z:+.1f}σ below baseline",
        action="Expect slippage; split orders",
        impact="Prints are sparse; the tape lags the book",
        tags=["flow"],
    ),
    SignalRule(
        id="queue_pressure_up", name="Queue pressure up", priority="medium",
        enter=_c("imbalance_l1", ">", 0.8), exit=_c("imbalance_l1", "<", 0.4), min_duration_s=1,
        message="Best-level imbalance {imbalance_l1:+.2f}: bid queue dominates the touch",
        action="Next tick is more likely up",
        impact="Touch imbalance is the classic micro-alpha signal",
        tags=["book"],
    ),
    SignalRule(
        id="queue_pressure_down", name="Queue pressure down", priority="medium",
        enter=_c("imbalance_l1", "<", -0.8), exit=_c("imbalance_l1", ">", -0.4), min_duration_s=1,
        message="Best-level imbalance {imbalance_l1:+.2f}: ask queue dominates the touch",
        action="Next tick is more likely down",
        impact="Touch imbalance is the classic micro-alpha signal",
        tags=["book"],
    ),
    SignalRule(
        id="vol_extreme", name="Extreme volatility", priority="high",
        enter=_c("regime", "==", "extreme"), exit=_c("regime", "in", ["calm", "normal"]),
        message="Volatility state extreme; trend {trend} (strength {regime_direction:+.2f})",
        action="Widen stops, cut size; trade with a significant trend, never against it",
        impact="The highest-variance state the HMM knows",
        tags=["regime"],
    ),
    SignalRule(
        id="vol_calm", name="Calm market", priority="low",
        enter=_c("regime", "==", "calm"), exit=_c("regime", "!=", "calm"),
        min_duration_s=30, cooldown_s=300,
        message="Volatility state calm",
        action="Low-variance state; patience",
        impact="Signals are weaker and slower when the market is calm",
        tags=["regime"],
    ),
    SignalRule(
        id="trend_up", name="Trending up", priority="medium",
        enter=_c("trend", "==", "up"), exit=_c("trend", "!=", "up"),
        min_duration_s=10, cooldown_s=120,
        message="Significant up-drift over 2 min (strength {regime_direction:+.2f})",
        action="Favour longs; fading needs a reason",
        impact="Fires only when the drift's Newey–West t-statistic clears 2",
        tags=["regime"],
    ),
    SignalRule(
        id="trend_down", name="Trending down", priority="medium",
        enter=_c("trend", "==", "down"), exit=_c("trend", "!=", "down"),
        min_duration_s=10, cooldown_s=120,
        message="Significant down-drift over 2 min (strength {regime_direction:+.2f})",
        action="Favour shorts; fading needs a reason",
        impact="Fires only when the drift's Newey–West t-statistic clears 2",
        tags=["regime"],
    ),
    SignalRule(
        id="model_long", name="Model leans long", priority="medium",
        enter=Group(all=[_c("p_up", ">", 0.5), _c("p_down", "<", 0.3)]), exit=_c("p_up", "<", 0.42),
        message="Calibrated P(up) {p_up:.0%} vs P(down) {p_down:.0%} over the horizon",
        action="Model edge is directional; size according to calibration",
        impact="Only meaningful when the drift monitor shows edge",
        tags=["model"],
    ),
    SignalRule(
        id="model_short", name="Model leans short", priority="medium",
        enter=Group(all=[_c("p_down", ">", 0.5), _c("p_up", "<", 0.3)]), exit=_c("p_down", "<", 0.42),
        message="Calibrated P(down) {p_down:.0%} vs P(up) {p_up:.0%} over the horizon",
        action="Model edge is directional; size according to calibration",
        impact="Only meaningful when the drift monitor shows edge",
        tags=["model"],
    ),
)  # fmt: skip

DEFAULT_RULE_IDS: tuple[str, ...] = tuple(r.id for r in DEFAULT_RULES)
