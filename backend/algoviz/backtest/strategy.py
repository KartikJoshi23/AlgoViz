"""
Strategy specification
======================

The declarative JSON stored on `Strategy.config`, validated with the same
condition language as signals and alerts. Example:

    {
      "side": "both", "size_pct": 25,
      "entry_long":  {"all": [{"f": "ofi_z", "op": ">", "v": 1.5}, {"f": "regime", "op": "in", "v": ["elevated", "extreme"]}]},
      "entry_short": {"all": [{"f": "ofi_z", "op": "<", "v": -1.5}]},
      "exit":        {"any": [{"f": "bars_held", "op": ">=", "v": 30}, {"f": "ofi_z", "op": "<", "v": 0}]},
      "stop_loss_bps": 20, "take_profit_bps": 40, "max_hold_s": 120
    }

`ml_signal` strategies express their entries on `p_up` / `p_down`, which the
runner joins in from the persisted predictions table.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from algoviz.core.conditions import Cond, Condition, Group, condition_fields, parse_condition

Side = Literal["long", "short", "both"]


class StrategySpec(BaseModel):
    side: Side = "both"
    size_pct: float = Field(default=100.0, gt=0, le=100)  # % of equity per position
    entry_long: Condition | None = None
    entry_short: Condition | None = None
    exit: Condition | None = None
    stop_loss_bps: float | None = Field(default=None, gt=0, le=10_000)
    take_profit_bps: float | None = Field(default=None, gt=0, le=10_000)
    max_hold_s: int | None = Field(default=None, gt=0, le=86_400)
    cooldown_s: int = Field(default=0, ge=0, le=86_400)

    @model_validator(mode="before")
    @classmethod
    def _parse_conditions(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            for key in ("entry_long", "entry_short", "exit"):
                if data.get(key) is not None and not isinstance(data[key], Cond | Group):
                    data[key] = parse_condition(data[key])
        return data

    @model_validator(mode="after")
    def _check(self) -> StrategySpec:
        if self.side in ("long", "both") and self.entry_long is None:
            raise ValueError("entry_long is required for side=long/both")
        if self.side in ("short", "both") and self.entry_short is None:
            raise ValueError("entry_short is required for side=short/both")
        if (
            self.exit is None
            and self.stop_loss_bps is None
            and self.take_profit_bps is None
            and self.max_hold_s is None
        ):
            raise ValueError(
                "at least one exit mechanism is required (exit / stop_loss_bps / take_profit_bps / max_hold_s)"
            )
        return self

    def fields(self) -> set[str]:
        out: set[str] = set()
        for c in (self.entry_long, self.entry_short, self.exit):
            if c is not None:
                out |= condition_fields(c)
        return out

    @property
    def uses_model(self) -> bool:
        return bool(self.fields() & {"p_up", "p_down"})

    def describe(self) -> dict[str, str | None]:
        return {
            "entry_long": self.entry_long.describe() if self.entry_long else None,
            "entry_short": self.entry_short.describe() if self.entry_short else None,
            "exit": self.exit.describe() if self.exit else None,
        }


EXAMPLE_SPECS: dict[str, dict[str, Any]] = {
    "ofi_momentum": {
        "side": "both",
        "size_pct": 50,
        "entry_long": {
            "all": [
                {"f": "ofi_z", "op": ">", "v": 1.5},
                {"f": "regime", "op": "not_in", "v": ["calm"]},
            ]
        },
        "entry_short": {
            "all": [
                {"f": "ofi_z", "op": "<", "v": -1.5},
                {"f": "regime", "op": "not_in", "v": ["calm"]},
            ]
        },
        "exit": {"any": [{"f": "bars_held", "op": ">=", "v": 30}]},
        "stop_loss_bps": 15,
        "take_profit_bps": 30,
    },
    "queue_imbalance_scalp": {
        "side": "both",
        "size_pct": 100,
        "entry_long": {"f": "imbalance_l1", "op": ">", "v": 0.8},
        "entry_short": {"f": "imbalance_l1", "op": "<", "v": -0.8},
        "max_hold_s": 10,
        "take_profit_bps": 3,
        "stop_loss_bps": 5,
    },
    "model_signal": {
        "side": "both",
        "size_pct": 50,
        "entry_long": {
            "all": [{"f": "p_up", "op": ">", "v": 0.5}, {"f": "p_down", "op": "<", "v": 0.3}]
        },
        "entry_short": {
            "all": [{"f": "p_down", "op": ">", "v": 0.5}, {"f": "p_up", "op": "<", "v": 0.3}]
        },
        "max_hold_s": 30,
        "stop_loss_bps": 10,
    },
}
