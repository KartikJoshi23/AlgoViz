/**
 * AlgoViz — Price Chart (TradingView Lightweight Charts)
 *
 * Real-time price line chart with VWAP overlay.
 */

import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi, ColorType } from 'lightweight-charts';
import { useStore } from '../store';

export function PriceChart() {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const priceSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const priceHistory = useStore((s) => s.priceHistory);

    // Create chart once
    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            width: containerRef.current.clientWidth,
            height: 320,
            layout: {
                background: { type: ColorType.Solid, color: '#161622' },
                textColor: '#8888aa',
                fontSize: 12,
                fontFamily: "'Inter', sans-serif",
            },
            grid: {
                vertLines: { color: 'rgba(35,35,54,0.5)' },
                horzLines: { color: 'rgba(35,35,54,0.5)' },
            },
            rightPriceScale: {
                borderColor: '#232336',
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            timeScale: {
                borderColor: '#232336',
                timeVisible: true,
                secondsVisible: true,
            },
            crosshair: {
                vertLine: { color: '#06b6d4', width: 1, style: 2, labelBackgroundColor: '#06b6d4' },
                horzLine: { color: '#06b6d4', width: 1, style: 2, labelBackgroundColor: '#06b6d4' },
            },
        });

        const priceSeries = chart.addLineSeries({
            color: '#06b6d4',
            lineWidth: 2,
            title: 'Price',
            priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
        });

        const vwapSeries = chart.addLineSeries({
            color: '#8b5cf6',
            lineWidth: 1,
            lineStyle: 2,
            title: 'VWAP',
            priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
        });

        chartRef.current = chart;
        priceSeriesRef.current = priceSeries;
        vwapSeriesRef.current = vwapSeries;

        // Resize observer
        const observer = new ResizeObserver((entries) => {
            const { width } = entries[0].contentRect;
            chart.applyOptions({ width });
        });
        observer.observe(containerRef.current);

        return () => {
            observer.disconnect();
            chart.remove();
        };
    }, []);

    // Update data
    useEffect(() => {
        if (!priceSeriesRef.current || !vwapSeriesRef.current) return;
        if (priceHistory.length === 0) return;

        const priceData = priceHistory
            .filter((p) => p.price > 0)
            .map((p) => ({
                time: Math.floor(new Date(p.timestamp).getTime() / 1000) as any,
                value: p.price,
            }));

        const vwapData = priceHistory
            .filter((p) => p.vwap > 0)
            .map((p) => ({
                time: Math.floor(new Date(p.timestamp).getTime() / 1000) as any,
                value: p.vwap,
            }));

        if (priceData.length > 0) {
            priceSeriesRef.current.setData(priceData);
        }
        if (vwapData.length > 0) {
            vwapSeriesRef.current.setData(vwapData);
        }
    }, [priceHistory]);

    return (
        <div className="chart-container">
            <div className="chart-title">
                <span>📈</span> Live Price & VWAP
            </div>
            <div ref={containerRef} style={{ borderRadius: '8px', overflow: 'hidden' }} />
        </div>
    );
}
