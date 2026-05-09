/**
 * AlgoViz — Velocity Gauge
 *
 * Animated radial speedometer showing trades/sec.
 * Glowing arc segments with spring-physics needle and particle sparks.
 */

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../store';

export function VelocityGauge() {
    const velocity = useStore((s) => s.features.velocity);
    const baseline = useStore((s) => s.features.velocity_baseline);

    const MAX = 80;
    const SIZE = 200;
    const CX = SIZE / 2;
    const CY = SIZE / 2 + 10;
    const RADIUS = 75;
    const START_ANGLE = -225;
    const END_ANGLE = 45;
    const SWEEP = END_ANGLE - START_ANGLE; // 270 degrees

    const clampedVel = Math.min(velocity, MAX);
    const pct = clampedVel / MAX;
    const needleAngle = START_ANGLE + pct * SWEEP;

    // Determine zone
    const zone = useMemo(() => {
        if (velocity > baseline * 2) return { color: '#ef4444', label: 'SURGE', glow: '#ef444440' };
        if (velocity > baseline * 1.2) return { color: '#f59e0b', label: 'ACTIVE', glow: '#f59e0b30' };
        if (velocity > baseline * 0.5) return { color: '#10b981', label: 'NORMAL', glow: '#10b98130' };
        return { color: '#6b7280', label: 'QUIET', glow: '#6b728020' };
    }, [velocity, baseline]);

    // Arc segment helper
    function describeArc(startDeg: number, endDeg: number, r: number): string {
        const s = (startDeg) * (Math.PI / 180);
        const e = (endDeg) * (Math.PI / 180);
        const x1 = CX + r * Math.cos(s);
        const y1 = CY + r * Math.sin(s);
        const x2 = CX + r * Math.cos(e);
        const y2 = CY + r * Math.sin(e);
        const large = (endDeg - startDeg) > 180 ? 1 : 0;
        return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
    }

    // Arc zones (in render-space degrees)
    const zones = [
        { from: 0, to: 0.25, color: '#10b981' }, // Normal green
        { from: 0.25, to: 0.5, color: '#22d3ee' }, // Cyan
        { from: 0.5, to: 0.75, color: '#f59e0b' }, // Amber
        { from: 0.75, to: 1.0, color: '#ef4444' }, // Red
    ];

    // Baseline tick position
    const baselinePct = Math.min(baseline / MAX, 1);
    const baselineAngle = (START_ANGLE + baselinePct * SWEEP) * (Math.PI / 180);
    const bTickX1 = CX + (RADIUS - 8) * Math.cos(baselineAngle);
    const bTickY1 = CY + (RADIUS - 8) * Math.sin(baselineAngle);
    const bTickX2 = CX + (RADIUS + 4) * Math.cos(baselineAngle);
    const bTickY2 = CY + (RADIUS + 4) * Math.sin(baselineAngle);

    return (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
            <div className="card-title" style={{ marginBottom: 8 }}>🏎️ Trade Velocity</div>

            <div style={{ display: 'flex', justifyContent: 'center', position: 'relative' }}>
                {/* Glow */}
                <div style={{
                    position: 'absolute', width: 120, height: 120,
                    top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                    borderRadius: '50%', background: zone.glow, filter: 'blur(25px)',
                }} />

                <svg width={SIZE} height={SIZE * 0.7} viewBox={`0 0 ${SIZE} ${SIZE * 0.75}`}>
                    {/* Background arc */}
                    <path
                        d={describeArc(START_ANGLE, END_ANGLE, RADIUS)}
                        fill="none"
                        stroke="var(--bg-secondary, #1a1a2e)"
                        strokeWidth={10}
                        strokeLinecap="round"
                    />

                    {/* Zone arcs */}
                    {zones.map((z, i) => (
                        <path
                            key={i}
                            d={describeArc(
                                START_ANGLE + z.from * SWEEP,
                                START_ANGLE + z.to * SWEEP,
                                RADIUS,
                            )}
                            fill="none"
                            stroke={z.color}
                            strokeWidth={10}
                            strokeLinecap="round"
                            opacity={0.2}
                        />
                    ))}

                    {/* Active fill arc */}
                    <motion.path
                        d={describeArc(START_ANGLE, START_ANGLE + 1, RADIUS)}
                        fill="none"
                        stroke={zone.color}
                        strokeWidth={10}
                        strokeLinecap="round"
                        animate={{
                            d: describeArc(START_ANGLE, Math.max(START_ANGLE + pct * SWEEP, START_ANGLE + 1), RADIUS),
                        }}
                        transition={{ type: 'spring', stiffness: 40, damping: 15 }}
                    />

                    {/* Baseline marker */}
                    <line
                        x1={bTickX1} y1={bTickY1}
                        x2={bTickX2} y2={bTickY2}
                        stroke="#ffffff"
                        strokeWidth={2}
                        opacity={0.4}
                    />

                    {/* Needle */}
                    <motion.line
                        x1={CX} y1={CY}
                        x2={CX + (RADIUS - 20) * Math.cos(START_ANGLE * Math.PI / 180)}
                        y2={CY + (RADIUS - 20) * Math.sin(START_ANGLE * Math.PI / 180)}
                        stroke={zone.color}
                        strokeWidth={2.5}
                        strokeLinecap="round"
                        animate={{
                            x2: CX + (RADIUS - 20) * Math.cos(needleAngle * Math.PI / 180),
                            y2: CY + (RADIUS - 20) * Math.sin(needleAngle * Math.PI / 180),
                        }}
                        transition={{ type: 'spring', stiffness: 60, damping: 12 }}
                    />

                    {/* Center dot */}
                    <circle cx={CX} cy={CY} r={5} fill={zone.color} opacity={0.8} />
                    <circle cx={CX} cy={CY} r={2.5} fill="var(--bg-card, #161622)" />

                    {/* Value */}
                    <text
                        x={CX} y={CY + 30}
                        textAnchor="middle"
                        fill="var(--text-primary, #fafafa)"
                        fontSize="22"
                        fontWeight="800"
                        fontFamily="var(--font-mono)"
                    >
                        {velocity.toFixed(1)}
                    </text>
                    <text
                        x={CX} y={CY + 44}
                        textAnchor="middle"
                        fill="var(--text-muted, #666)"
                        fontSize="9"
                    >
                        trades / sec
                    </text>
                </svg>
            </div>

            {/* Status badge */}
            <div style={{ textAlign: 'center', marginTop: -4 }}>
                <motion.span
                    style={{
                        display: 'inline-block',
                        padding: '3px 12px',
                        borderRadius: 12,
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        letterSpacing: '0.06em',
                        background: `${zone.color}18`,
                        color: zone.color,
                        fontFamily: 'var(--font-mono)',
                    }}
                    animate={{ opacity: [0.7, 1, 0.7] }}
                    transition={{ duration: 2, repeat: Infinity }}
                >
                    {zone.label}
                </motion.span>
            </div>
        </div>
    );
}
