"use client";

import { Droplets } from "lucide-react";
import dynamic from "next/dynamic";
import { useState, useSyncExternalStore } from "react";

import { Heatmap } from "@/components/charts/Heatmap";
import { Badge, Panel, SegmentedControl, Skeleton, Tooltip } from "@/components/ds";
import { fmtQty, fmtSigned } from "@/lib/format";
import { hasWebGL } from "@/lib/perf/webgl";
import { useBook, useConnection, useEffectiveMotion, useStore } from "@/lib/store";

const Terrain = dynamic(() => import("@/components/three/Terrain").then((m) => m.Terrain), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

const noSubscribe = () => () => {};

type View = "heatmap" | "terrain";

/** Header stats subscribe to the 5 Hz book on their own so the canvas host doesn't re-render. */
function LiquidityStats() {
  const book = useBook();
  const { symbol } = useConnection();
  const subscribed = useStore((s) => s.prefs.bookSubscribed);
  if (!book) return <Badge>{subscribed ? "syncing book…" : "book stream paused"}</Badge>;
  const imb = book.imbalance_w;
  return (
    <>
      {!subscribed && <Badge tone="warning">stream paused</Badge>}
      <Tooltip content="Depth-weighted queue imbalance: + more resting bids near the touch, − more asks">
        <Badge tone={Math.abs(imb) < 0.005 ? "neutral" : imb > 0 ? "bid" : "ask"} tabIndex={0}>
          <span className="num">imb {fmtSigned(imb, 2)}</span>
        </Badge>
      </Tooltip>
      <Tooltip content="Resting quantity within ±10 bps of mid, both sides">
        <Badge tabIndex={0} className="hidden lg:inline-flex">
          <span className="num">
            ±10 bps {fmtQty(book.liquidity_10bps, 1)} {symbol.replace(/USDT$/, "")}
          </span>
        </Badge>
      </Tooltip>
    </>
  );
}

/**
 * The liquidity hero: a price × time heatmap by default (legible at a glance,
 * 2D on every tier) and the 3D depth terrain on request where WebGL exists.
 */
export function LiquidityHero({
  height = 400,
  className = "",
  interactive = true,
}: {
  height?: number;
  className?: string;
  interactive?: boolean;
}) {
  // null during SSR/hydration; the Terrain option appears once WebGL is confirmed
  const webgl = useSyncExternalStore(noSubscribe, hasWebGL, () => null);
  const motion = useEffectiveMotion();
  const [view, setView] = useState<View>("heatmap");
  const terrain = view === "terrain" && webgl === true;

  return (
    <Panel
      className={className}
      icon={Droplets}
      title="Liquidity"
      subtitle={
        terrain
          ? `cumulative depth × 19 s${motion ? " · buys rise, sells fall" : ""}`
          : "resting size by price · last 3 min · bubbles are trades"
      }
      actions={
        <>
          <LiquidityStats />
          {webgl === true && (
            <SegmentedControl
              label="Liquidity view"
              value={view}
              onChange={setView}
              items={[
                { value: "heatmap", label: "Heatmap" },
                { value: "terrain", label: "Terrain" },
              ]}
            />
          )}
        </>
      }
      padded={false}
    >
      <div className="relative overflow-hidden rounded-b-[13px]" style={{ height }}>
        {terrain ? (
          <Terrain height={height} interactive={interactive} />
        ) : (
          <div className="px-4 pb-3">
            <Heatmap height={height - 12} />
          </div>
        )}
      </div>
    </Panel>
  );
}
