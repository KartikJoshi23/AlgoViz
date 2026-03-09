/**
 * AlgoViz — Alerts Page
 *
 * Alert rule management, creation, history feed, and acknowledgment.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, Plus, Check, CheckCheck, X, Trash2 } from 'lucide-react';
import api from '../api';

interface AlertRule {
    id: number;
    name: string;
    alert_type: string;
    condition_field: string;
    comparison: string;
    threshold: number;
    priority: string;
    message_template: string | null;
    cooldown_seconds: number;
    notify_discord: boolean;
    notify_email: boolean;
    is_active: boolean;
    created_at: string;
}

interface AlertHistoryItem {
    id: number;
    rule_name: string;
    priority: string;
    message: string;
    triggered_at: string;
    acknowledged: boolean;
    acknowledged_at: string | null;
}

const PRIORITY_CONFIG: Record<string, { emoji: string; color: string; bg: string }> = {
    HIGH: { emoji: '🔴', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
    MEDIUM: { emoji: '🟡', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
    LOW: { emoji: '🟢', color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
};

const CONDITION_FIELDS = [
    'spread_bps', 'volatility_bps', 'velocity', 'imbalance',
    'price_change_pct', 'buy_pressure', 'current_price',
];

const COMPARISONS = [
    { value: 'gt', label: '>' },
    { value: 'gte', label: '≥' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '≤' },
    { value: 'eq', label: '=' },
];

export function AlertsPage() {
    const queryClient = useQueryClient();
    const [showCreate, setShowCreate] = useState(false);

    const { data: rules = [] } = useQuery<AlertRule[]>({
        queryKey: ['alert-rules'],
        queryFn: () => api.get('/alerts/rules').then(r => r.data),
    });

    const { data: history = [] } = useQuery<AlertHistoryItem[]>({
        queryKey: ['alert-history'],
        queryFn: () => api.get('/alerts/history?limit=30').then(r => r.data),
        refetchInterval: 5000,
    });

    const ackAllMutation = useMutation({
        mutationFn: () => api.post('/alerts/history/acknowledge-all'),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-history'] }),
    });

    const deleteRuleMutation = useMutation({
        mutationFn: (id: number) => api.delete(`/alerts/rules/${id}`),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-rules'] }),
    });

    const unacked = history.filter(h => !h.acknowledged).length;

    return (
        <div>
            <div className="page-header">
                <h1 className="page-title">
                    <Bell size={24} style={{ marginRight: 10, verticalAlign: 'middle' }} />
                    Alerts
                    {unacked > 0 && (
                        <span className="badge badge-red" style={{ marginLeft: 10, fontSize: '0.7rem', verticalAlign: 'middle' }}>
                            {unacked} new
                        </span>
                    )}
                </h1>
                <p className="page-subtitle">Custom alert rules with multi-channel notifications</p>
            </div>

            {/* Action Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => setShowCreate(true)} style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '8px 16px', borderRadius: 8,
                        background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                        border: 'none', color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem',
                    }}>
                        <Plus size={15} /> New Rule
                    </button>
                    {unacked > 0 && (
                        <button onClick={() => ackAllMutation.mutate()} style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 16px', borderRadius: 8,
                            background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                            color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.82rem',
                        }}>
                            <CheckCheck size={15} /> Acknowledge All
                        </button>
                    )}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                    {rules.length} rule{rules.length !== 1 ? 's' : ''} active
                </div>
            </div>

            {/* Create Rule Form */}
            <AnimatePresence>
                {showCreate && <CreateRuleForm onClose={() => setShowCreate(false)} />}
            </AnimatePresence>

            {/* Two-column layout: Rules + History */}
            <div className="chart-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                {/* Alert Rules */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">📋 Alert Rules</div>
                    </div>
                    {rules.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
                            <Bell size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
                            <p style={{ fontSize: '0.85rem' }}>No rules configured</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
                            {rules.map((rule) => {
                                const pri = PRIORITY_CONFIG[rule.priority] || PRIORITY_CONFIG.LOW;
                                return (
                                    <motion.div key={rule.id}
                                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                        style={{
                                            padding: '12px 14px', borderRadius: 8,
                                            background: pri.bg, border: `1px solid ${pri.color}30`,
                                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                        }}
                                    >
                                        <div>
                                            <div style={{ fontWeight: 600, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                                                {pri.emoji} {rule.name}
                                            </div>
                                            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                                                {rule.condition_field} {COMPARISONS.find(c => c.value === rule.comparison)?.label || rule.comparison} {rule.threshold}
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => deleteRuleMutation.mutate(rule.id)}
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}
                                        >
                                            <Trash2 size={15} />
                                        </button>
                                    </motion.div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Alert History */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">🕐 Alert History</div>
                        <span className="badge" style={{
                            background: unacked > 0 ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)',
                            color: unacked > 0 ? '#ef4444' : '#10b981',
                        }}>
                            {unacked > 0 ? `${unacked} unacked` : 'all clear'}
                        </span>
                    </div>
                    {history.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
                            <Check size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
                            <p style={{ fontSize: '0.85rem' }}>No alerts triggered yet</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 0', maxHeight: 400, overflowY: 'auto' }}>
                            {history.map((h) => (
                                <AlertHistoryRow key={h.id} item={h} />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function AlertHistoryRow({ item }: { item: AlertHistoryItem }) {
    const queryClient = useQueryClient();
    const pri = PRIORITY_CONFIG[item.priority] || PRIORITY_CONFIG.LOW;

    const ackMutation = useMutation({
        mutationFn: () => api.post(`/alerts/history/${item.id}/acknowledge`),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-history'] }),
    });

    return (
        <div style={{
            padding: '10px 12px', borderRadius: 6,
            background: item.acknowledged ? 'transparent' : pri.bg,
            border: `1px solid ${item.acknowledged ? 'var(--border-color)' : `${pri.color}30`}`,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            opacity: item.acknowledged ? 0.6 : 1,
        }}>
            <div style={{ flex: 1 }}>
                <div style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    {pri.emoji}
                    <span style={{ fontWeight: item.acknowledged ? 400 : 600 }}>{item.message || item.rule_name}</span>
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
                    {new Date(item.triggered_at).toLocaleString()}
                </div>
            </div>
            {!item.acknowledged && (
                <button onClick={() => ackMutation.mutate()} title="Acknowledge" style={{
                    background: 'none', border: 'none', cursor: 'pointer', color: '#10b981', padding: 4,
                }}>
                    <Check size={16} />
                </button>
            )}
        </div>
    );
}

function CreateRuleForm({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient();
    const [name, setName] = useState('');
    const [conditionField, setConditionField] = useState('spread_bps');
    const [comparison, setComparison] = useState('gt');
    const [threshold, setThreshold] = useState('5');
    const [priority, setPriority] = useState('MEDIUM');

    const createMutation = useMutation({
        mutationFn: (data: Record<string, unknown>) => api.post('/alerts/rules', data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['alert-rules'] });
            onClose();
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!name.trim()) return;
        createMutation.mutate({
            name: name.trim(),
            alert_type: 'threshold',
            condition_field: conditionField,
            comparison,
            threshold: parseFloat(threshold),
            priority,
            cooldown_seconds: 60,
            notify_discord: false,
            notify_email: false,
        });
    };

    return (
        <motion.div className="card" style={{ marginBottom: 'var(--space-4)' }}
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }}
        >
            <div className="card-header">
                <div className="card-title">New Alert Rule</div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                    <X size={18} />
                </button>
            </div>
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '8px 0' }}>
                <input
                    type="text" value={name} onChange={(e) => setName(e.target.value)}
                    placeholder="Rule name (e.g. High Spread Alert)" required
                    style={{
                        padding: '10px 14px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                        borderRadius: 8, color: 'var(--text-primary)', fontSize: '0.9rem', outline: 'none',
                    }}
                />
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <select value={conditionField} onChange={(e) => setConditionField(e.target.value)} style={{
                        flex: 1, padding: '8px 12px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                        borderRadius: 6, color: 'var(--text-primary)', fontSize: '0.85rem',
                    }}>
                        {CONDITION_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                    <select value={comparison} onChange={(e) => setComparison(e.target.value)} style={{
                        width: 60, padding: '8px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                        borderRadius: 6, color: 'var(--text-primary)', textAlign: 'center', fontSize: '0.95rem',
                    }}>
                        {COMPARISONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                    <input
                        type="number" step="any" value={threshold} onChange={(e) => setThreshold(e.target.value)}
                        style={{
                            width: 100, padding: '8px 10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                            borderRadius: 6, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.85rem',
                        }}
                    />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    {(['HIGH', 'MEDIUM', 'LOW'] as const).map(p => {
                        const cfg = PRIORITY_CONFIG[p];
                        return (
                            <button key={p} type="button" onClick={() => setPriority(p)} style={{
                                padding: '6px 16px', borderRadius: 6, fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
                                border: priority === p ? `2px solid ${cfg.color}` : '2px solid var(--border-color)',
                                background: priority === p ? cfg.bg : 'transparent',
                                color: priority === p ? cfg.color : 'var(--text-secondary)',
                            }}>
                                {cfg.emoji} {p}
                            </button>
                        );
                    })}
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
                        background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                        border: 'none', color: '#fff', cursor: 'pointer', fontWeight: 600,
                    }}>
                        {createMutation.isPending ? 'Creating…' : 'Create Rule'}
                    </button>
                </div>
            </form>
        </motion.div>
    );
}
