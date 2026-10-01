"""initial schema

Revision ID: 98b588110c0f
Revises: 
Create Date: 2026-09-17 15:24:56.325890+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '98b588110c0f'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('market_snapshots',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('open', sa.Float(), nullable=False),
    sa.Column('high', sa.Float(), nullable=False),
    sa.Column('low', sa.Float(), nullable=False),
    sa.Column('close', sa.Float(), nullable=False),
    sa.Column('last_price', sa.Float(), nullable=True),
    sa.Column('volume', sa.Float(), nullable=False),
    sa.Column('buy_volume', sa.Float(), nullable=False),
    sa.Column('trade_count', sa.Integer(), nullable=False),
    sa.Column('spread_bps', sa.Float(), nullable=True),
    sa.Column('microprice', sa.Float(), nullable=True),
    sa.Column('imbalance', sa.Float(), nullable=True),
    sa.Column('imbalance_w', sa.Float(), nullable=True),
    sa.Column('ofi', sa.Float(), nullable=True),
    sa.Column('liquidity_5bps', sa.Float(), nullable=True),
    sa.Column('liquidity_10bps', sa.Float(), nullable=True),
    sa.Column('book_slope', sa.Float(), nullable=True),
    sa.Column('vwap', sa.Float(), nullable=True),
    sa.Column('velocity', sa.Float(), nullable=True),
    sa.Column('buy_pressure', sa.Float(), nullable=True),
    sa.Column('volatility_bps', sa.Float(), nullable=True),
    sa.Column('spread_z', sa.Float(), nullable=True),
    sa.Column('velocity_z', sa.Float(), nullable=True),
    sa.Column('vol_z', sa.Float(), nullable=True),
    sa.Column('ofi_z', sa.Float(), nullable=True),
    sa.Column('imbalance_z', sa.Float(), nullable=True),
    sa.Column('regime', sa.String(length=20), nullable=True),
    sa.Column('extra', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('market_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_market_symbol_ts', ['symbol', 'timestamp'], unique=True)

    op.create_table('ml_models',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('model_type', sa.String(length=50), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=True),
    sa.Column('training_samples', sa.Integer(), nullable=True),
    sa.Column('horizon_s', sa.Integer(), nullable=True),
    sa.Column('metrics', sa.JSON(), nullable=True),
    sa.Column('feature_names', sa.JSON(), nullable=True),
    sa.Column('feature_importance', sa.JSON(), nullable=True),
    sa.Column('hyperparameters', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('trained_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ml_models_symbol'), ['symbol'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table('alert_rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('alert_type', sa.String(length=50), nullable=False),
    sa.Column('condition_field', sa.String(length=50), nullable=False),
    sa.Column('comparison', sa.String(length=10), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('message_template', sa.Text(), nullable=True),
    sa.Column('cooldown_seconds', sa.Integer(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('notify_discord', sa.Boolean(), nullable=False),
    sa.Column('notify_email', sa.Boolean(), nullable=False),
    sa.Column('last_fired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('predictions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('model_id', sa.Integer(), nullable=True),
    sa.Column('horizon_s', sa.Integer(), nullable=False),
    sa.Column('mid_at_prediction', sa.Float(), nullable=False),
    sa.Column('p_up', sa.Float(), nullable=False),
    sa.Column('p_down', sa.Float(), nullable=False),
    sa.Column('p_flat', sa.Float(), nullable=False),
    sa.Column('predicted_class', sa.String(length=10), nullable=False),
    sa.Column('resolved', sa.Boolean(), nullable=False),
    sa.Column('realised_class', sa.String(length=10), nullable=True),
    sa.Column('realised_move_bps', sa.Float(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['model_id'], ['ml_models.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_predictions_resolved'), ['resolved'], unique=False)
        batch_op.create_index('ix_predictions_symbol_ts', ['symbol', 'timestamp'], unique=False)

    op.create_table('strategies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('strategy_type', sa.String(length=50), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_public', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('alert_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('rule_name', sa.String(length=100), nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('field', sa.String(length=50), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=True),
    sa.Column('acknowledged', sa.Boolean(), nullable=False),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alert_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alert_history_rule_id'), ['rule_id'], unique=False)
        batch_op.create_index('ix_alert_history_triggered', ['triggered_at'], unique=False)

    op.create_table('backtest_results',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('strategy_id', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('data_source', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('initial_capital', sa.Float(), nullable=False),
    sa.Column('final_capital', sa.Float(), nullable=False),
    sa.Column('total_pnl', sa.Float(), nullable=False),
    sa.Column('total_pnl_pct', sa.Float(), nullable=False),
    sa.Column('total_trades', sa.Integer(), nullable=False),
    sa.Column('win_rate', sa.Float(), nullable=False),
    sa.Column('max_drawdown_pct', sa.Float(), nullable=False),
    sa.Column('sharpe_ratio', sa.Float(), nullable=False),
    sa.Column('sortino_ratio', sa.Float(), nullable=False),
    sa.Column('profit_factor', sa.Float(), nullable=False),
    sa.Column('exposure_pct', sa.Float(), nullable=False),
    sa.Column('commission_bps', sa.Float(), nullable=False),
    sa.Column('slippage_bps', sa.Float(), nullable=False),
    sa.Column('trades_json', sa.JSON(), nullable=False),
    sa.Column('equity_curve_json', sa.JSON(), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backtest_results', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_backtest_results_strategy_id'), ['strategy_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('backtest_results', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_backtest_results_strategy_id'))

    op.drop_table('backtest_results')
    with op.batch_alter_table('alert_history', schema=None) as batch_op:
        batch_op.drop_index('ix_alert_history_triggered')
        batch_op.drop_index(batch_op.f('ix_alert_history_rule_id'))

    op.drop_table('alert_history')
    op.drop_table('strategies')
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_index('ix_predictions_symbol_ts')
        batch_op.drop_index(batch_op.f('ix_predictions_resolved'))

    op.drop_table('predictions')
    op.drop_table('alert_rules')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))

    op.drop_table('users')
    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ml_models_symbol'))

    op.drop_table('ml_models')
    with op.batch_alter_table('market_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_market_symbol_ts')

    op.drop_table('market_snapshots')
