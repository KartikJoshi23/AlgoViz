"""regime split: volatility state labels and a trend column

The single "regime" becomes two axes. Its four labels were volatility states
all along (each HMM state is labelled by its mean volatility z), so they are
renamed for what they measure — quiet → calm, trending → normal, volatile →
elevated, breakout → extreme — and the trend (down / flat / up) gets its own
column. Stored bars and saved strategies' regime conditions are rewritten.

Revision ID: 4c1e7b2a9d30
Revises: 98b588110c0f
Create Date: 2026-09-26 12:00:00+00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import context, op

revision: str = '4c1e7b2a9d30'
down_revision: str | None = '98b588110c0f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAME = {"quiet": "calm", "trending": "normal", "volatile": "elevated", "breakout": "extreme"}

snapshots = sa.table("market_snapshots", sa.column("regime", sa.String))
strategies = sa.table("strategies", sa.column("id", sa.Integer), sa.column("config", sa.JSON))


def _rename_values(node: Any, mapping: dict[str, str]) -> Any:
    """Rewrite the values of `regime` conditions anywhere in a condition tree."""
    if isinstance(node, list):
        return [_rename_values(n, mapping) for n in node]
    if not isinstance(node, dict):
        return node
    out = {k: _rename_values(v, mapping) for k, v in node.items()}
    if out.get("f") == "regime":
        v = out.get("v")
        out["v"] = [mapping.get(x, x) for x in v] if isinstance(v, list) else mapping.get(v, v)
    return out


def _migrate(mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        op.execute(snapshots.update().where(snapshots.c.regime == old).values(regime=new))
    if context.is_offline_mode():
        return  # --sql renders DDL only; strategy configs are rewritten against a live database
    conn = op.get_bind()
    for sid, config in conn.execute(sa.select(strategies.c.id, strategies.c.config)).all():
        rewritten = _rename_values(config, mapping)
        if rewritten != config:
            conn.execute(strategies.update().where(strategies.c.id == sid).values(config=rewritten))


def upgrade() -> None:
    with op.batch_alter_table('market_snapshots') as batch:
        batch.add_column(sa.Column('trend', sa.String(length=8), nullable=True))
    _migrate(RENAME)


def downgrade() -> None:
    _migrate({new: old for old, new in RENAME.items()})
    with op.batch_alter_table('market_snapshots') as batch:
        batch.drop_column('trend')
