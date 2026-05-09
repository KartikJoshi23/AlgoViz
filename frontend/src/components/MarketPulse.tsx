/**
 * AlgoViz — MarketPulse Hero Component
 *
 * Animated concentric rings that pulse in sync with trade velocity.
 * A visual "heartbeat" fingerprint of market state — unique to AlgoViz.
 */

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../store';

function regimeColor(volatility: number, velocity: number, baseline: number): string {
    if (volatility > 20) return '#ef4444'; // Volatile — red
    if (velocity > baseline * 2) return '#f59e0b'; // Surge — amber
    if (volatility < 10) return '#06b6d4'; // Calm — cyan
    return '#8b5cf6'; // Normal — purple
}

export function MarketPulse() {
    const features = useStore((s) => s.features);
    const connected = useStore((s) => s.connected);

    const {
        current_price, velocity, velocity_baseline, volatility_bps,
        buy_pressure, spread_bps, imbalance,
    } = features;

    // Derived values
    const pulseSpeed = useMemo(() => {
        if (!connected || velocity === 0) return 3;
        const ratio = velocity / Math.max(velocity_baseline, 1);
        return Math.max(0.4, 3 / Math.max(ratio, 0.5));
    }, [velocity, velocity_baseline, connected]);

    const ringColor = useMemo(
        () => regimeColor(volatility_bps, velocity, velocity_baseline),
        [volatility_bps, velocity, velocity_baseline],
    );

    const buyArc = buy_pressure * 360;
    const imbalanceAngle = imbalance * 45; // -45° to +45°

    const SIZE = 200;
    const CX = SIZE / 2;
    const CY = SIZE / 2;

    const rings = [
        { r: 80, width: 2.5, opacity: 0.6, delay: 0 },
        { r: 68, width: 2, opacity: 0.45, delay: 0.15 },
        { r: 56, width: 1.5, opacity: 0.3, delay: 0.3 },
    ];

    // SVG arc path helper
    function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
        const s = (startDeg - 90) * (Math.PI / 180);
        const e = (endDeg - 90) * (Math.PI / 180);
        const x1 = cx + r * Math.cos(s);
        const y1 = cy + r * Math.sin(s);
        const x2 = cx + r * Math.cos(e);
        const y2 = cy + r * Math.sin(e);
        const large = endDeg - startDeg > 180 ? 1 : 0;
        return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
    }

    return (
        <div className="card" style={{ padding: 'var(--space-4)', overflow: 'hidden', position: 'relative' }}>
            <div className="card-title" style={{ marginBottom: 12, zIndex: 1, position: 'relative' }}>
                ⚡ Market Pulse
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                {/* Background glow */}
                <div style={{
                    position: 'absolute', width: 160, height: 160, borderRadius: '50%',
                    background: `radial-gradient(circle, ${ringColor}15 0%, transparent 70%)`,
                    filter: 'blur(20px)',
                }} />

                <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
                    {/* Pulsing concentric rings */}
                    {rings.map((ring, i) => (
                        <motion.circle
                            key={i}
                            cx={CX} cy={CY} r={ring.r}
                            fill="none"
                            stroke={ringColor}
                            strokeWidth={ring.width}
                            opacity={ring.opacity}
                            animate={{
                                r: [ring.r, ring.r + 4, ring.r],
                                opacity: [ring.opacity, ring.opacity * 1.5, ring.opacity],
                                strokeWidth: [ring.width, ring.width * 1.4, ring.width],
                            }}
                            transition={{
                                duration: pulseSpeed,
                                delay: ring.delay,
                                repeat: Infinity,
                                ease: 'easeInOut',
                            }}
                        />
                    ))}

                    {/* Buy pressure arc (green) */}
                    {buyArc > 5 && (
                        <motion.path
                            d={arcPath(CX, CY, 44, 0, Math.min(buyArc, 359))}
                            fill="none"
                            stroke="#10b981"
                            strokeWidth={4}
                            strokeLinecap="round"
                            opacity={0.7}
                            animate={{ opacity: [0.5, 0.8, 0.5] }}
                            transition={{ duration: 2, repeat: Infinity }}
                        />
                    )}

                    {/* Sell pressure arc (red) */}
                    {buyArc < 355 && (
                        <motion.path
                            d={arcPath(CX, CY, 44, Math.min(buyArc, 359), 360)}
                            fill="none"
                            stroke="#ef4444"
                            strokeWidth={4}
                            strokeLinecap="round"
                            opacity={0.5}
                        />
                    )}

                    {/* Imbalance needle */}
                    <motion.line
                        x1={CX} y1={CY - 30}
                        x2={CX} y2={CY - 42}
                        stroke={imbalance > 0 ? '#10b981' : '#ef4444'}
                        strokeWidth={2}
                        strokeLinecap="round"
                        animate={{ rotate: imbalanceAngle }}
                        transition={{ type: 'spring', stiffness: 60, damping: 15 }}
                        style={{ transformOrigin: `${CX}px ${CY}px` }}
                    />

                    {/* Orbiting particles */}
                    {[0, 1, 2].map((i) => (
                        <motion.circle
                            key={`particle-${i}`}
                            r={2}
                            fill={ringColor}
                            opacity={0.6}
                            animate={{
                                cx: [
                                    CX + 74 * Math.cos((i * 120) * Math.PI / 180),
                                    CX + 74 * Math.cos((i * 120 + 360) * Math.PI / 180),
                                ],
                                cy: [
                                    CY + 74 * Math.sin((i * 120) * Math.PI / 180),
                                    CY + 74 * Math.sin((i * 120 + 360) * Math.PI / 180),
                                ],
                            }}
                            transition={{
                                duration: pulseSpeed * 3,
                                repeat: Infinity,
                                ease: 'linear',
                            }}
                        />
                    ))}

                    {/* Center price */}
                    <text
                        x={CX} y={CY - 6}
                        textAnchor="middle"
                        fill="var(--text-primary, #fafafa)"
                        fontSize="14"
                        fontWeight="700"
                        fontFamily="var(--font-mono)"
                    >
                        ${current_price > 0 ? current_price.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
                    </text>
                    <text
                        x={CX} y={CY + 12}
                        textAnchor="middle"
                        fill="var(--text-muted, #666)"
                        fontSize="9"
                        fontFamily="var(--font-mono)"
                    >
                        {velocity.toFixed(1)}/s · {volatility_bps.toFixed(1)}bps
                    </text>
                </svg>
            </div>

            {/* Bottom stats row */}
            <div style={{
                display: 'flex', justifyContent: 'space-around', marginTop: 8,
                fontSize: '0.72rem', color: 'var(--text-muted)',
            }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ color: '#10b981', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                        {(buy_pressure * 100).toFixed(0)}%
                    </div>
                    <div>Buy</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ color: ringColor, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                        {spread_bps.toFixed(1)}
                    </div>
                    <div>Spread</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ color: '#ef4444', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                        {((1 - buy_pressure) * 100).toFixed(0)}%
                    </div>
                    <div>Sell</div>
                </div>
            </div>
        </div>
    );
}
