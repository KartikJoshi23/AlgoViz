/**
 * AlgoViz — Dashboard Page
 *
 * Main dashboard with KPIs, charts, and trading intelligence.
 */

import { motion } from 'framer-motion';
import { KpiCards } from '../components/KpiCards';
import { PriceChart } from '../components/PriceChart';
import { InsightPanel } from '../components/InsightPanel';
import { useStore } from '../store';

function MetricGauge({ label, value, max, unit, color }: {
    label: string; value: number; max: number; unit: string; color: string;
}) {
    const pct = Math.min((value / max) * 100, 100);
    return (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
            <div className="card-title" style={{ marginBottom: '12px' }}>{label}</div>
            <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '1.5rem',
                fontWeight: 700,
                color,
                marginBottom: '8px',
            }}>
                {value.toFixed(1)} {unit}
            </div>
            <div style={{
                height: 6,
                background: 'var(--bg-secondary)',
                borderRadius: 3,
                overflow: 'hidden',
            }}>
                <motion.div
                    style={{
                        height: '100%',
                        background: color,
                        borderRadius: 3,
                    }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                />
            </div>
        </div>
    );
}

export function DashboardPage() {
    const features = useStore((s) => s.features);
    const connected = useStore((s) => s.connected);

    return (
        <div>
            <div className="page-header">
                <h1 className="page-title">
                    Dashboard
                    {connected && (
                        <span className="badge badge-green" style={{ marginLeft: 12, fontSize: '0.65rem', verticalAlign: 'middle' }}>
                            ● LIVE
                        </span>
                    )}
                </h1>
                <p className="page-subtitle">Real-time market intelligence for {features.symbol}</p>
            </div>

            {/* KPI Cards */}
            <KpiCards />

            {/* Charts Row 1: Price + Insights */}
            <div className="chart-grid">
                <PriceChart />
                <InsightPanel />
            </div>

            {/* Charts Row 2: Metric Gauges */}
            <div className="chart-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <MetricGauge
                    label="Spread"
                    value={features.spread_bps}
                    max={10}
                    unit="bps"
                    color={features.spread_bps > 6 ? '#ef4444' : features.spread_bps < 2 ? '#10b981' : '#f59e0b'}
                />
                <MetricGauge
                    label="Trade Velocity"
                    value={features.velocity}
                    max={60}
                    unit="/s"
                    color={features.velocity > 40 ? '#ef4444' : features.velocity > 20 ? '#f59e0b' : '#10b981'}
                />
                <MetricGauge
                    label="Volatility"
                    value={features.volatility_bps}
                    max={30}
                    unit="bps"
                    color={features.volatility_bps > 20 ? '#ef4444' : features.volatility_bps > 10 ? '#f59e0b' : '#10b981'}
                />
                <MetricGauge
                    label="Order Imbalance"
                    value={Math.abs(features.imbalance_pct)}
                    max={100}
                    unit="%"
                    color={Math.abs(features.imbalance_pct) > 50 ? '#ef4444' : '#06b6d4'}
                />
            </div>

            {/* Recent Trades */}
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
                <div className="card-header">
                    <div className="card-title">📋 Recent Trades</div>
                    <span className="badge badge-cyan">{useStore.getState().trades.length} buffered</span>
                </div>
                <RecentTrades />
            </div>
        </div>
    );
}

function RecentTrades() {
    const trades = useStore((s) => s.trades);
    const recent = trades.slice(-10).reverse();

    if (recent.length === 0) {
        return (
            <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Waiting for trade data…
            </div>
        );
    }

    return (
        <table className="data-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Price</th>
                    <th>Qty</th>
                    <th>Side</th>
                </tr>
            </thead>
            <tbody>
                {recent.map((t, i) => (
                    <tr key={`${t.trade_id}-${i}`}>
                        <td>{new Date(t.timestamp).toLocaleTimeString()}</td>
                        <td style={{ color: t.is_buyer_maker ? '#ef4444' : '#10b981' }}>
                            ${t.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        <td>{t.quantity.toFixed(5)}</td>
                        <td>
                            <span className={`badge ${t.is_buyer_maker ? 'badge-red' : 'badge-green'}`}>
                                {t.is_buyer_maker ? 'SELL' : 'BUY'}
                            </span>
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}
