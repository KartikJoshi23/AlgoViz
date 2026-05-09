/**
 * AlgoViz — Spread Heatmap
 *
 * Time-series heatmap showing spread_bps values with color gradient.
 * Green (<2 bps) → Yellow (3-5 bps) → Red (>6 bps).
 */

import { useRef, useEffect, useCallback } from 'react';
import { useStore } from '../store';

function spreadColor(bps: number): string {
    if (bps <= 1.5) return '#10b981';
    if (bps <= 2.5) return '#34d399';
    if (bps <= 3.5) return '#a3e635';
    if (bps <= 4.5) return '#facc15';
    if (bps <= 5.5) return '#fb923c';
    if (bps <= 6.5) return '#f87171';
    return '#ef4444';
}

export function SpreadHeatmap() {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const spreadHistory = useStore((s) => s.spreadHistory);

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

        // Clear
        ctx.clearRect(0, 0, W, H);

        if (spreadHistory.length < 2) {
            ctx.fillStyle = 'var(--text-muted)';
            ctx.font = '12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Accumulating spread data…', W / 2, H / 2);
            return;
        }

        const data = spreadHistory.slice(-80);
        const cellW = W / data.length;
        const rows = 5;
        const cellH = H / rows;

        // Draw heatmap grid — each column is a time point
        // Rows represent different thresholds for visual density
        data.forEach((point, i) => {
            const bps = point.spread_bps;
            const color = spreadColor(bps);

            // Main cell
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.7;
            const intensity = Math.min(bps / 8, 1);
            const filledRows = Math.max(1, Math.round(intensity * rows));

            for (let r = 0; r < filledRows; r++) {
                const y = H - (r + 1) * cellH;
                const alpha = 0.3 + (r / rows) * 0.5;
                ctx.globalAlpha = alpha;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.roundRect(i * cellW + 0.5, y + 0.5, cellW - 1, cellH - 1, 2);
                ctx.fill();
            }
        });

        ctx.globalAlpha = 1;

        // Draw threshold lines
        const thresholds = [
            { bps: 2, label: '2bp', color: '#10b98180' },
            { bps: 6, label: '6bp', color: '#ef444480' },
        ];

        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        thresholds.forEach((t) => {
            const y = H - (t.bps / 8) * H;
            if (y > 0 && y < H) {
                ctx.strokeStyle = t.color;
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(W, y);
                ctx.stroke();

                ctx.fillStyle = t.color.slice(0, 7);
                ctx.font = '9px monospace';
                ctx.textAlign = 'right';
                ctx.fillText(t.label, W - 4, y - 3);
            }
        });
        ctx.setLineDash([]);

        // Current value label
        if (data.length > 0) {
            const last = data[data.length - 1];
            ctx.fillStyle = spreadColor(last.spread_bps);
            ctx.font = 'bold 11px monospace';
            ctx.textAlign = 'left';
            ctx.fillText(`${last.spread_bps.toFixed(1)} bps`, 6, 14);
        }
    }, [spreadHistory]);

    useEffect(() => {
        draw();
    }, [draw]);

    // Resize handler
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const observer = new ResizeObserver(() => draw());
        observer.observe(canvas.parentElement || canvas);
        return () => observer.disconnect();
    }, [draw]);

    return (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
            <div className="card-title" style={{ marginBottom: 12 }}>🌡️ Spread Heatmap</div>
            <canvas
                ref={canvasRef}
                style={{
                    width: '100%',
                    height: 140,
                    borderRadius: 8,
                    background: 'var(--bg-secondary)',
                }}
            />
            <div style={{
                display: 'flex', justifyContent: 'space-between',
                marginTop: 6, fontSize: '0.65rem', color: 'var(--text-muted)',
            }}>
                <span>← older</span>
                <div style={{ display: 'flex', gap: 8 }}>
                    <span style={{ color: '#10b981' }}>■ tight</span>
                    <span style={{ color: '#facc15' }}>■ normal</span>
                    <span style={{ color: '#ef4444' }}>■ wide</span>
                </div>
                <span>newer →</span>
            </div>
        </div>
    );
}
