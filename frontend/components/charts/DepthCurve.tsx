"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { fmtPrice, fmtQty, fmtSigned } from "@/lib/format";
import { useBook, useConnection, useStore } from "@/lib/store";
import { CHART, COLORS, areaGradient, rgba } from "@/lib/theme";

import { crisp, prepareCanvas, useWidth } from "./canvas";

const PAD_T = 22;
const PAD_B = 22;
// The y-scale stops at this multiple of the thinner side's depth, so one wall can't flatten the other side.
const CLAMP = 2.5;

type Step = [price: number, cumulative: number];

/** Depth resting between the touch and `price` on one side (steps run from the touch outward). */
function depthAt(steps: Step[], price: number, side: "bid" | "ask"): number {
  let cum = 0;
  for (const [p, c] of steps) {
    if (side === "bid" ? p < price : p > price) break;
    cum = c;
  }
  return cum;
}

/**
 * Cumulative depth curve (2D) from the server's depth profile — built from the
 * full local book, so it spans the whole adaptive band even where the top-N
 * level list covers a fraction of a basis point (BTC's 0.01 tick). The scale
 * is symmetric (±band around mid) with the y-axis clamped at 2.5× the thinner
 * side, so a wall on one side never flattens the other (a clipped side shows
 * its total). Bids step left of mid, asks right, each a 2px line over a light
 * wash; mid and microprice are hairline guides; labels and hover are DOM.
 */
export function DepthCurve({ height = 220 }: { height?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [host, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const book = useBook();
  const subscribed = useStore((s) => s.prefs.bookSubscribed);
  const base = useConnection().symbol.replace(/USDT$/, "");

  const geo = useMemo(() => {
    const p = book?.profile;
    if (!book || !p || p.bins === 0 || !(book.mid > 0)) return null;
    const mid = book.mid;
    const band = p.band_bps;
    const step = band / p.bins;
    // bin i holds everything within (i + 1) steps of mid; its step starts at the bin's inner edge
    const at = (i: number, sign: 1 | -1) => mid * (1 + (sign * i * step) / 10_000);
    const bids: Step[] = p.bids.map((c, i) => [at(i, -1), c]);
    const asks: Step[] = p.asks.map((c, i) => [at(i, 1), c]);
    const bidTotal = bids.at(-1)?.[1] ?? 0;
    const askTotal = asks.at(-1)?.[1] ?? 0;
    const thin = Math.min(bidTotal, askTotal);
    const maxCum = Math.max(thin > 0 ? Math.min(Math.max(bidTotal, askTotal), thin * CLAMP) : Math.max(bidTotal, askTotal), 1e-9);
    return { mid, micro: book.microprice, band, lo: at(p.bins, -1), hi: at(p.bins, 1), bids, asks, bidTotal, askTotal, maxCum };
  }, [book]);

  useEffect(() => {
    const el = canvas.current;
    if (!el || width === 0) return;
    const ctx = prepareCanvas(el, width, height);
    if (!ctx || !geo) return;
    const W = width;
    const H = height;
    const x = (p: number) => ((p - geo.lo) / (geo.hi - geo.lo)) * W;
    const y = (c: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - Math.min(c, geo.maxCum) / geo.maxCum);

    ctx.strokeStyle = CHART.grid;
    ctx.lineWidth = 1;
    for (const f of [0.25, 0.5, 0.75]) {
      ctx.beginPath();
      ctx.moveTo(0, crisp(y(geo.maxCum * f)));
      ctx.lineTo(W, crisp(y(geo.maxCum * f)));
      ctx.stroke();
    }
    ctx.strokeStyle = CHART.axis;
    ctx.beginPath();
    ctx.moveTo(0, crisp(y(0)));
    ctx.lineTo(W, crisp(y(0)));
    ctx.stroke();

    const drawSide = (steps: Step[], color: string, edge: number) => {
      if (steps.length === 0) return;
      ctx.beginPath();
      ctx.moveTo(x(geo.mid), y(0));
      let prevY = y(0);
      for (const [p, c] of steps) {
        ctx.lineTo(x(p), prevY);
        ctx.lineTo(x(p), y(c));
        prevY = y(c);
      }
      ctx.lineTo(edge, prevY);
      ctx.strokeStyle = color;
      ctx.lineWidth = CHART.lineWidth;
      ctx.lineJoin = "round";
      ctx.stroke();
      ctx.lineTo(edge, y(0));
      ctx.closePath();
      ctx.fillStyle = areaGradient(ctx, color, PAD_T, y(0));
      ctx.fill();
    };
    drawSide(geo.bids, COLORS.bid, 0);
    drawSide(geo.asks, COLORS.ask, W);

    const guide = (p: number, color: string) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(crisp(x(p)), PAD_T - 4);
      ctx.lineTo(crisp(x(p)), H - PAD_B);
      ctx.stroke();
    };
    guide(geo.mid, rgba(COLORS.mid, 0.8));
    if (Math.abs(geo.micro - geo.mid) > 1e-9) guide(geo.micro, COLORS.inkFaint);

    if (hover != null) {
      ctx.strokeStyle = CHART.crosshair;
      ctx.beginPath();
      ctx.moveTo(crisp(hover * W), PAD_T - 4);
      ctx.lineTo(crisp(hover * W), H - PAD_B);
      ctx.stroke();
    }
  }, [geo, width, height, hover]);

  const readout = useMemo(() => {
    if (!geo || hover == null) return null;
    const price = geo.lo + hover * (geo.hi - geo.lo);
    const side = price < geo.mid ? "bid" : "ask";
    const depth = depthAt(side === "bid" ? geo.bids : geo.asks, price, side);
    return { price, side, depth, bps: (price / geo.mid - 1) * 10_000 } as const;
  }, [geo, hover]);

  const at = (p: number) => (geo ? ((p - geo.lo) / (geo.hi - geo.lo)) * 100 : 50);
  const hoverX = hover == null ? 0 : hover * width;

  return (
    <div
      ref={host}
      className="relative w-full"
      style={{ height }}
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setHover(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)));
      }}
      onPointerLeave={() => setHover(null)}
    >
      <canvas
        ref={canvas}
        className="absolute inset-0 block h-full w-full"
        role="img"
        aria-label={geo ? `Cumulative depth within ±${geo.band.toFixed(1)} bps of mid ${fmtPrice(geo.mid, 2)}` : "Cumulative depth"}
      />
      {geo ? (
        <>
          <span
            className="num pointer-events-none absolute top-0 -translate-x-1/2 whitespace-nowrap text-caption text-mid-text"
            style={{ left: `${at(geo.mid)}%` }}
          >
            mid {fmtPrice(geo.mid, 2)}
          </span>
          {geo.bidTotal > geo.maxCum && (
            <span className="num pointer-events-none absolute left-0 top-0 text-caption text-ink-faint">
              ↑ {fmtQty(geo.bidTotal, 1)} {base}
            </span>
          )}
          {geo.askTotal > geo.maxCum && (
            <span className="num pointer-events-none absolute right-0 top-0 text-caption text-ink-faint">
              ↑ {fmtQty(geo.askTotal, 1)} {base}
            </span>
          )}
          <span className="num pointer-events-none absolute bottom-0 left-0 text-caption text-ink-faint">−{geo.band.toFixed(1)} bps</span>
          <span className="num pointer-events-none absolute bottom-0 right-0 text-caption text-ink-faint">+{geo.band.toFixed(1)} bps</span>
          {Math.abs(geo.micro - geo.mid) > 1e-9 && (
            <span
              className="num pointer-events-none absolute bottom-0 -translate-x-1/2 whitespace-nowrap text-caption text-ink-muted"
              style={{ left: `${at(geo.micro)}%` }}
            >
              μ {fmtPrice(geo.micro, 2)}
            </span>
          )}
          {readout && (
            <div
              className="float pointer-events-none absolute z-10 rounded-md px-2 py-1 text-caption"
              style={{ top: PAD_T, ...(hoverX > width / 2 ? { right: width - hoverX + 8 } : { left: hoverX + 8 }) }}
            >
              <div className="num text-ink">
                {fmtPrice(readout.price, 2)} <span className="text-ink-faint">{fmtSigned(readout.bps, 1)} bps</span>
              </div>
              <div className="num flex items-center gap-1.5 text-ink-muted">
                <span className={`h-1.5 w-1.5 rounded-full ${readout.side === "bid" ? "bg-bid" : "bg-ask"}`} aria-hidden />
                {readout.side} depth {fmtQty(readout.depth, 3)} {base}
              </div>
            </div>
          )}
        </>
      ) : (
        <span className="absolute inset-0 grid place-items-center text-meta text-ink-faint">
          {subscribed ? "Waiting for the first book snapshot…" : "Book stream paused — resume it to see depth"}
        </span>
      )}
    </div>
  );
}
