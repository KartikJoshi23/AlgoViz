"use client";

import { useEffect } from "react";
import { getGPUTier } from "detect-gpu";

import { isSoftwareRenderer } from "@/lib/perf/webgl";
import { useStore } from "@/lib/store";

/** Detect the GPU tier once and record the OS reduced-motion preference. */
export function usePerfDetection(): void {
  const setDetectedTier = useStore((s) => s.setDetectedTier);
  const setReducedMotionOS = useStore((s) => s.setReducedMotionOS);

  useEffect(() => {
    let cancelled = false;
    // Software renderers (CI, VMs, remote desktops) are "low" immediately — no
    // need to wait for detect-gpu's benchmark fetch, which also needs network.
    if (isSoftwareRenderer()) {
      setDetectedTier("low");
    } else {
      getGPUTier()
        .then((r) => {
          if (cancelled) return;
          setDetectedTier(r.tier >= 3 ? "high" : r.tier === 2 ? "mid" : "low");
        })
        .catch(() => {
          if (!cancelled) setDetectedTier("mid");
        });
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotionOS(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReducedMotionOS(e.matches);
    mq.addEventListener("change", onChange);
    return () => {
      cancelled = true;
      mq.removeEventListener("change", onChange);
    };
  }, [setDetectedTier, setReducedMotionOS]);
}
