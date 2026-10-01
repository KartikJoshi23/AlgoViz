"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fmtPrice, fmtQty } from "@/lib/format";
import { useConnection, useStore } from "@/lib/store";
import type { HeatRing } from "@/lib/store/heat";
import { CHART, COLORS, rgba } from "@/lib/theme";

import { crisp, prepareCanvas, useWidth } from "./canvas";

const AXIS_W = 76; // right gutter: price axis
const AXIS_H = 22; // bottom gutter: time axis
const ROWS = 240; // raster rows across the visible price span
const PRICE_TICKS = 6;
const TIME_TICKS = 6;
const STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000];

interface View {
  center: number; // price at the vertical middle
  halfBps: number; // half the visible span, bps of `center`
  n: number; // columns written (≤ capacity)
}

function rgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/**
 * One side's sequential ramp as packed RGBA: transparent at zero, dim for
 * ordinary levels, the full side colour by ~70 % of the reference size and a
 * light tint above that, so walls stand out from the background book.
 */
function ramp(hex: string): Uint32Array {
  const [r, g, b] = rgb(hex);
  const out = new Uint32Array(256);
  for (let i = 1; i < 256; i += 1) {
    const t = i / 255;
    const k = 0.38 + 0.62 * Math.min(1, t / 0.7);
    const w = Math.max(0, (t - 0.7) / 0.3) * 0.55;
    const cr = r * k + (255 - r * k) * w;
    const cg = g * k + (255 - g * k) * w;
    const cb = b * k + (255 - b * k) * w;
    const a = Math.min(1, 0.1 + t * 1.3);
    out[i] = ((Math.round(a * 255) << 24) | (Math.round(cb) << 16) | (Math.round(cg) << 8) | Math.round(cr)) >>> 0;
  }
  return out;
}

const niceStep = (span: number, ticks: number) => STEPS.find((s) => span / s <= ticks) ?? STEPS[STEPS.length - 1]!;

/** Fills the raster (one pixel per column × row) and returns the view it was drawn for. */
function rasterize(heat: HeatRing, img: ImageData, prev: View | null, luts: [Uint32Array, Uint32Array]): View | null {
  const n = Math.min(heat.head, heat.capacity);
  const buf = new Uint32Array(img.data.buffer);
  buf.fill(0);
  if (n === 0) return null;
  const newest = heat.slot(0);
  const m0 = heat.mid[newest]!;
  // the centre follows the mid, eased so the axis doesn't jitter frame to frame
  const center = prev && Math.abs(prev.center / m0 - 1) < 0.01 ? prev.center + 0.25 * (m0 - prev.center) : m0;
  // the span is the current band, widened to follow the recent price trail — but only so
  // far: past 2.5 bands the resting liquidity would shrink to a sliver, so older prices
  // scroll out of view instead (as on a trading heatmap)
  let dev = 0;
  for (let age = 0; age < n; age += 1) dev = Math.max(dev, Math.abs(heat.mid[heat.slot(age)]! / center - 1));
  const band = heat.bandBps[newest]!;
  const target = Math.max(1.2 * band, Math.min(dev * 10_000 * 1.05, 2.5 * band));
  const halfBps = prev ? prev.halfBps + 0.15 * (target - prev.halfBps) : target;

  const cols = heat.capacity;
  const per = heat.perSide;
  const peak = Math.max(heat.peak, 1e-9);
  const rowScale = new Float64Array(ROWS); // price / centre for each raster row
  for (let r = 0; r < ROWS; r += 1) rowScale[r] = 1 + (halfBps * (1 - (2 * (r + 0.5)) / ROWS)) / 10_000;
  const [bidLut, askLut] = luts;
  for (let age = 0; age < n; age += 1) {
    const s = heat.slot(age);
    const x = cols - 1 - age;
    const ratio = center / heat.mid[s]!;
    const step = heat.bandBps[s]! / per;
    const base = s * per * 2;
    for (let r = 0; r < ROWS; r += 1) {
      const off = (ratio * rowScale[r]! - 1) * 10_000; // bps from this column's mid
      // interpolate between bin centres: bins are mid-relative, so without this a resting
      // level hops between neighbouring bins as the mid moves and the map speckles
      const pos = Math.abs(off) / step - 0.5;
      if (pos >= per - 0.5) continue;
      const i0 = Math.max(0, Math.floor(pos));
      const i1 = Math.min(per - 1, i0 + 1);
      const f = Math.min(1, Math.max(0, pos - i0));
      const side = off < 0 ? base : base + per;
      const q = heat.qty[side + i0]! * (1 - f) + heat.qty[side + i1]! * f;
      if (q <= 0) continue;
      const idx = Math.min(255, Math.floor((q / peak) ** 0.65 * 255));
      buf[r * cols + x] = (off < 0 ? bidLut : askLut)[idx]!;
    }
  }
  return { center, halfBps, n };
}

/**
 * Price × time liquidity heatmap, Bookmap-style: each column is one book frame,
 * each cell the quantity resting in that price bin, coloured on the side's
 * ramp. The mid trail and trade bubbles (sized by traded quantity) are drawn
 * over it, so price can be seen moving through — or bouncing off — resting
 * liquidity. The raster is rebuilt per book frame; hover only re-composites.
 */
export function Heatmap({ height = 400 }: { height?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [host, width] = useWidth<HTMLDivElement>();
  const heat = useStore((s) => s.heat);
  const bookHead = useStore((s) => s.bookHead);
  const subscribed = useStore((s) => s.prefs.bookSubscribed);
  const base = useConnection().symbol.replace(/USDT$/, "");
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);

  const raster = useRef<{ canvas: HTMLCanvasElement; img: ImageData; luts: [Uint32Array, Uint32Array] } | null>(null);
  const view = useRef<View | null>(null);
  const priceLabels = useRef<(HTMLSpanElement | null)[]>([]);
  const timeLabels = useRef<(HTMLSpanElement | null)[]>([]);
  const midTag = useRef<HTMLSpanElement>(null);
  const fillNote = useRef<HTMLSpanElement>(null);

  const plotW = Math.max(0, width - AXIS_W);
  const plotH = Math.max(0, height - AXIS_H);

  const composite = useCallback(() => {
    const el = canvas.current;
    const r = raster.current;
    const v = view.current;
    if (!el || !r || width === 0) return;
    const ctx = prepareCanvas(el, width, height);
    if (!ctx) return;
    const priceTags = priceLabels.current;
    const timeTags = timeLabels.current;
    if (!v) {
      for (const t of [...priceTags, ...timeTags, midTag.current, fillNote.current]) if (t) t.style.display = "none";
      return;
    }
    const cols = heat.capacity;
    const xOf = (age: number) => ((cols - 1 - age + 0.5) / cols) * plotW;
    const yOf = (price: number) => plotH * (0.5 - ((price / v.center - 1) * 10_000) / (2 * v.halfBps));

    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(r.canvas, 0, 0, plotW, plotH);

    // price grid + axis labels (a tick next to the live mid tag yields to it)
    const mid = heat.mid[heat.slot(0)]!;
    const midY = yOf(mid);
    const lo = v.center * (1 - v.halfBps / 10_000);
    const hi = v.center * (1 + v.halfBps / 10_000);
    const step = niceStep(hi - lo, PRICE_TICKS);
    const decimals = step < 1 ? 2 : 0;
    ctx.strokeStyle = CHART.grid;
    ctx.lineWidth = 1;
    let k = 0;
    for (let p = Math.ceil(lo / step) * step; p <= hi && k < priceTags.length; p += step, k += 1) {
      const y = yOf(p);
      ctx.beginPath();
      ctx.moveTo(0, crisp(y));
      ctx.lineTo(plotW, crisp(y));
      ctx.stroke();
      const tag = priceTags[k];
      if (tag) {
        tag.style.display = Math.abs(y - midY) < 14 ? "none" : "";
        tag.style.top = `${y}px`;
        tag.textContent = fmtPrice(p, decimals as 0 | 2);
      }
    }
    for (; k < priceTags.length; k += 1) if (priceTags[k]) priceTags[k]!.style.display = "none";
    ctx.strokeStyle = CHART.axis;
    ctx.beginPath();
    ctx.moveTo(crisp(plotW), 0);
    ctx.lineTo(crisp(plotW), plotH);
    ctx.moveTo(0, crisp(plotH));
    ctx.lineTo(plotW, crisp(plotH));
    ctx.stroke();

    // time axis: a tick every 30 s of event time back from the newest frame (60 s when narrow)
    const every = plotW < 480 ? 60 : 30;
    const newestTs = heat.ts[heat.slot(0)]!;
    let t = 0;
    let nextMark = every;
    for (let age = 0; age < v.n && t < timeTags.length; age += 1) {
      const dt = (newestTs - heat.ts[heat.slot(age)]!) / 1000;
      if (age === 0 || dt >= nextMark) {
        const tag = timeTags[t];
        if (tag) {
          tag.style.display = "";
          tag.style.left = `${xOf(age)}px`;
          tag.textContent =
            age === 0
              ? "now"
              : `−${dt >= 60 ? `${Math.floor(dt / 60)}:${String(Math.round(dt % 60)).padStart(2, "0")}` : `${Math.round(dt)} s`}`;
        }
        if (age > 0) nextMark += every;
        t += 1;
      }
    }
    for (; t < timeTags.length; t += 1) if (timeTags[t]) timeTags[t]!.style.display = "none";
    if (fillNote.current) {
      fillNote.current.style.display = v.n < cols ? "" : "none";
      fillNote.current.style.right = `${width - xOf(v.n - 1) + 10}px`;
    }

    // mid trail
    ctx.beginPath();
    for (let age = v.n - 1; age >= 0; age -= 1) {
      const x = xOf(age);
      const y = yOf(heat.mid[heat.slot(age)]!);
      if (age === v.n - 1) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = COLORS.mid;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.stroke();
    if (midTag.current) {
      midTag.current.style.top = `${midY}px`;
      midTag.current.textContent = fmtPrice(mid, 2);
    }

    // trade bubbles: area ∝ traded quantity, at the column's VWAP per side
    const flow = Math.max(heat.flow, 1e-9);
    const bubble = (qty: number, notional: number, age: number, color: string) => {
      if (qty <= 0) return;
      const radius = Math.min(9, 2.2 * Math.sqrt(qty / flow));
      if (radius < 1.2) return;
      ctx.beginPath();
      ctx.arc(xOf(age), yOf(notional / qty), radius, 0, Math.PI * 2);
      ctx.fillStyle = rgba(color, 0.8);
      ctx.fill();
      ctx.strokeStyle = COLORS.page;
      ctx.lineWidth = 1;
      ctx.stroke();
    };
    for (let age = v.n - 1; age >= 0; age -= 1) {
      const s = heat.slot(age);
      bubble(heat.buyQty[s]!, heat.buyNotional[s]!, age, COLORS.bid);
      bubble(heat.sellQty[s]!, heat.sellNotional[s]!, age, COLORS.ask);
    }

    if (hover && hover.x < plotW && hover.y < plotH) {
      ctx.strokeStyle = CHART.crosshair;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(crisp(hover.x), 0);
      ctx.lineTo(crisp(hover.x), plotH);
      ctx.moveTo(0, crisp(hover.y));
      ctx.lineTo(plotW, crisp(hover.y));
      ctx.stroke();
    }
  }, [heat, width, height, plotW, plotH, hover]);

  // rebuild the raster once per book frame (`bookHead`; the ring is mutated in place)…
  useEffect(() => {
    if (!raster.current) {
      const c = document.createElement("canvas");
      c.width = heat.capacity;
      c.height = ROWS;
      const ctx = c.getContext("2d");
      if (!ctx) return;
      raster.current = { canvas: c, img: ctx.createImageData(heat.capacity, ROWS), luts: [ramp(COLORS.bid), ramp(COLORS.ask)] };
    }
    const r = raster.current;
    view.current = rasterize(heat, r.img, view.current, r.luts);
    r.canvas.getContext("2d")?.putImageData(r.img, 0, 0);
  }, [heat, bookHead]);

  // …and composite after it, on resize and under the pointer
  useEffect(() => composite(), [composite, bookHead]);

  // the store's head, not the ring, decides emptiness: hydration must see the server's state
  const empty = bookHead === 0 || heat.head === 0;
  const v = empty ? null : view.current;
  const readout = (() => {
    if (!hover || !v || hover.x >= plotW || hover.y >= plotH) return null;
    const age = heat.capacity - 1 - Math.floor((hover.x / plotW) * heat.capacity);
    const s = heat.slot(age);
    if (s < 0) return null;
    const price = v.center * (1 + ((0.5 - hover.y / plotH) * 2 * v.halfBps) / 10_000);
    const off = (price / heat.mid[s]! - 1) * 10_000;
    const i = Math.floor(Math.abs(off) / (heat.bandBps[s]! / heat.perSide));
    const qty = i < heat.perSide ? heat.qty[s * heat.perSide * 2 + (off < 0 ? i : heat.perSide + i)]! : Number.NaN;
    return {
      price,
      side: off < 0 ? "bid" : "ask",
      qty,
      ago: (heat.ts[heat.slot(0)]! - heat.ts[s]!) / 1000,
      bought: heat.buyQty[s]!,
      sold: heat.sellQty[s]!,
    } as const;
  })();

  return (
    <div
      ref={host}
      className="relative w-full select-none"
      style={{ height }}
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setHover({ x: e.clientX - r.left, y: e.clientY - r.top });
      }}
      onPointerLeave={() => setHover(null)}
    >
      <canvas
        ref={canvas}
        className="absolute inset-0 block h-full w-full"
        role="img"
        aria-label={`Liquidity heatmap: resting size by price over the last 3 minutes, with trades${v ? `; mid ${fmtPrice(heat.mid[heat.slot(0)], 2)}` : ""}`}
      />
      <div className="num pointer-events-none absolute inset-y-0 right-0 text-caption text-ink-faint" style={{ width: AXIS_W }} aria-hidden>
        {Array.from({ length: PRICE_TICKS + 1 }, (_, i) => (
          <span
            key={i}
            ref={(n) => {
              priceLabels.current[i] = n;
            }}
            className="absolute left-2 -translate-y-1/2"
            style={{ display: "none" }}
          />
        ))}
        <span
          ref={midTag}
          className="absolute left-1 -translate-y-1/2 rounded-sm bg-mid px-1 font-medium text-page"
          style={{ top: -100 }}
        />
      </div>
      <div
        className="num pointer-events-none absolute inset-x-0 bottom-0 text-caption text-ink-faint"
        style={{ height: AXIS_H }}
        aria-hidden
      >
        {Array.from({ length: TIME_TICKS + 1 }, (_, i) => (
          <span
            key={i}
            ref={(n) => {
              timeLabels.current[i] = n;
            }}
            className="absolute top-1 -translate-x-1/2 whitespace-nowrap"
            style={{ display: "none" }}
          />
        ))}
      </div>
      <span
        ref={fillNote}
        className="pointer-events-none absolute top-1/2 -translate-y-1/2 text-caption text-ink-faint"
        style={{ display: "none" }}
      >
        history fills in over 3 minutes →
      </span>
      {empty && (
        <span className="absolute inset-0 grid place-items-center text-meta text-ink-faint">
          {subscribed ? "Waiting for the first book frame…" : "Book stream paused — resume it to see liquidity"}
        </span>
      )}
      {readout && hover && (
        <div
          className="float pointer-events-none absolute z-10 rounded-md px-2 py-1 text-caption"
          style={{
            top: Math.min(hover.y + 12, height - 70),
            ...(hover.x > plotW / 2 ? { right: width - hover.x + 12 } : { left: hover.x + 12 }),
          }}
        >
          <div className="num text-ink">
            {fmtPrice(readout.price, 2)}{" "}
            <span className="text-ink-faint">{readout.ago < 0.1 ? "now" : `${readout.ago.toFixed(1)} s ago`}</span>
          </div>
          <div className="num flex items-center gap-1.5 text-ink-muted">
            <span className={`h-1.5 w-1.5 rounded-full ${readout.side === "bid" ? "bg-bid" : "bg-ask"}`} aria-hidden />
            {Number.isFinite(readout.qty) ? `${fmtQty(readout.qty, 3)} ${base} resting` : "outside the book band"}
          </div>
          {(readout.bought > 0 || readout.sold > 0) && (
            <div className="num text-ink-faint">
              traded {fmtQty(readout.bought, 3)} bought · {fmtQty(readout.sold, 3)} sold
            </div>
          )}
        </div>
      )}
    </div>
  );
}
