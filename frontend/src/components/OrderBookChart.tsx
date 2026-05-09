/**
 * AlgoViz — Order Book Depth Visualization
 *
 * Bidirectional horizontal bar chart showing bid/ask liquidity walls.
 * Bids extend left (green gradient), asks extend right (red gradient).
 */

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../store';

interface Level {
    price: number;
    quantity: number;
    cumulative: number;
    pct: number;
}

export function OrderBookChart() {
    const features = useStore((s) => s.features);
    const {
        best_bid, best_ask, bid_volume, ask_volume,
        spread_bps,
    } = features;

    // Generate synthetic depth levels from features data
    const { bids, asks } = useMemo(() => {
        if (best_bid === 0 || best_ask === 0) {
            return { bids: [] as Level[], asks: [] as Level[], maxCum: 1 };
        }

        const levels = 8;
        const step = spread_bps > 0 ? (best_ask - best_bid) * 0.5 : 0.5;

        const bidLevels: Level[] = [];
        let bidCum = 0;
        for (let i = 0; i < levels; i++) {
            const qty = (bid_volume / levels) * (1 + Math.random() * 0.4 - 0.2) * (1 - i * 0.06);
            bidCum += qty;
            bidLevels.push({
                price: best_bid - i * step,
                quantity: qty,
                cumulative: bidCum,
                pct: 0,
            });
        }

        const askLevels: Level[] = [];
        let askCum = 0;
        for (let i = 0; i < levels; i++) {
            const qty = (ask_volume / levels) * (1 + Math.random() * 0.4 - 0.2) * (1 - i * 0.06);
            askCum += qty;
            askLevels.push({
                price: best_ask + i * step,
                quantity: qty,
                cumulative: askCum,
                pct: 0,
            });
        }

        const maxC = Math.max(bidCum, askCum, 0.001);
        bidLevels.forEach((l) => (l.pct = (l.cumulative / maxC) * 100));
        askLevels.forEach((l) => (l.pct = (l.cumulative / maxC) * 100));

        return { bids: bidLevels, asks: askLevels, maxCum: maxC };
    }, [best_bid, best_ask, bid_volume, ask_volume, spread_bps]);

    const barHeight = 22;
    const gap = 3;

    if (best_bid === 0) {
        return (
            <div className="card" style={{ padding: 'var(--space-4)' }}>
                <div className="card-title" style={{ marginBottom: 12 }}>📊 Order Book Depth</div>
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    Waiting for depth data…
                </div>
            </div>
        );
    }

    return (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
            <div className="card-header">
                <div className="card-title">📊 Order Book Depth</div>
                <div style={{ display: 'flex', gap: 12, fontSize: '0.72rem' }}>
                    <span style={{ color: '#10b981', fontFamily: 'var(--font-mono)' }}>
                        Bids: {bid_volume.toFixed(2)}
                    </span>
                    <span style={{ color: '#ef4444', fontFamily: 'var(--font-mono)' }}>
                        Asks: {ask_volume.toFixed(2)}
                    </span>
                </div>
            </div>

            <div style={{ display: 'flex', gap: 2, marginTop: 12 }}>
                {/* Bids (left) */}
                <div style={{ flex: 1 }}>
                    {bids.map((level, i) => (
                        <div
                            key={`bid-${i}`}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                height: barHeight,
                                marginBottom: gap,
                                justifyContent: 'flex-end',
                                position: 'relative',
                            }}
                        >
                            <span style={{
                                fontSize: '0.68rem', fontFamily: 'var(--font-mono)',
                                color: 'var(--text-secondary)', marginRight: 8, zIndex: 1,
                                minWidth: 70, textAlign: 'right',
                            }}>
                                ${level.price.toFixed(1)}
                            </span>
                            <div style={{
                                position: 'absolute', right: 0, top: 0, bottom: 0,
                                borderRadius: '4px 0 0 4px', overflow: 'hidden',
                            }}>
                                <motion.div
                                    initial={{ width: 0 }}
                                    animate={{ width: `${level.pct * 2}px` }}
                                    transition={{ duration: 0.5, delay: i * 0.03 }}
                                    style={{
                                        height: '100%',
                                        background: `linear-gradient(90deg, rgba(16,185,129,0.08), rgba(16,185,129,${0.15 + level.pct * 0.004}))`,
                                        borderRadius: '4px 0 0 4px',
                                    }}
                                />
                            </div>
                        </div>
                    ))}
                </div>

                {/* Center divider with spread */}
                <div style={{
                    width: 2, alignSelf: 'stretch',
                    background: `linear-gradient(180deg, #10b981, var(--border-primary), #ef4444)`,
                    borderRadius: 1, position: 'relative',
                }}>
                    <div style={{
                        position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                        background: 'var(--bg-card)', padding: '2px 6px', borderRadius: 4,
                        fontSize: '0.6rem', color: 'var(--text-muted)', whiteSpace: 'nowrap',
                        fontFamily: 'var(--font-mono)',
                    }}>
                        {spread_bps.toFixed(1)}bp
                    </div>
                </div>

                {/* Asks (right) */}
                <div style={{ flex: 1 }}>
                    {asks.map((level, i) => (
                        <div
                            key={`ask-${i}`}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                height: barHeight,
                                marginBottom: gap,
                                position: 'relative',
                            }}
                        >
                            <div style={{
                                position: 'absolute', left: 0, top: 0, bottom: 0,
                                borderRadius: '0 4px 4px 0', overflow: 'hidden',
                            }}>
                                <motion.div
                                    initial={{ width: 0 }}
                                    animate={{ width: `${level.pct * 2}px` }}
                                    transition={{ duration: 0.5, delay: i * 0.03 }}
                                    style={{
                                        height: '100%',
                                        background: `linear-gradient(90deg, rgba(239,68,68,${0.15 + level.pct * 0.004}), rgba(239,68,68,0.08))`,
                                        borderRadius: '0 4px 4px 0',
                                    }}
                                />
                            </div>
                            <span style={{
                                fontSize: '0.68rem', fontFamily: 'var(--font-mono)',
                                color: 'var(--text-secondary)', marginLeft: 8, zIndex: 1,
                            }}>
                                ${level.price.toFixed(1)}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
