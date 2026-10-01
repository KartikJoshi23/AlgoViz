"use client";

import { useEffect } from "react";

import { useStore } from "@/lib/store";
import { REGIME_COLORS } from "@/lib/theme";
import type { RegimeLabel } from "@/lib/ws/types";

/**
 * The page background: a regime-tinted light from above, a fine grid and grain
 * (all CSS, see `.ambient` in globals.css). It is static; when the regime
 * changes the tint cross-fades through the registered `--regime` property.
 */
export function AmbientLayer() {
  const label = useStore((s) => (s.regime?.label ?? "calm") as RegimeLabel);

  useEffect(() => {
    document.documentElement.style.setProperty("--regime", REGIME_COLORS[label] ?? REGIME_COLORS.calm);
  }, [label]);

  return <div className="ambient" aria-hidden />;
}
