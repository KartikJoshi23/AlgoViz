"use client";

import { AreaSeries, ColorType, CrosshairMode, LineStyle, TickMarkType, createChart, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";

import { fmtPrice } from "@/lib/format";
import { CHART, COLORS, rgba } from "@/lib/theme";

const hm = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
const hms = (t: number) =>
  new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

/**
 * A backtest's equity curve and its drawdown in two panes on one time axis —
 * each with its own scale, rather than two scales on one plot. The dotted
 * level is the starting capital.
 */
export function EquityChart({ curve, height = 300, initialCapital }: { curve: number[][]; height?: number; initialCapital: number }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const c = createChart(el, {
      height,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: CHART.text,
        fontFamily: CHART.fontFamily,
        fontSize: 11,
        attributionLogo: false,
        panes: { separatorColor: CHART.axis, separatorHoverColor: rgba(COLORS.ink, 0.06), enableResize: false },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: CHART.grid } },
      rightPriceScale: { borderColor: CHART.axis, scaleMargins: { top: 0.1, bottom: 0.08 } },
      localization: { timeFormatter: (t: UTCTimestamp) => hms(t) },
      timeScale: {
        borderColor: CHART.axis,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (t: UTCTimestamp, type: TickMarkType) =>
          type >= TickMarkType.Time ? hm(t) : new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }),
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: CHART.crosshair, style: LineStyle.Solid, labelBackgroundColor: COLORS.raised },
        horzLine: { color: CHART.crosshair, style: LineStyle.Solid, labelBackgroundColor: COLORS.raised },
      },
      handleScroll: { vertTouchDrag: false },
    });
    const equity = c.addSeries(
      AreaSeries,
      {
        lineColor: COLORS.accent,
        topColor: rgba(COLORS.accent, CHART.areaAlpha),
        bottomColor: rgba(COLORS.accent, 0),
        lineWidth: CHART.lineWidth,
        priceFormat: { type: "custom", formatter: (v: number) => `$${fmtPrice(v, 2)}` },
        lastValueVisible: true,
        priceLineVisible: false,
      },
      0,
    );
    const drawdown = c.addSeries(
      AreaSeries,
      {
        lineColor: COLORS.inkMuted,
        topColor: rgba(COLORS.inkMuted, 0),
        bottomColor: rgba(COLORS.inkMuted, CHART.areaAlpha),
        invertFilledArea: true,
        lineWidth: 1,
        priceFormat: { type: "custom", formatter: (v: number) => `${v.toFixed(2)}%` },
        lastValueVisible: false,
        priceLineVisible: false,
      },
      1,
    );
    equity.createPriceLine({
      price: initialCapital,
      color: rgba(COLORS.ink, 0.35),
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: false,
      title: "start",
    });
    const [top, bottom] = c.panes();
    top?.setStretchFactor(0.72);
    bottom?.setStretchFactor(0.28);

    const eq: { time: UTCTimestamp; value: number }[] = [];
    const dd: { time: UTCTimestamp; value: number }[] = [];
    let last = -1;
    for (const row of curve) {
      const t = Math.floor((row[0] ?? 0) / 1000);
      if (t <= last) continue;
      last = t;
      eq.push({ time: t as UTCTimestamp, value: row[1] ?? 0 });
      dd.push({ time: t as UTCTimestamp, value: -(row[2] ?? 0) });
    }
    equity.setData(eq);
    drawdown.setData(dd);
    c.timeScale().fitContent();
    return () => c.remove();
  }, [curve, height, initialCapital]);

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center gap-x-3 text-meta text-ink-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded-full bg-accent" aria-hidden /> equity
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded-full bg-ink-muted" aria-hidden /> drawdown, lower pane
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3.5 border-t border-dotted border-ink-muted" aria-hidden /> starting capital
        </span>
      </div>
      <div ref={host} className="w-full" style={{ height }} role="img" aria-label="Equity and drawdown" />
    </div>
  );
}
