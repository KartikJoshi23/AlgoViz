"""
Condition evaluator
===================

The one declarative condition language shared by signal rules, alert rules
and backtest strategies:

    {"f": "ofi_z", "op": ">", "v": 1.5}
    {"all": [cond, ...]}   /   {"any": [cond, ...]}   /   {"not": cond}

Field names are validated against the feature catalog (plus a few
evaluation-context extras such as `bars_held`). Missing or `None` values make
a leaf condition *false*, never an error, so a rule on `spread_z` simply
stays quiet during warm-up.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from algoviz.market.catalog import FEATURE_REGISTRY

Op = Literal[">", ">=", "<", "<=", "==", "!=", "in", "not_in", "gt", "gte", "lt", "lte", "eq"]

_OP_ALIASES: dict[str, str] = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=="}

# Fields that exist only inside an evaluation context (not in the catalog).
CONTEXT_FIELDS: dict[str, str] = {
    "bars_held": "Bars since the current position was opened (backtest / signal state)",
    "position": "Current position: 1 long, -1 short, 0 flat (backtest)",
    "unrealised_bps": "Open P&L of the current position in bps (backtest)",
    "seconds_active": "Seconds since the signal became active (signal state)",
}

NUMERIC_OPS = frozenset({">", ">=", "<", "<=", "==", "!="})
SET_OPS = frozenset({"in", "not_in"})


def normalise_op(op: str) -> str:
    return _OP_ALIASES.get(op, op)


class Cond(BaseModel):
    """Leaf condition."""

    f: str = Field(min_length=1, max_length=50)
    op: Op
    v: float | int | str | bool | list[str | float | int]

    @model_validator(mode="after")
    def _validate(self) -> Cond:
        op = normalise_op(self.op)
        spec = FEATURE_REGISTRY.get(self.f)
        if spec is None and self.f not in CONTEXT_FIELDS:
            raise ValueError(f"unknown feature '{self.f}'")
        if spec is not None and spec.kind == "categorical":
            if op not in ("==", "!=", "in", "not_in"):
                raise ValueError(f"operator '{self.op}' not valid for categorical '{self.f}'")
            values = self.v if isinstance(self.v, list) else [self.v]
            bad = [x for x in values if x not in spec.values]
            if bad:
                raise ValueError(f"invalid value(s) for '{self.f}': {bad}")
        else:
            if op in SET_OPS and not isinstance(self.v, list):
                raise ValueError(f"'{self.op}' needs a list value")
            if op in NUMERIC_OPS and isinstance(self.v, list | str | bool):
                raise ValueError(f"'{self.op}' on '{self.f}' needs a numeric value")
        return self

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        x = ctx.get(self.f)
        if x is None:
            return False
        op = normalise_op(self.op)
        v = self.v
        try:
            if op == ">":
                return float(x) > float(v)  # type: ignore[arg-type]
            if op == ">=":
                return float(x) >= float(v)  # type: ignore[arg-type]
            if op == "<":
                return float(x) < float(v)  # type: ignore[arg-type]
            if op == "<=":
                return float(x) <= float(v)  # type: ignore[arg-type]
            if op == "==":
                return x == v if isinstance(v, str) else float(x) == float(v)  # type: ignore[arg-type]
            if op == "!=":
                return x != v if isinstance(v, str) else float(x) != float(v)  # type: ignore[arg-type]
            if op == "in":
                return x in v  # type: ignore[operator]
            if op == "not_in":
                return x not in v  # type: ignore[operator]
        except (TypeError, ValueError):
            return False
        return False

    def describe(self) -> str:
        return f"{self.f} {normalise_op(self.op)} {self.v}"


class Group(BaseModel):
    """`all` / `any` / `not` combinator. Exactly one key must be set."""

    all: list[Condition] | None = None
    any: list[Condition] | None = None
    not_: Condition | None = Field(default=None, alias="not")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _one_of(self) -> Group:
        set_keys = [k for k in ("all", "any", "not_") if getattr(self, k) is not None]
        if len(set_keys) != 1:
            raise ValueError("a group must have exactly one of: all, any, not")
        if self.all is not None and len(self.all) == 0:
            raise ValueError("'all' must contain at least one condition")
        if self.any is not None and len(self.any) == 0:
            raise ValueError("'any' must contain at least one condition")
        return self

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        if self.all is not None:
            return all(c.evaluate(ctx) for c in self.all)
        if self.any is not None:
            return any(c.evaluate(ctx) for c in self.any)
        assert self.not_ is not None
        return not self.not_.evaluate(ctx)

    def describe(self) -> str:
        if self.all is not None:
            return "(" + " AND ".join(c.describe() for c in self.all) + ")"
        if self.any is not None:
            return "(" + " OR ".join(c.describe() for c in self.any) + ")"
        assert self.not_ is not None
        return f"NOT {self.not_.describe()}"

    def fields(self) -> set[str]:
        out: set[str] = set()
        for c in (self.all or []) + (self.any or []) + ([self.not_] if self.not_ else []):
            out |= c.fields() if isinstance(c, Group) else {c.f}
        return out


Condition = Cond | Group

Group.model_rebuild()


def parse_condition(raw: Any) -> Condition:
    """Parse a dict into a Cond or Group (raises pydantic ValidationError)."""
    if isinstance(raw, Cond | Group):
        return raw
    if isinstance(raw, dict) and any(k in raw for k in ("all", "any", "not")):
        return Group.model_validate(raw)
    return Cond.model_validate(raw)


def condition_fields(cond: Condition) -> set[str]:
    return cond.fields() if isinstance(cond, Group) else {cond.f}
