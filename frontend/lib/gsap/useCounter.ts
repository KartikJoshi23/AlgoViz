"use client";

import { useEffect, useRef } from "react";

import { gsap } from "./index";
import { useEffectiveMotion } from "@/lib/store";

/**
 * Tween a displayed number toward `value` without React re-renders per frame.
 * Returns a ref to attach to the element whose textContent is written.
 */
export function useCounter(value: number | null | undefined, format: (v: number) => string, opts: { duration?: number } = {}) {
  const ref = useRef<HTMLSpanElement>(null);
  const proxy = useRef({ v: Number.NaN });
  const lastFlash = useRef(0);
  const motion = useEffectiveMotion();
  const fmtRef = useRef(format);
  useEffect(() => {
    fmtRef.current = format;
  }, [format]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (value == null || !Number.isFinite(value)) {
      el.textContent = "—";
      proxy.current.v = Number.NaN;
      return;
    }
    // No tween on first value, with reduced motion, or while the tab is hidden
    // (requestAnimationFrame is paused there, so a tween would never complete).
    if (!motion || !Number.isFinite(proxy.current.v) || document.hidden) {
      proxy.current.v = value;
      el.textContent = fmtRef.current(value);
      return;
    }
    // terminal-style tick flash: teal on an up-tick, coral on a down-tick,
    // at most once per 2.5 s so 5 Hz features read as ticks, not a strobe
    const now = performance.now();
    if (value !== proxy.current.v && now - lastFlash.current > 2500) {
      lastFlash.current = now;
      el.removeAttribute("data-tick");
      void el.offsetWidth; // restart the CSS animation
      el.setAttribute("data-tick", value > proxy.current.v ? "up" : "down");
    }
    const tween = gsap.to(proxy.current, {
      v: value,
      duration: opts.duration ?? 0.45,
      ease: "power2.out",
      overwrite: true,
      onUpdate: () => {
        el.textContent = fmtRef.current(proxy.current.v);
      },
    });
    return () => {
      tween.kill();
    };
  }, [value, motion, opts.duration]);

  return ref;
}
