"use client";

import { AlertOctagon, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { gsap } from "@/lib/gsap";
import { useEffectiveMotion, useStore, type Toast } from "@/lib/store";

const ICONS: Record<Toast["tone"], typeof Info> = {
  neutral: Info,
  accent: Info,
  good: CheckCircle2,
  warning: AlertTriangle,
  serious: AlertTriangle,
  critical: AlertOctagon,
};

const COLOR: Record<Toast["tone"], string> = {
  neutral: "var(--color-ink-faint)",
  accent: "var(--color-accent)",
  good: "var(--color-good)",
  warning: "var(--color-warning)",
  serious: "var(--color-serious)",
  critical: "var(--color-critical)",
};

function ToastCard({ toast }: { toast: Toast }) {
  const dismiss = useStore((s) => s.dismissToast);
  const motion = useEffectiveMotion();
  const ref = useRef<HTMLDivElement>(null);
  const Icon = ICONS[toast.tone];

  useEffect(() => {
    const el = ref.current;
    if (el && motion) gsap.fromTo(el, { y: 8, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, ease: "power3.out" });
    const id = setTimeout(() => {
      if (el && motion) {
        gsap.to(el, { opacity: 0, y: 4, duration: 0.2, ease: "power2.in", onComplete: () => dismiss(toast.id) });
      } else {
        dismiss(toast.id);
      }
    }, toast.ttlMs);
    return () => clearTimeout(id);
  }, [toast.id, toast.ttlMs, dismiss, motion]);

  return (
    <div
      ref={ref}
      className="float pointer-events-auto flex w-80 items-start gap-3 rounded-[10px] py-3 pl-3 pr-2"
      style={{ borderLeft: `3px solid ${COLOR[toast.tone]}` }}
      role="status"
    >
      <Icon size={16} className="mt-0.5 shrink-0" style={{ color: COLOR[toast.tone] }} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="truncate text-body font-semibold text-ink">{toast.title}</div>
        {toast.body && <div className="mt-0.5 line-clamp-3 text-meta leading-snug text-ink-muted">{toast.body}</div>}
      </div>
      <button type="button" className="btn btn-ghost btn-sm btn-icon -mt-1" onClick={() => dismiss(toast.id)} aria-label="Dismiss">
        <X size={14} />
      </button>
    </div>
  );
}

export function Toasts() {
  const toasts = useStore((s) => s.ui.toasts);
  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-80 flex flex-col gap-2 md:bottom-10" aria-live="polite">
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} />
      ))}
    </div>
  );
}
