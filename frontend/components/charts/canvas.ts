"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

/** An element's content width, updated on resize, so canvas charts redraw when the layout changes rather than on the next bar. */
export function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry?.contentRect.width ?? 0)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** Sizes the backing store for the device pixel ratio (capped at 2) and returns a cleared context in CSS pixels. */
export function prepareCanvas(el: HTMLCanvasElement, width: number, height: number): CanvasRenderingContext2D | null {
  const ctx = el.getContext("2d");
  if (!ctx) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  el.width = Math.round(width * dpr);
  el.height = Math.round(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return ctx;
}

/** Snaps a coordinate to the pixel grid so 1px hairlines stay crisp. */
export const crisp = (v: number) => Math.round(v) + 0.5;
