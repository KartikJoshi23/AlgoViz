"use client";

import { ArrowLeftRight, ChartCandlestick, Gauge } from "lucide-react";
import { useRef } from "react";

import { PriceChart } from "@/components/charts/PriceChart";
import { Strip, cumulative } from "@/components/charts/Strip";
import { Badge, Panel } from "@/components/ds";
import { BookPanel } from "@/components/panels/BookPanel";
import { LiquidityHero } from "@/components/panels/LiquidityHero";
import { MarketStrip } from "@/components/panels/MarketStrip";
import { PredictionPanel } from "@/components/panels/PredictionPanel";
import { RegimePanel } from "@/components/panels/RegimePanel";
import { SignalsFeed } from "@/components/panels/SignalsFeed";
import { TradeTape } from "@/components/panels/TradeTape";
import { PageHeader } from "@/components/ui/PageHeader";
import { fmtSigned } from "@/lib/format";
import { gsap, useGSAP } from "@/lib/gsap";
import { motionAllowed, useConnection, useHydrated } from "@/lib/store";
import { COLORS, rgba } from "@/lib/theme";

function LegendItem({ color, label, bar }: { color: string; label: string; bar?: string }) {
  return (
    <span className="flex items-center gap-1.5">
      {bar ? (
        <span className="flex h-2.5 items-end gap-px" aria-hidden>
          <span className="h-2 w-1 rounded-[1px]" style={{ background: color }} />
          <span className="h-2.5 w-1 rounded-[1px]" style={{ background: bar }} />
        </span>
      ) : (
        <span className="h-0.5 w-3.5 rounded-full" style={{ background: color }} aria-hidden />
      )}
      {label}
    </span>
  );
}

const sigma = (v: number) => `${fmtSigned(v, 2)}σ`;
// |z| ≥ 2 is where the signal rules fire; shaded in neutral ink, not a status colour
const TAILS = [
  { from: 2, to: 1e3, color: rgba(COLORS.ink, 0.04) },
  { from: -1e3, to: -2, color: rgba(COLORS.ink, 0.04) },
];
const Z_DOMAIN: [number, number] = [-3, 3];

export default function OverviewPage() {
  const root = useRef<HTMLDivElement>(null);
  const hydrated = useHydrated();
  const conn = useConnection();
  const base = conn.symbol.replace(/USDT$/, "");

  useGSAP(
    () => {
      if (!motionAllowed()) return;
      gsap.from(".panel", {
        y: 8,
        opacity: 0,
        duration: 0.45,
        stagger: { each: 0.03, from: "start" },
        ease: "power2.out",
        clearProps: "transform,opacity",
      });
    },
    { scope: root, dependencies: [] },
  );

  return (
    <div ref={root} className="space-y-3">
      <PageHeader
        eyebrow="Live market"
        title="Overview"
        subtitle={`${conn.symbol} · 1-second bars · 5 Hz features · ${conn.source} feed`}
        actions={!hydrated && <Badge>hydrating…</Badge>}
      />

      <MarketStrip />

      <div className="grid gap-3 lg:grid-cols-12">
        <LiquidityHero className="lg:col-span-8" height={400} />
        <div className="grid gap-3 lg:col-span-4 lg:grid-rows-2">
          <PredictionPanel />
          <RegimePanel />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-12">
        <Panel
          className="lg:col-span-8"
          icon={ChartCandlestick}
          title="Price"
          subtitle="1 s bars · local time"
          actions={
            <div className="flex items-center gap-3 text-meta text-ink-muted">
              <LegendItem color={COLORS.mid} label="mid" />
              <LegendItem color={COLORS.accent} label="VWAP" />
              <LegendItem color={COLORS.inkFaint} label="microprice" />
              <LegendItem color={rgba(COLORS.bid, 0.6)} bar={rgba(COLORS.ask, 0.6)} label="volume · net side" />
            </div>
          }
        >
          <PriceChart height={300} />
        </Panel>
        <BookPanel className="lg:col-span-4" height={200} />
      </div>

      <div className="grid gap-3 lg:grid-cols-12 lg:[&>*]:h-[380px]">
        <Panel
          className="lg:col-span-4"
          icon={ArrowLeftRight}
          title="Order flow"
          subtitle={`order-flow imbalance, ${base} · last 5 min`}
          bodyClassName="gap-4"
        >
          <Strip col="ofi" mode="bars" polarity height={112} label="Per 1 s bar" format={(v) => fmtSigned(v, 3)} />
          <Strip col="ofi" polarity transform={cumulative} height={112} label="Cumulative" format={(v) => fmtSigned(v, 2)} />
        </Panel>
        <SignalsFeed className="lg:col-span-4" />
        <TradeTape className="lg:col-span-4" rows={20} />
      </div>

      <Panel icon={Gauge} title="Session" subtitle="z-scores against the 15-minute baseline · shaded beyond ±2σ">
        <div className="grid gap-4 md:grid-cols-3">
          <Strip col="spread_z" zero height={100} label="Spread z" format={sigma} bands={TAILS} domain={Z_DOMAIN} />
          <Strip col="ofi_z" polarity height={100} label="Order-flow imbalance z" format={sigma} bands={TAILS} domain={Z_DOMAIN} />
          <Strip col="vol_z" zero height={100} label="Volatility z" format={sigma} bands={TAILS} domain={Z_DOMAIN} />
        </div>
      </Panel>
    </div>
  );
}
