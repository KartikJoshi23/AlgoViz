import type { ReactNode } from "react";

/** A page's title block: an eyebrow naming the area in the brand gradient, the title, a one-line subtitle, and actions. */
export function PageHeader({
  title,
  eyebrow,
  subtitle,
  actions,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 pt-1">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow brand-text mb-1.5 w-fit">{eyebrow}</p>}
        <h1 className="text-h1 font-semibold leading-tight tracking-[-0.02em] text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-body text-ink-faint">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: ReactNode; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="panel items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="text-title font-semibold text-ink">{title}</div>
      {body && <div className="max-w-md text-body text-ink-muted">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** A small read-out inside a panel: label over an ink value, with a side dot when the value belongs to bid, ask or mid. */
export function MetricTile({
  label,
  value,
  tone,
  hint,
  className = "",
}: {
  label: ReactNode;
  value: ReactNode;
  tone?: "bid" | "ask" | "mid" | "muted";
  hint?: ReactNode;
  className?: string;
}) {
  const dot = tone === "bid" ? "bg-bid" : tone === "ask" ? "bg-ask" : tone === "mid" ? "bg-mid" : null;
  return (
    <div className={`raised flex min-w-0 flex-col gap-0.5 px-3 py-2 ${className}`} title={typeof hint === "string" ? hint : undefined}>
      <span className="flex items-center gap-1.5 text-meta text-ink-muted">
        {dot && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} aria-hidden />}
        {label}
      </span>
      <span className={`num truncate text-title font-semibold ${tone === "muted" ? "text-ink-muted" : "text-ink"}`}>{value}</span>
      {hint && <span className="truncate text-caption text-ink-faint">{hint}</span>}
    </div>
  );
}
