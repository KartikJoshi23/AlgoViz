"""market bars: an index on (symbol, source, timestamp)

Reads of the bars filter by source as well as symbol (training history, the
edge study, collection progress), which the (symbol, timestamp) index cannot
serve: counting a source's bars scanned the whole table. Measured on 36,178
live bars: 27.7 ms as a scan, 7.0 ms on this index (covering); the scan grows
with the table, to seconds at the 60 days of bars production keeps.

Revision ID: b7d2f05c1e94
Revises: 4c1e7b2a9d30
Create Date: 2026-10-08 19:00:00+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'b7d2f05c1e94'
down_revision: str | None = '4c1e7b2a9d30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('market_snapshots') as batch:
        batch.create_index('ix_market_symbol_source_ts', ['symbol', 'source', 'timestamp'])


def downgrade() -> None:
    with op.batch_alter_table('market_snapshots') as batch:
        batch.drop_index('ix_market_symbol_source_ts')
