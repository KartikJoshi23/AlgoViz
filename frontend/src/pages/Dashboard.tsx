/**
 * AlgoViz — Dashboard Page
 *
 * Main dashboard with MarketPulse hero, KPIs, live charts, and trading intelligence.
 * Bloomberg Terminal meets Cyberpunk aesthetic.
 */

import { useStore } from '../store';
import { KpiCards } from '../components/KpiCards';
import { PriceChart } from '../components/PriceChart';
import { InsightPanel } from '../components/InsightPanel';
import { MarketPulse } from '../components/MarketPulse';
import { OrderBookChart } from '../components/OrderBookChart';
import { VelocityGauge } from '../components/VelocityGauge';
import { SpreadHeatmap } from '../components/SpreadHeatmap';
import { VolatilityChart } from '../components/VolatilityChart';

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

export function DashboardPage() {
    const connected = useStore((s) => s.connected);
    const features = useStore((s) => s.features);

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

            {/* Row 0: MarketPulse Hero + KPI Cards */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '240px 1fr',
                gap: 'var(--space-4)',
                marginBottom: 'var(--space-4)',
            }}>
                <MarketPulse />
                <KpiCards />
            </div>

            {/* Row 1: Price Chart + Insight Panel */}
            <div className="chart-grid">
                <PriceChart />
                <InsightPanel />
            </div>

            {/* Row 2: Order Book + Velocity Gauge */}
            <div className="chart-grid" style={{ marginTop: 'var(--space-4)' }}>
                <OrderBookChart />
                <VelocityGauge />
            </div>

            {/* Row 3: Spread Heatmap + Volatility Chart */}
            <div className="chart-grid" style={{ marginTop: 'var(--space-4)' }}>
                <SpreadHeatmap />
                <VolatilityChart />
            </div>

            {/* Row 4: Recent Trades */}
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
