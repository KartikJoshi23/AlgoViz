/**
 * AlgoViz — Volatility Chart
 *
 * Area chart with dynamic regime bands and gradient fills.
 * Shows volatility_bps timeline with Low/Medium/High zones.
 */

import { useRef, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../store';

function volatilityColor(bps: number): string {
    if (bps > 20) return '#ef4444';
    if (bps > 10) return '#f59e0b';
    return '#10b981';
}

function regimeLabel(bps: number): string {
    if (bps > 20) return 'HIGH VOLATILITY';
    if (bps > 10) return 'MODERATE';
    return 'LOW VOLATILITY';
}

export function VolatilityChart() {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const volatilityHistory = useStore((s) => s.volatilityHistory);
    const currentVol = useStore((s) => s.features.volatility_bps);

    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);

        const W = rect.width;
        const H = rect.height;
        const PAD_TOP = 10;
        const PAD_BOT = 20;
        const drawH = H - PAD_TOP - PAD_BOT;

        ctx.clearRect(0, 0, W, H);

        if (volatilityHistory.length < 3) {
            ctx.fillStyle = '#666';
            ctx.font = '12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Collecting volatility data…', W / 2, H / 2);
            return;
        }

        const data = volatilityHistory.slice(-80);
        const maxVal = Math.max(30, ...data.map((d) => d.volatility_bps)) * 1.1;

        const xStep = W / (data.length - 1);
        const yScale = (v: number) => PAD_TOP + drawH - (v / maxVal) * drawH;

        // Regime bands
        const bands = [
            { from: 0, to: 10, color: 'rgba(16,185,129,0.06)', label: 'Low' },
            { from: 10, to: 20, color: 'rgba(245,158,11,0.06)', label: 'Med' },
            { from: 20, to: maxVal, color: 'rgba(239,68,68,0.06)', label: 'High' },
        ];

        bands.forEach((b) => {
            const y1 = yScale(Math.min(b.to, maxVal));
            const y2 = yScale(b.from);
            ctx.fillStyle = b.color;
            ctx.fillRect(0, y1, W, y2 - y1);

            // Band label
            ctx.fillStyle = b.color.replace('0.06', '0.4');
            ctx.font = '9px monospace';
            ctx.textAlign = 'right';
            ctx.fillText(b.label, W - 4, y1 + 11);
        });

        // Threshold lines
        [10, 20].forEach((t) => {
            const y = yScale(t);
            ctx.setLineDash([3, 3]);
            ctx.strokeStyle = t === 20 ? 'rgba(239,68,68,0.3)' : 'rgba(245,158,11,0.25)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(W, y);
            ctx.stroke();
        });
        ctx.setLineDash([]);

        // Build path
        const points: [number, number][] = data.map((d, i) => [i * xStep, yScale(d.volatility_bps)]);

        // Gradient fill under curve
        const gradient = ctx.createLinearGradient(0, PAD_TOP, 0, H - PAD_BOT);
        const lastColor = volatilityColor(data[data.length - 1].volatility_bps);
        gradient.addColorStop(0, lastColor + '50');
        gradient.addColorStop(1, lastColor + '05');

        ctx.beginPath();
        ctx.moveTo(points[0][0], H - PAD_BOT);

        // Smooth curve using bezier
        points.forEach(([x, y], i) => {
            if (i === 0) {
                ctx.lineTo(x, y);
            } else {
                const prev = points[i - 1];
                const cpx = (prev[0] + x) / 2;
                ctx.bezierCurveTo(cpx, prev[1], cpx, y, x, y);
            }
        });

        ctx.lineTo(points[points.length - 1][0], H - PAD_BOT);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();

        // Line
        ctx.beginPath();
        points.forEach(([x, y], i) => {
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                const prev = points[i - 1];
                const cpx = (prev[0] + x) / 2;
                ctx.bezierCurveTo(cpx, prev[1], cpx, y, x, y);
            }
        });
        ctx.strokeStyle = lastColor;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Current value dot
        if (points.length > 0) {
            const [lx, ly] = points[points.length - 1];
            ctx.beginPath();
            ctx.arc(lx, ly, 4, 0, Math.PI * 2);
            ctx.fillStyle = lastColor;
            ctx.fill();
            ctx.beginPath();
            ctx.arc(lx, ly, 7, 0, Math.PI * 2);
            ctx.strokeStyle = lastColor + '40';
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        // Y-axis labels
        ctx.fillStyle = '#666';
        ctx.font = '9px monospace';
        ctx.textAlign = 'left';
        [0, 10, 20, 30].forEach((v) => {
            if (v <= maxVal) {
                ctx.fillText(`${v}`, 4, yScale(v) - 2);
            }
        });
    }, [volatilityHistory]);

    useEffect(() => {
        draw();
    }, [draw]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const observer = new ResizeObserver(() => draw());
        observer.observe(canvas.parentElement || canvas);
        return () => observer.disconnect();
    }, [draw]);

    const color = volatilityColor(currentVol);

    return (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
            <div className="card-header">
                <div className="card-title">📉 Volatility Monitor</div>
                <motion.span
                    className="badge"
                    style={{
                        background: `${color}18`,
                        color,
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                    }}
                    animate={{ opacity: [0.7, 1, 0.7] }}
                    transition={{ duration: 2, repeat: Infinity }}
                >
                    {currentVol.toFixed(1)} bps · {regimeLabel(currentVol)}
                </motion.span>
            </div>
            <canvas
                ref={canvasRef}
                style={{
                    width: '100%',
                    height: 180,
                    borderRadius: 8,
                    marginTop: 8,
                }}
            />
        </div>
    );
}
