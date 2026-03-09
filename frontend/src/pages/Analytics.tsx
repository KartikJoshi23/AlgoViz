/**
 * AlgoViz — Analytics Page
 *
 * ML predictions, SHAP feature importance, model status, and market stats.
 */

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { BarChart3, Brain, TrendingUp, TrendingDown, Minus, Activity, Zap, Info } from 'lucide-react';
import api from '../api';

interface Prediction {
    direction: string;
    confidence: number;
    predicted_move_bps: number;
    momentum_score: number;
    regime: string;
    signal_action: string;
    model_name: string;
    timestamp: string;
    contributing_factors?: string[];
    reason?: string;
}

interface ShapFeature {
    feature: string;
    importance: number;
    direction: string;
}

interface ModelInfo {
    trained: boolean;
    model_name: string;
    accuracy: number;
    training_samples: number;
    pending_samples: number;
    classes: string[];
    retrain_threshold: number;
    last_trained: string | null;
    feature_count: number;
}

const fadeIn = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.4 },
};

function DirectionIcon({ direction }: { direction: string }) {
    if (direction === 'up' || direction === 'UP') return <TrendingUp size={28} />;
    if (direction === 'down' || direction === 'DOWN') return <TrendingDown size={28} />;
    return <Minus size={28} />;
}

function directionColor(direction: string): string {
    if (direction === 'up' || direction === 'UP') return '#10b981';
    if (direction === 'down' || direction === 'DOWN') return '#ef4444';
    return '#f59e0b';
}

function confidenceGradient(confidence: number): string {
    if (confidence >= 0.7) return 'linear-gradient(135deg, #10b981, #059669)';
    if (confidence >= 0.4) return 'linear-gradient(135deg, #f59e0b, #d97706)';
    return 'linear-gradient(135deg, #6b7280, #4b5563)';
}

export function AnalyticsPage() {
    const { data: prediction, isLoading: predLoading } = useQuery<Prediction>({
        queryKey: ['prediction'],
        queryFn: () => api.get('/analytics/prediction').then(r => r.data),
        refetchInterval: 3000,
    });

    const { data: shapData } = useQuery<{ features: ShapFeature[]; model_trained: boolean }>({
        queryKey: ['shap'],
        queryFn: () => api.get('/analytics/shap').then(r => r.data),
        refetchInterval: 10000,
    });

    const { data: modelInfo } = useQuery<ModelInfo>({
        queryKey: ['model-info'],
        queryFn: () => api.get('/analytics/model-info').then(r => r.data),
        refetchInterval: 15000,
    });

    return (
        <div>
            <div className="page-header">
                <h1 className="page-title">
                    <BarChart3 size={24} style={{ marginRight: 10, verticalAlign: 'middle' }} />
                    Analytics
                </h1>
                <p className="page-subtitle">AI-powered market intelligence and predictions</p>
            </div>

            {/* Row 1: Prediction + Signal */}
            <div className="chart-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <PredictionCard prediction={prediction} loading={predLoading} />
                <SignalCard prediction={prediction} loading={predLoading} />
            </div>

            {/* Row 2: SHAP + Model Info */}
            <div className="chart-grid" style={{ gridTemplateColumns: '2fr 1fr', marginTop: 'var(--space-4)' }}>
                <ShapChart shapData={shapData} />
                <ModelInfoCard modelInfo={modelInfo} />
            </div>

            {/* Row 3: Regime + Contributing Factors */}
            <div className="chart-grid" style={{ gridTemplateColumns: '1fr 1fr', marginTop: 'var(--space-4)' }}>
                <RegimeCard prediction={prediction} />
                <MomentumCard prediction={prediction} />
            </div>
        </div>
    );
}

function PredictionCard({ prediction, loading }: { prediction?: Prediction; loading: boolean }) {
    const dir = prediction?.direction || 'neutral';
    const conf = prediction?.confidence ?? 0;
    const color = directionColor(dir);

    return (
        <motion.div className="card" {...fadeIn}>
            <div className="card-header">
                <div className="card-title">🧠 ML Prediction</div>
                <span className="badge" style={{
                    background: confidenceGradient(conf),
                    color: '#fff',
                    padding: '4px 12px',
                    borderRadius: 12,
                }}>
                    {(conf * 100).toFixed(0)}% confidence
                </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '20px 0' }}>
                <div style={{
                    width: 64, height: 64, borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: `${color}20`, color,
                    border: `2px solid ${color}`,
                }}>
                    <DirectionIcon direction={dir} />
                </div>
                <div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700, textTransform: 'uppercase', color }}>
                        {loading ? '...' : dir}
                    </div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: 4 }}>
                        Predicted move: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                            {prediction?.predicted_move_bps?.toFixed(1) ?? '0.0'} bps
                        </span>
                    </div>
                </div>
            </div>
            {prediction?.contributing_factors && prediction.contributing_factors.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {prediction.contributing_factors.map((f, i) => (
                        <span key={i} className="badge badge-cyan" style={{ fontSize: '0.72rem' }}>{f}</span>
                    ))}
                </div>
            )}
        </motion.div>
    );
}

function SignalCard({ prediction, loading }: { prediction?: Prediction; loading: boolean }) {
    const action = prediction?.signal_action || 'HOLD';
    const actionColors: Record<string, string> = {
        'BUY': '#10b981', 'STRONG_BUY': '#059669',
        'SELL': '#ef4444', 'STRONG_SELL': '#dc2626',
        'HOLD': '#f59e0b',
    };
    const color = actionColors[action] || '#6b7280';

    return (
        <motion.div className="card" {...fadeIn} transition={{ delay: 0.1, duration: 0.4 }}>
            <div className="card-header">
                <div className="card-title">⚡ Signal Action</div>
            </div>
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <motion.div
                    style={{
                        fontSize: '2rem', fontWeight: 800, color,
                        fontFamily: 'var(--font-mono)',
                        letterSpacing: 2,
                    }}
                    animate={{ scale: [1, 1.03, 1] }}
                    transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
                >
                    {loading ? '...' : action}
                </motion.div>
                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 24 }}>
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: 4 }}>Momentum</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '1.1rem' }}>
                            {prediction?.momentum_score?.toFixed(2) ?? '0.00'}
                        </div>
                    </div>
                    <div style={{ width: 1, background: 'var(--border-color)' }} />
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: 4 }}>Model</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.9rem' }}>
                            {prediction?.model_name ?? 'loading'}
                        </div>
                    </div>
                </div>
            </div>
        </motion.div>
    );
}

function ShapChart({ shapData }: { shapData?: { features: ShapFeature[]; model_trained: boolean } }) {
    const features = shapData?.features || [];
    const maxImportance = Math.max(...features.map(f => Math.abs(f.importance)), 0.001);

    return (
        <motion.div className="card" {...fadeIn} transition={{ delay: 0.2, duration: 0.4 }}>
            <div className="card-header">
                <div className="card-title">📊 Feature Importance (SHAP)</div>
                <span className="badge" style={{
                    background: shapData?.model_trained ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    color: shapData?.model_trained ? '#10b981' : '#f59e0b',
                }}>
                    {shapData?.model_trained ? '✓ Trained' : '⏳ Collecting Data'}
                </span>
            </div>
            {features.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
                    <Brain size={36} style={{ marginBottom: 12, opacity: 0.5 }} />
                    <p>Model is accumulating training data…</p>
                    <p style={{ fontSize: '0.8rem', marginTop: 8 }}>SHAP explanations will appear once the model has enough samples to train.</p>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 0' }}>
                    {features.map((f, i) => {
                        const pct = (Math.abs(f.importance) / maxImportance) * 100;
                        const isPositive = f.direction === 'positive' || f.importance > 0;
                        const barColor = isPositive ? '#10b981' : '#ef4444';
                        return (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{
                                    width: 140, fontSize: '0.78rem', color: 'var(--text-secondary)',
                                    textAlign: 'right', fontFamily: 'var(--font-mono)', flexShrink: 0,
                                }}>
                                    {f.feature}
                                </div>
                                <div style={{ flex: 1, height: 18, background: 'var(--bg-secondary)', borderRadius: 4, overflow: 'hidden' }}>
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${pct}%` }}
                                        transition={{ duration: 0.6, delay: i * 0.05 }}
                                        style={{
                                            height: '100%', borderRadius: 4,
                                            background: barColor,
                                            opacity: 0.8,
                                        }}
                                    />
                                </div>
                                <div style={{
                                    width: 50, fontSize: '0.75rem', fontFamily: 'var(--font-mono)',
                                    color: barColor, textAlign: 'right',
                                }}>
                                    {f.importance.toFixed(3)}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </motion.div>
    );
}

function ModelInfoCard({ modelInfo }: { modelInfo?: ModelInfo }) {
    const items = [
        { label: 'Status', value: modelInfo?.trained ? '✅ Trained' : '⏳ Collecting', color: modelInfo?.trained ? '#10b981' : '#f59e0b' },
        { label: 'Accuracy', value: modelInfo?.accuracy ? `${(modelInfo.accuracy * 100).toFixed(1)}%` : 'N/A', color: '#06b6d4' },
        { label: 'Samples', value: modelInfo?.training_samples?.toLocaleString() ?? '0', color: '#8b5cf6' },
        { label: 'Pending', value: modelInfo?.pending_samples?.toLocaleString() ?? '0', color: '#f59e0b' },
        { label: 'Features', value: modelInfo?.feature_count?.toString() ?? '0', color: '#ec4899' },
        { label: 'Retrain @', value: modelInfo?.retrain_threshold?.toString() ?? '100', color: '#6b7280' },
    ];

    return (
        <motion.div className="card" {...fadeIn} transition={{ delay: 0.3, duration: 0.4 }}>
            <div className="card-header">
                <div className="card-title">
                    <Info size={16} style={{ marginRight: 6 }} />
                    Model Status
                </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '8px 0' }}>
                {items.map((item, i) => (
                    <div key={i} style={{
                        padding: '12px',
                        background: 'var(--bg-secondary)',
                        borderRadius: 8,
                        textAlign: 'center',
                    }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                            {item.label}
                        </div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.9rem', color: item.color }}>
                            {item.value}
                        </div>
                    </div>
                ))}
            </div>
            {modelInfo?.model_name && (
                <div style={{
                    marginTop: 8, padding: '8px 12px', background: 'var(--bg-secondary)',
                    borderRadius: 8, fontSize: '0.78rem', color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-mono)',
                }}>
                    Model: {modelInfo.model_name}
                </div>
            )}
        </motion.div>
    );
}

function RegimeCard({ prediction }: { prediction?: Prediction }) {
    const regime = prediction?.regime || 'unknown';
    const regimeConfig: Record<string, { icon: React.ReactNode; color: string; desc: string }> = {
        'trending_up': { icon: <TrendingUp size={20} />, color: '#10b981', desc: 'Strong upward momentum detected' },
        'trending_down': { icon: <TrendingDown size={20} />, color: '#ef4444', desc: 'Downward pressure in effect' },
        'ranging': { icon: <Activity size={20} />, color: '#f59e0b', desc: 'Range-bound, low directional bias' },
        'volatile': { icon: <Zap size={20} />, color: '#8b5cf6', desc: 'High volatility regime' },
        'unknown': { icon: <Minus size={20} />, color: '#6b7280', desc: 'Insufficient data for classification' },
    };
    const cfg = regimeConfig[regime] || regimeConfig['unknown'];

    return (
        <motion.div className="card" {...fadeIn} transition={{ delay: 0.4, duration: 0.4 }}>
            <div className="card-header">
                <div className="card-title">🎯 Market Regime</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '20px 0' }}>
                <div style={{
                    width: 48, height: 48, borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: `${cfg.color}20`, color: cfg.color,
                }}>
                    {cfg.icon}
                </div>
                <div>
                    <div style={{
                        fontSize: '1.1rem', fontWeight: 700, textTransform: 'uppercase',
                        color: cfg.color, fontFamily: 'var(--font-mono)',
                    }}>
                        {regime.replace('_', ' ')}
                    </div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: 4 }}>
                        {cfg.desc}
                    </div>
                </div>
            </div>
        </motion.div>
    );
}

function MomentumCard({ prediction }: { prediction?: Prediction }) {
    const momentum = prediction?.momentum_score ?? 0;
    const normalized = Math.min(Math.abs(momentum) * 50, 100);
    const isPositive = momentum >= 0;
    const color = isPositive ? '#10b981' : '#ef4444';

    return (
        <motion.div className="card" {...fadeIn} transition={{ delay: 0.5, duration: 0.4 }}>
            <div className="card-header">
                <div className="card-title">📈 Momentum Score</div>
            </div>
            <div style={{ padding: '20px 0', textAlign: 'center' }}>
                <div style={{
                    fontSize: '2.5rem', fontWeight: 800, color,
                    fontFamily: 'var(--font-mono)',
                }}>
                    {isPositive ? '+' : ''}{momentum.toFixed(3)}
                </div>
                <div style={{
                    margin: '16px auto 0', width: '80%', height: 8,
                    background: 'var(--bg-secondary)', borderRadius: 4, overflow: 'hidden',
                }}>
                    <motion.div
                        style={{ height: '100%', background: color, borderRadius: 4 }}
                        animate={{ width: `${normalized}%` }}
                        transition={{ duration: 0.5, ease: 'easeOut' }}
                    />
                </div>
                <div style={{ marginTop: 8, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {Math.abs(momentum) < 0.3 ? 'Weak signal' : Math.abs(momentum) < 0.7 ? 'Moderate signal' : 'Strong signal'}
                </div>
            </div>
        </motion.div>
    );
}
