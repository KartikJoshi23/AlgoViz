"use client";

import { useCallback, useMemo } from "react";

import { Sparkline } from "@/components/charts/Sparkline";
import { ZBadge } from "@/components/ds";
import { Stat } from "@/components/ds/Stat";
import { fmtBpsValue, fmtPrice, fmtSigned } from "@/lib/format";
import { useBars, useConnection, useFeatures } from "@/lib/store";

const FIVE_MIN = 300; // 1-second bars

/** Change of the mid over the trailing five minutes of bars (the stat tile's delta). */
function useFiveMinuteChange(): number | null {
  const { bars, head } = useBars();
  return useMemo(() => {
    void head;
    const n = bars.length;
    if (n < 2) return null;
    const last = bars.cols.close.at(n - 1);
    const first = bars.cols.close.at(Math.max(0, n - FIVE_MIN));
    return Number.isFinite(last) && Number.isFinite(first) && first > 0 ? (last / first - 1) * 100 : null;
  }, [bars, head]);
}

/** The six numbers a microstructure trader glances at first, each with its z-score and a 5-minute trend. */
export function MarketStrip() {
  const f = useFeatures();
  const { symbol } = useConnection();
  const { bars } = useBars();
  const change = useFiveMinuteChange();
  const base = symbol.replace(/USDT$/, "");

  // microprice − mid, in bps, per bar (the trend behind the microprice tile)
  const micropriceDev = useCallback(
    (i: number) => {
      const mid = bars.cols.close.at(i);
      const micro = bars.cols.microprice.at(i);
      return mid > 0 && Number.isFinite(micro) ? ((micro - mid) / mid) * 10_000 : Number.NaN;
    },
    [bars],
  );

  return (
    <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Stat
        label="Mid"
        value={f?.mid}
        format={(v) => fmtPrice(v, 2)}
        delta={
          change == null
            ? undefined
            : {
                text: `${fmtSigned(change, 3)}%`,
                direction: change > 0 ? "up" : change < 0 ? "down" : null,
                title: "Change over the last 5 minutes",
              }
        }
        trend={<Sparkline col="close" label="Mid, last 5 minutes" />}
      />
      <Stat
        label="Spread"
        value={f?.spread_bps}
        format={(v) => fmtBpsValue(v)}
        unit="bps"
        badge={<ZBadge z={f?.spread_z} />}
        trend={<Sparkline col="spread_bps" label="Spread, last 5 minutes" />}
      />
      <Stat
        label="Microprice − mid"
        value={f?.microprice_dev_bps}
        format={(v) => fmtSigned(v, 3)}
        unit="bps"
        trend={<Sparkline col="microprice" transform={micropriceDev} label="Microprice minus mid, last 5 minutes" />}
      />
      <Stat
        label={
          <>
            <abbr title="Order-flow imbalance" className="no-underline">
              OFI
            </abbr>{" "}
            5 s
          </>
        }
        value={f?.ofi_5s}
        format={(v) => fmtSigned(v, 3)}
        unit={base}
        badge={<ZBadge z={f?.ofi_z} />}
        trend={<Sparkline col="ofi" label="OFI per bar, last 5 minutes" />}
      />
      <Stat
        label="Trade velocity"
        value={f?.velocity}
        format={(v) => v.toFixed(1)}
        unit="trades/s"
        badge={<ZBadge z={f?.velocity_z} />}
        trend={<Sparkline col="velocity" label="Trade velocity, last 5 minutes" />}
      />
      <Stat
        label="Volatility"
        value={f?.volatility_bps}
        format={(v) => v.toFixed(2)}
        unit="bps/min"
        badge={<ZBadge z={f?.vol_z} />}
        trend={<Sparkline col="volatility_bps" label="Volatility, last 5 minutes" />}
      />
    </section>
  );
}
