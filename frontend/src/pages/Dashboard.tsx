/**
 * AlgoViz — Dashboard Page (Premium Redesign)
 *
 * Hero-level trading dashboard with animated ticker, neon KPIs,
 * glassmorphism cards, and live data visualization.
 */

import { useStore } from '../store';
import { motion } from 'framer-motion';
import { PriceChart } from '../components/PriceChart';
import { InsightPanel } from '../components/InsightPanel';
import { OrderBookChart } from '../components/OrderBookChart';
import { VelocityGauge } from '../components/VelocityGauge';
import { SpreadHeatmap } from '../components/SpreadHeatmap';
import { VolatilityChart } from '../components/VolatilityChart';
import { TrendingUp, TrendingDown, Activity, Zap, BarChart3, Gauge, Waves, ShieldCheck } from 'lucide-react';

/* ── Animated Ticker Tape ─────────────────────────────────────────── */
function TickerTape() {
    const features = useStore((s) => s.features);
    const price = features.current_price;
    const spread = features.spread_bps;
    const velocity = features.velocity;
    const imbalance = features.imbalance;
    const buyPressure = features.buy_pressure;
    const vwap = features.vwap;

    const items = [
        { label: 'BTC/USDT', value: `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`, color: '#06b6d4', icon: '₿' },
        { label: 'SPREAD', value: `${spread.toFixed(1)} bps`, color: '#8b5cf6', icon: '◇' },
        { label: 'VELOCITY', value: `${velocity.toFixed(1)}/s`, color: '#f59e0b', icon: '⚡' },
        { label: 'IMBALANCE', value: `${(imbalance * 100).toFixed(1)}%`, color: imbalance > 0 ? '#10b981' : '#ef4444', icon: '⇅' },
        { label: 'BUY PRESSURE', value: `${(buyPressure * 100).toFixed(1)}%`, color: buyPressure > 0.5 ? '#10b981' : '#ef4444', icon: '◈' },
        { label: 'VWAP', value: `$${vwap.toLocaleString(undefined, { maximumFractionDigits: 2 })}`, color: '#ec4899', icon: '◆' },
    ];

    // Duplicate for seamless loop
    const allItems = [...items, ...items, ...items];

    return (
        <div className="ticker-tape">
            <motion.div
                className="ticker-track"
                animate={{ x: ['0%', '-33.33%'] }}
                transition={{ duration: 30, repeat: Infinity, ease: 'linear' }}
            >
                {allItems.map((item, i) => (
                    <div key={i} className="ticker-item">
                        <span className="ticker-icon" style={{ color: item.color }}>{item.icon}</span>
                        <span className="ticker-label">{item.label}</span>
                        <span className="ticker-value" style={{ color: item.color }}>{item.value}</span>
                        <span className="ticker-separator">│</span>
                    </div>
                ))}
            </motion.div>
            <div className="ticker-fade-left" />
            <div className="ticker-fade-right" />
        </div>
    );
}

/* ── Hero KPI Card ────────────────────────────────────────────────── */
function HeroKpi({ icon: Icon, label, value, change, color, delay = 0 }: {
    icon: React.ElementType; label: string; value: string;
    change?: string; color: string; delay?: number;
}) {
    return (
        <motion.div
            className="hero-kpi"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay, duration: 0.5 }}
            whileHover={{ y: -6, scale: 1.02 }}
            style={{ '--kpi-color': color } as React.CSSProperties}
        >
            <div className="hero-kpi-glow" />
            <div className="hero-kpi-icon">
                <Icon size={20} />
            </div>
            <div className="hero-kpi-label">{label}</div>
            <div className="hero-kpi-value">{value}</div>
            {change && (
                <div className="hero-kpi-change" style={{
                    color: change.startsWith('+') ? '#10b981' : change.startsWith('-') ? '#ef4444' : '#8888aa'
                }}>
                    {change}
                </div>
            )}
        </motion.div>
    );
}

/* ── Dashboard Page ───────────────────────────────────────────────── */
export function DashboardPage() {
    const connected = useStore((s) => s.connected);
    const features = useStore((s) => s.features);
    const trades = useStore((s) => s.trades);

    const price = features.current_price;
    const spread = features.spread_bps;
    const vwap = features.vwap;
    const velocity = features.velocity;
    const imbalance = features.imbalance;
    const buyPressure = features.buy_pressure;
    const volatility = features.volatility_bps;

    const recent = trades.slice(-8).reverse();

    return (
        <div className="dashboard">
            {/* Ticker Tape */}
            <TickerTape />

            {/* Page Header */}
            <motion.div
                className="dash-header"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
            >
                <div>
                    <h1 className="dash-title">
                        Dashboard
                        {connected && (
                            <motion.span
                                className="dash-live-badge"
                                animate={{ opacity: [1, 0.5, 1] }}
                                transition={{ duration: 2, repeat: Infinity }}
                            >
                                ● LIVE
                            </motion.span>
                        )}
                    </h1>
                    <p className="dash-subtitle">Real-time market intelligence for {features.symbol}</p>
                </div>
            </motion.div>

            {/* Hero KPI Row */}
            <div className="hero-kpi-grid">
                <HeroKpi icon={TrendingUp} label="PRICE" value={`$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                    change={features.price_change_pct ? `${features.price_change_pct > 0 ? '+' : ''}${features.price_change_pct.toFixed(2)}%` : undefined}
                    color="#06b6d4" delay={0.05} />
                <HeroKpi icon={Activity} label="SPREAD" value={`${spread.toFixed(1)} bps`} color="#8b5cf6" delay={0.1} />
                <HeroKpi icon={Gauge} label="VWAP" value={`$${vwap.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} color="#f59e0b" delay={0.15} />
                <HeroKpi icon={Zap} label="VELOCITY" value={`${velocity.toFixed(1)}/s`} color="#ec4899" delay={0.2} />
                <HeroKpi icon={BarChart3} label="IMBALANCE" value={`${(imbalance * 100).toFixed(1)}%`} color={imbalance > 0 ? '#10b981' : '#ef4444'} delay={0.25} />
                <HeroKpi icon={Waves} label="VOLATILITY" value={`${volatility.toFixed(1)} bps`} color="#f97316" delay={0.3} />
                <HeroKpi icon={ShieldCheck} label="BUY PRESSURE" value={`${(buyPressure * 100).toFixed(1)}%`} color={buyPressure > 0.5 ? '#10b981' : '#ef4444'} delay={0.35} />
            </div>

            {/* Charts Row 1 */}
            <div className="dash-grid-2">
                <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
                    <PriceChart />
                </motion.div>
                <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
                    <InsightPanel />
                </motion.div>
            </div>

            {/* Charts Row 2 */}
            <div className="dash-grid-2">
                <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }}>
                    <OrderBookChart />
                </motion.div>
                <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}>
                    <VelocityGauge />
                </motion.div>
            </div>

            {/* Charts Row 3 */}
            <div className="dash-grid-2">
                <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.45 }}>
                    <SpreadHeatmap />
                </motion.div>
                <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
                    <VolatilityChart />
                </motion.div>
            </div>

            {/* Recent Trades */}
            <motion.div className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.55 }}>
                <div className="card-header">
                    <div className="card-title">📋 Recent Trades</div>
                    <span className="badge badge-cyan">{trades.length} buffered</span>
                </div>
                {recent.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        Waiting for trade data…
                    </div>
                ) : (
                    <table className="data-table">
                        <thead>
                            <tr><th>Time</th><th>Price</th><th>Qty</th><th>Side</th></tr>
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
                )}
            </motion.div>
        </div>
    );
}
