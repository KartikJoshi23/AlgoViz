/**
 * AlgoViz — Strategies Page
 *
 * Strategy CRUD, backtesting, and results visualization.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { GitBranch, Plus, Play, Trash2, ChevronDown, ChevronRight, X } from 'lucide-react';
import api from '../api';

interface Strategy {
    id: number;
    name: string;
    description: string;
    strategy_type: string;
    config: Record<string, unknown>;
    is_active: boolean;
    created_at: string;
}

interface BacktestResult {
    id: number;
    strategy_id: number;
    total_pnl: number;
    total_trades: number;
    win_rate: number;
    initial_capital: number;
    final_capital: number;
    created_at: string;
}

const STRATEGY_TYPES = [
    { value: 'momentum', label: 'Momentum', color: '#10b981' },
    { value: 'mean_reversion', label: 'Mean Reversion', color: '#8b5cf6' },
    { value: 'breakout', label: 'Breakout', color: '#f59e0b' },
    { value: 'arbitrage', label: 'Arbitrage', color: '#06b6d4' },
    { value: 'custom', label: 'Custom', color: '#ec4899' },
];

const fadeIn = {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -16 },
    transition: { duration: 0.3 },
};

export function StrategiesPage() {
    const queryClient = useQueryClient();
    const [showCreate, setShowCreate] = useState(false);
    const [expandedId, setExpandedId] = useState<number | null>(null);

    const { data: strategies = [], isLoading } = useQuery<Strategy[]>({
        queryKey: ['strategies'],
        queryFn: () => api.get('/strategies/').then(r => r.data),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => api.delete(`/strategies/${id}`),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategies'] }),
    });

    return (
        <div>
            <div className="page-header">
                <h1 className="page-title">
                    <GitBranch size={24} style={{ marginRight: 10, verticalAlign: 'middle' }} />
                    Strategies
                </h1>
                <p className="page-subtitle">Build, backtest, and manage trading strategies</p>
            </div>

            {/* Action Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                    {strategies.length} strateg{strategies.length === 1 ? 'y' : 'ies'}
                </div>
                <button
                    className="btn-primary"
                    onClick={() => setShowCreate(true)}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '10px 20px', borderRadius: 8,
                        background: 'linear-gradient(135deg, #10b981, #059669)',
                        color: '#fff', border: 'none', cursor: 'pointer',
                        fontWeight: 600, fontSize: '0.85rem',
                    }}
                >
                    <Plus size={16} /> New Strategy
                </button>
            </div>

            {/* Create Form */}
            <AnimatePresence>
                {showCreate && (
                    <CreateStrategyForm onClose={() => setShowCreate(false)} />
                )}
            </AnimatePresence>

            {/* Strategy List */}
            {isLoading ? (
                <div className="card" style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    Loading strategies…
                </div>
            ) : strategies.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '60px 40px' }}>
                    <GitBranch size={48} color="var(--text-muted)" style={{ marginBottom: 16, opacity: 0.4 }} />
                    <h3 style={{ marginBottom: 8, color: 'var(--text-secondary)' }}>No Strategies Yet</h3>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        Create your first strategy to start backtesting
                    </p>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {strategies.map((s) => (
                        <StrategyCard
                            key={s.id}
                            strategy={s}
                            expanded={expandedId === s.id}
                            onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)}
                            onDelete={() => deleteMutation.mutate(s.id)}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

function CreateStrategyForm({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient();
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [strategyType, setStrategyType] = useState('momentum');

    const createMutation = useMutation({
        mutationFn: (data: { name: string; description: string; strategy_type: string; config: Record<string, unknown> }) =>
            api.post('/strategies/', data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['strategies'] });
            onClose();
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!name.trim()) return;
        createMutation.mutate({
            name: name.trim(),
            description: description.trim(),
            strategy_type: strategyType,
            config: {},
        });
    };

    return (
        <motion.div className="card" style={{ marginBottom: 'var(--space-4)' }} {...fadeIn}>
            <div className="card-header">
                <div className="card-title">Create Strategy</div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                    <X size={18} />
                </button>
            </div>
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '8px 0' }}>
                <input
                    type="text" value={name} onChange={(e) => setName(e.target.value)}
                    placeholder="Strategy name" required
                    style={{
                        padding: '10px 14px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                        borderRadius: 8, color: 'var(--text-primary)', fontSize: '0.9rem', outline: 'none',
                    }}
                />
                <textarea
                    value={description} onChange={(e) => setDescription(e.target.value)}
                    placeholder="Description (optional)" rows={2}
                    style={{
                        padding: '10px 14px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                        borderRadius: 8, color: 'var(--text-primary)', fontSize: '0.9rem', resize: 'vertical', outline: 'none',
                        fontFamily: 'inherit',
                    }}
                />
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {STRATEGY_TYPES.map((t) => (
                        <button
                            key={t.value} type="button"
                            onClick={() => setStrategyType(t.value)}
                            style={{
                                padding: '6px 14px', borderRadius: 6, fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
                                border: strategyType === t.value ? `2px solid ${t.color}` : '2px solid var(--border-color)',
                                background: strategyType === t.value ? `${t.color}20` : 'transparent',
                                color: strategyType === t.value ? t.color : 'var(--text-secondary)',
                            }}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                    <button type="button" onClick={onClose} style={{
                        padding: '8px 20px', borderRadius: 8, background: 'var(--bg-secondary)',
                        border: '1px solid var(--border-color)', color: 'var(--text-secondary)', cursor: 'pointer',
                    }}>
                        Cancel
                    </button>
                    <button type="submit" disabled={createMutation.isPending} style={{
                        padding: '8px 20px', borderRadius: 8,
                        background: 'linear-gradient(135deg, #10b981, #059669)',
                        border: 'none', color: '#fff', cursor: 'pointer', fontWeight: 600,
                    }}>
                        {createMutation.isPending ? 'Creating…' : 'Create'}
                    </button>
                </div>
            </form>
        </motion.div>
    );
}

function StrategyCard({
    strategy, expanded, onToggle, onDelete,
}: {
    strategy: Strategy; expanded: boolean; onToggle: () => void; onDelete: () => void;
}) {
    const typeCfg = STRATEGY_TYPES.find((t) => t.value === strategy.strategy_type) || STRATEGY_TYPES[4];

    return (
        <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div
                style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    cursor: 'pointer', padding: '4px 0',
                }}
                onClick={onToggle}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    <div>
                        <div style={{ fontWeight: 600, fontSize: '1rem' }}>{strategy.name}</div>
                        {strategy.description && (
                            <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: 2 }}>
                                {strategy.description}
                            </div>
                        )}
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="badge" style={{
                        background: `${typeCfg.color}20`, color: typeCfg.color,
                    }}>
                        {typeCfg.label}
                    </span>
                    <button
                        onClick={(e) => { e.stopPropagation(); onDelete(); }}
                        title="Delete" style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--text-muted)', padding: 4,
                        }}
                    >
                        <Trash2 size={16} />
                    </button>
                </div>
            </div>

            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        style={{ overflow: 'hidden' }}
                    >
                        <div style={{ borderTop: '1px solid var(--border-color)', marginTop: 12, paddingTop: 16 }}>
                            <BacktestSection strategyId={strategy.id} />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}

function BacktestSection({ strategyId }: { strategyId: number }) {
    const queryClient = useQueryClient();
    const [capital, setCapital] = useState('10000');

    const { data: backtests = [] } = useQuery<BacktestResult[]>({
        queryKey: ['backtests', strategyId],
        queryFn: () => api.get(`/strategies/${strategyId}/backtests`).then(r => r.data),
    });

    const runMutation = useMutation({
        mutationFn: () => api.post(`/strategies/${strategyId}/backtest`, {
            initial_capital: parseFloat(capital) || 10000,
        }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backtests', strategyId] }),
    });

    return (
        <div>
            {/* Run Backtest */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Capital $</label>
                <input
                    type="number" value={capital} onChange={(e) => setCapital(e.target.value)}
                    style={{
                        width: 120, padding: '6px 10px', background: 'var(--bg-secondary)',
                        border: '1px solid var(--border-color)', borderRadius: 6,
                        color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.85rem',
                    }}
                />
                <button
                    onClick={() => runMutation.mutate()}
                    disabled={runMutation.isPending}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '6px 16px', borderRadius: 6,
                        background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                        border: 'none', color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem',
                    }}
                >
                    <Play size={14} />
                    {runMutation.isPending ? 'Running…' : 'Run Backtest'}
                </button>
            </div>

            {/* Results */}
            {backtests.length > 0 ? (
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Initial</th>
                            <th>Final</th>
                            <th>P&L</th>
                            <th>Win Rate</th>
                            <th>Trades</th>
                        </tr>
                    </thead>
                    <tbody>
                        {backtests.slice(0, 5).map((b) => (
                            <tr key={b.id}>
                                <td>{new Date(b.created_at).toLocaleDateString()}</td>
                                <td>${b.initial_capital.toLocaleString()}</td>
                                <td>${b.final_capital.toLocaleString()}</td>
                                <td style={{ color: b.total_pnl >= 0 ? '#10b981' : '#ef4444' }}>
                                    {b.total_pnl >= 0 ? '+' : ''}${b.total_pnl.toFixed(2)}
                                </td>
                                <td>{(b.win_rate * 100).toFixed(1)}%</td>
                                <td>{b.total_trades}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            ) : (
                <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                    No backtest results yet. Run your first backtest above.
                </div>
            )}
        </div>
    );
}
