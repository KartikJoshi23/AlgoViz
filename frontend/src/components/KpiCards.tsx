/**
 * AlgoViz — KPI Cards Component
 *
 * Displays key performance indicators with animated values.
 */

import { motion } from 'framer-motion';
import { useStore, type MarketFeatures } from '../store';

function formatPrice(n: number): string {
    if (n === 0) return '—';
    if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`;
    return `$${n.toFixed(2)}`;
}

function formatBps(n: number): string {
    return `${n.toFixed(1)} bps`;
}

function formatPct(n: number): string {
    const sign = n >= 0 ? '+' : '';
    return `${sign}${n.toFixed(2)}%`;
}

function formatVelocity(n: number): string {
    return `${n.toFixed(1)}/s`;
}

interface KpiDef {
    key: keyof MarketFeatures;
    label: string;
    format: (v: number) => string;
    accent: string;
    changeKey?: keyof MarketFeatures;
}

const kpis: KpiDef[] = [
    { key: 'current_price', label: 'Price', format: formatPrice, accent: '#06b6d4', changeKey: 'price_change_pct' },
    { key: 'spread_bps', label: 'Spread', format: formatBps, accent: '#8b5cf6' },
    { key: 'vwap', label: 'VWAP', format: formatPrice, accent: '#3b82f6' },
    { key: 'velocity', label: 'Velocity', format: formatVelocity, accent: '#f59e0b' },
    { key: 'imbalance_pct', label: 'Imbalance', format: formatPct, accent: '#10b981' },
    { key: 'volatility_bps', label: 'Volatility', format: formatBps, accent: '#ef4444' },
    { key: 'buy_pressure', label: 'Buy Pressure', format: (v) => `${(v * 100).toFixed(1)}%`, accent: '#ec4899' },
];

export function KpiCards() {
    const features = useStore((s) => s.features);

    return (
        <div className="kpi-grid">
            {kpis.map((kpi, i) => {
                const value = features[kpi.key] as number;
                const change = kpi.changeKey ? (features[kpi.changeKey] as number) : null;

                return (
                    <motion.div
                        key={kpi.key}
                        className="kpi-card"
                        style={{ '--kpi-accent': kpi.accent } as React.CSSProperties}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05, duration: 0.3 }}
                    >
                        <div className="kpi-label">{kpi.label}</div>
                        <div className="kpi-value">{kpi.format(value)}</div>
                        {change !== null && (
                            <div className={`kpi-change ${change >= 0 ? 'positive' : 'negative'}`}>
                                {change >= 0 ? '▲' : '▼'} {formatPct(change)}
                            </div>
                        )}
                    </motion.div>
                );
            })}
        </div>
    );
}
