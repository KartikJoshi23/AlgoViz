"use client";

import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  TickMarkType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { fmtPrice } from "@/lib/format";
import { BAR_CAPACITY, SESSION_GAP_MS, useBars, useConnection, type BarCol } from "@/lib/store";
import type { RingTable } from "@/lib/store/rings";
import { CHART, COLORS, rgba } from "@/lib/theme";

const hms = (t: number, seconds: boolean) =>
  new Date(t * 1000).toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
  });

type LinePoint = { time: UTCTimestamp; value?: number };
type VolPoint = { time: UTCTimestamp; value?: number; color?: string };

const secs = (ms: number) => Math.floor(ms / 1000) as UTCTimestamp;
const gapText = (ms: number) => {
  const s = Math.round(ms / 1000);
  return `gap ${s >= 90 ? `${Math.round(s / 60)} min` : `${s} s`}`;
};

/** The chart points for bar `i`, and the length of the gap before it if the session broke there. */
function pointsAt(bars: RingTable<BarCol>, i: number) {
  const ts = bars.cols.ts_ms.at(i);
  const line = (col: "close" | "vwap" | "microprice"): LinePoint | null => {
    const v = bars.cols[col].at(i);
    return Number.isFinite(v) && v > 0 ? { time: secs(ts), value: v } : null;
  };
  const volume = bars.cols.volume.at(i);
  const buy = bars.cols.buy_volume.at(i);
  const vol: VolPoint | null = Number.isFinite(volume)
    ? { time: secs(ts), value: volume, color: rgba(buy >= volume / 2 ? COLORS.bid : COLORS.ask, 0.45) }
    : null;
  const prev = i > 0 ? bars.cols.ts_ms.at(i - 1) : Number.NaN;
  const gapMs = Number.isFinite(prev) && ts - prev > SESSION_GAP_MS ? ts - prev : 0;
  return { ts, mid: line("close"), vwap: line("vwap"), micro: line("microprice"), vol, gapMs };
}

/**
 * Mid (a line over a fading area) / VWAP / microprice over a volume histogram (each bar coloured by the
 * side that traded more) from the 1-second bar ring. Hydrates with setData on
 * (re)connect and appends with update() as bars arrive — no re-render per bar.
 * A session gap (feed outage or restart) breaks the lines — a whitespace point —
 * and is marked with its length. Axis and crosshair labels are in local time.
 */
export function PriceChart({ height = 300 }: { height?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<{
    mid: ISeriesApi<"Area">;
    vwap: ISeriesApi<"Line">;
    micro: ISeriesApi<"Line">;
    vol: ISeriesApi<"Histogram">;
    markers: ISeriesMarkersPluginApi<Time>;
  } | null>(null);
  const gaps = useRef<SeriesMarker<Time>[]>([]);
  const lastTs = useRef(0);
  const { bars, head } = useBars();
  const symbol = useConnection().symbol;

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
      },
      grid: { vertLines: { visible: false }, horzLines: { color: CHART.grid } },
      rightPriceScale: { borderColor: CHART.axis, scaleMargins: { top: 0.1, bottom: 0.24 } },
      localization: { timeFormatter: (t: UTCTimestamp) => hms(t, true), priceFormatter: (p: number) => fmtPrice(p, 2) },
      timeScale: {
        borderColor: CHART.axis,
        timeVisible: true,
        secondsVisible: true,
        rightOffset: 4,
        tickMarkFormatter: (t: UTCTimestamp, type: TickMarkType) =>
          type === TickMarkType.TimeWithSeconds
            ? hms(t, true)
            : type === TickMarkType.Time
              ? hms(t, false)
              : new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }),
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: CHART.crosshair, style: LineStyle.Solid, labelBackgroundColor: COLORS.raised },
        horzLine: { color: CHART.crosshair, style: LineStyle.Solid, labelBackgroundColor: COLORS.raised },
      },
      handleScroll: { vertTouchDrag: false },
    });
    const vol = c.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    c.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
    const mid = c.addSeries(AreaSeries, {
      lineColor: COLORS.mid,
      topColor: rgba(COLORS.mid, 0.2),
      bottomColor: rgba(COLORS.mid, 0),
      lineWidth: CHART.lineWidth,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      lastValueVisible: true,
      priceLineVisible: true,
      priceLineColor: COLORS.mid,
      priceLineStyle: LineStyle.Dotted,
      crosshairMarkerBorderColor: COLORS.panel,
      crosshairMarkerBorderWidth: 2,
    });
    const vwap = c.addSeries(LineSeries, {
      color: COLORS.accent,
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    const micro = c.addSeries(LineSeries, {
      color: COLORS.inkFaint,
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    series.current = { mid, vwap, micro, vol, markers: createSeriesMarkers(mid, []) };
    chart.current = c;
    lastTs.current = 0;
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, [height]);

  // reset on symbol switch
  useEffect(() => {
    lastTs.current = 0;
  }, [symbol]);

  useEffect(() => {
    const s = series.current;
    if (!s || bars.length === 0) return;
    const n = bars.length;
    const newest = bars.cols.ts_ms.at(n - 1);
    if (!Number.isFinite(newest)) return;
    const marker = (p: ReturnType<typeof pointsAt>): SeriesMarker<Time> => ({
      time: secs(p.ts),
      position: "aboveBar",
      shape: "square",
      color: COLORS.warning,
      text: gapText(p.gapMs),
      size: 0.6,
    });
    const hole = (p: ReturnType<typeof pointsAt>) => ({ time: secs(p.ts - 1000) });

    if (lastTs.current === 0 || newest < lastTs.current) {
      // full hydration
      const mids: LinePoint[] = [];
      const vwaps: LinePoint[] = [];
      const micros: LinePoint[] = [];
      const vols: VolPoint[] = [];
      gaps.current = [];
      for (let i = 0; i < n; i += 1) {
        const p = pointsAt(bars, i);
        if (!Number.isFinite(p.ts)) continue;
        if (p.gapMs) {
          for (const arr of [mids, vwaps, micros]) arr.push(hole(p));
          gaps.current.push(marker(p));
        }
        if (p.mid) mids.push(p.mid);
        if (p.vwap) vwaps.push(p.vwap);
        if (p.micro) micros.push(p.micro);
        if (p.vol) vols.push(p.vol);
      }
      const points = dedupe(mids);
      s.mid.setData(points);
      s.vwap.setData(dedupe(vwaps));
      s.micro.setData(dedupe(micros));
      s.vol.setData(dedupe(vols));
      s.markers.setMarkers(gaps.current);
      // Open on the ring's whole window, right-aligned: fitting a half-filled ring would fix a
      // wide bar spacing that new bars then keep, so a page opened just after a restart showed
      // seconds instead of minutes. New bars slide this window along at a constant spacing.
      chart.current?.timeScale().setVisibleLogicalRange({ from: points.length - BAR_CAPACITY, to: points.length + 3 });
      lastTs.current = newest;
      return;
    }
    // append bars newer than what we've drawn — update() must be called in
    // ascending time order, so find the first new index then walk forward
    let first = n;
    while (first > 0 && bars.cols.ts_ms.at(first - 1) > lastTs.current) first -= 1;
    for (let i = first; i < n; i += 1) {
      const p = pointsAt(bars, i);
      if (p.gapMs) {
        for (const line of [s.mid, s.vwap, s.micro]) line.update(hole(p));
        gaps.current = [...gaps.current, marker(p)];
        s.markers.setMarkers(gaps.current);
      }
      if (p.mid) s.mid.update(p.mid);
      if (p.vwap) s.vwap.update(p.vwap);
      if (p.micro) s.micro.update(p.micro);
      if (p.vol) s.vol.update(p.vol);
    }
    lastTs.current = newest;
  }, [bars, head]);

  // grows with the panel body; `height` is the floor
  return <div ref={host} className="w-full flex-1" style={{ minHeight: height }} aria-label="Price chart" role="img" />;
}

function dedupe<T extends { time: UTCTimestamp }>(points: T[]): T[] {
  const out: T[] = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (last && last.time === p.time) out[out.length - 1] = p;
    else if (!last || p.time > last.time) out.push(p);
  }
  return out;
}
