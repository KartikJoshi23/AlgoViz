"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";

import { useCounter } from "@/lib/gsap/useCounter";
import { cx } from "./index";

/**
 * Stat tile: label · z-badge / value · unit · delta / trend. The value is
 * ink (colour belongs to the delta pill and the marks), tweened between
 * samples and tabular so a live number never jitters.
 */
export function Stat({
  label,
  value,
  format,
  unit,
  badge,
  delta,
  trend,
  className,
}: {
  label: ReactNode;
  value: number | null | undefined;
  format: (v: number) => string;
  unit?: ReactNode;
  badge?: ReactNode;
  delta?: { text: ReactNode; direction?: "up" | "down" | null; title?: string };
  trend?: ReactNode;
  className?: string;
}) {
  const ref = useCounter(value, format);
  const Arrow = delta?.direction === "up" ? ArrowUpRight : delta?.direction === "down" ? ArrowDownRight : null;
  const pill = delta && (
    <span className="delta-pill shrink-0" data-direction={delta.direction ?? undefined} title={delta.title}>
      {Arrow && <Arrow size={12} strokeWidth={2.25} aria-hidden />}
      {delta.text}
    </span>
  );
  return (
    <div className={cx("panel flex min-w-0 flex-col gap-2 px-4 pb-3 pt-3.5", className)}>
      {/* the delta takes the badge's corner when there is no badge */}
      <div className="flex h-5 items-center justify-between gap-2">
        <span className="eyebrow truncate">{label}</span>
        {badge ?? pill}
      </div>
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-1">
        <span ref={ref} className="stat-value truncate px-0.5 text-ink">
          —
        </span>
        {unit && <span className="stat-unit shrink-0">{unit}</span>}
        {badge && pill && <span className="ml-auto self-center">{pill}</span>}
      </div>
      {trend && <div className="mt-auto">{trend}</div>}
    </div>
  );
}
