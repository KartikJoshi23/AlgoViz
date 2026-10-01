"use client";

/**
 * Design-system primitives. Styling lives in app/ds.css; these components only
 * choose the classes and the accessible structure. Colour is semantic
 * (bid / ask / mid, the status scale, the regime ramp, the accent) and text
 * stays in ink — tones are carried by dots, tints and marks.
 */
import { X, type LucideIcon } from "lucide-react";
import {
  cloneElement,
  forwardRef,
  isValidElement,
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";

import { regimeLevel } from "@/lib/theme";
import type { RegimeLabel } from "@/lib/ws/types";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ── Panel ─────────────────────────────────────────────────────────

export interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  /** The section's glyph, shown in a small chip before the title. */
  icon?: LucideIcon;
  /** Inline metadata after the title (one line, truncated). */
  subtitle?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  /** false: the body has no padding (charts and canvases that run to the edge). */
  padded?: boolean;
  bodyClassName?: string;
}

/** The surface every dashboard tile is built on: header (icon · title · meta · actions), body, optional footer. */
export const Panel = forwardRef<HTMLElement, PanelProps>(function Panel(
  { title, icon: Icon, subtitle, actions, footer, padded = true, className, bodyClassName, children, ...rest },
  ref,
) {
  return (
    <section ref={ref} className={cx("panel", className)} {...rest}>
      {(title || actions) && (
        <header className="panel-header">
          {Icon && (
            <span className="panel-icon" aria-hidden>
              <Icon size={14} strokeWidth={2} />
            </span>
          )}
          {title && <h2 className="panel-title">{title}</h2>}
          {subtitle && <span className="panel-meta">{subtitle}</span>}
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      <div className={cx("panel-body", bodyClassName)} data-flush={padded ? undefined : ""}>
        {children}
      </div>
      {footer && <footer className="panel-footer">{footer}</footer>}
    </section>
  );
});

// ── Button ────────────────────────────────────────────────────────

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "danger" | "ghost";
  size?: "sm" | "md";
  icon?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "md", icon, className, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx("btn", variant !== "default" && `btn-${variant}`, size === "sm" && "btn-sm", icon && "btn-icon", className)}
      {...rest}
    />
  );
});

// ── Badge ─────────────────────────────────────────────────────────

export type BadgeTone = "neutral" | "bid" | "ask" | "mid" | "accent" | "good" | "warning" | "serious" | "critical" | "brand" | RegimeLabel;

const REGIME_TONES: ReadonlySet<string> = new Set(["calm", "normal", "elevated", "extreme"]);

export function Badge({ tone = "neutral", className, children, ...rest }: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  const dataTone = tone === "neutral" ? undefined : REGIME_TONES.has(tone) ? `regime-${regimeLevel(tone as RegimeLabel)}` : tone;
  return (
    <span className={cx("badge", className)} data-tone={dataTone} {...rest}>
      {children}
    </span>
  );
}

/** A z-score against the 15-minute baseline: quiet until |z| ≥ 2, dim while the baseline warms up. */
export function ZBadge({ z }: { z: number | null | undefined }) {
  if (z == null || !Number.isFinite(z)) {
    return (
      <span className="zbadge" data-level="warming" title="Baseline warming up (2 min of bars)">
        z —
      </span>
    );
  }
  const unusual = Math.abs(z) >= 2;
  return (
    <span className="zbadge" data-level={unusual ? "elevated" : undefined} title="z-score vs. the 15-minute EWMA baseline">
      {`${z > 0 ? "+" : z < 0 ? "−" : ""}${Math.abs(z).toFixed(1)}σ`}
    </span>
  );
}

// ── Form controls ─────────────────────────────────────────────────

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cx("input", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cx("input select", className)} {...rest}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={cx("input min-h-[72px] resize-y", className)} {...rest} />;
});

/**
 * Label + control + optional hint, stacked. Renders a <label> so a single
 * input/select inherits its accessible name; pass `as="div"` for composite
 * controls (segmented controls, switches, sliders) where a wrapping label
 * would mislabel them.
 */
export function Field({
  label,
  hint,
  className,
  children,
  as = "label",
}: {
  label: ReactNode;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
  as?: "label" | "div";
}) {
  const Tag = as;
  return (
    <Tag className={cx("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </Tag>
  );
}

/** A toggle. Needs a name: a visible `label`, or `aria-label` when the context says what it does. */
export function Switch({
  checked,
  onChange,
  label,
  disabled,
  className,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      className={cx("switch", className)}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-track" />
      {label && <span className="text-meta text-ink-muted">{label}</span>}
    </button>
  );
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  items,
  className,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: ReactNode }[];
  className?: string;
  label?: string;
}) {
  return (
    <div className={cx("segmented", className)} role="tablist" aria-label={label}>
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          type="button"
          aria-selected={it.value === value}
          className="segment"
          onClick={() => onChange(it.value)}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

// ── Tables and overlays ───────────────────────────────────────────

/** A scrolling table region. Focusable, so a keyboard can scroll it; named for screen readers. */
export function TableWrap({
  label,
  maxHeight,
  className,
  children,
}: {
  label: string;
  maxHeight?: number | string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={cx("table-wrap", className)}
      style={maxHeight != null ? { maxHeight } : undefined}
    >
      {children}
    </div>
  );
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A side sheet (modal dialog) for forms. Focus moves into it on open, Tab is
 * trapped inside, Escape and the backdrop close it, page scroll is locked,
 * and focus returns to whatever opened it.
 */
export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  footer,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const close = useEffectEvent(onClose);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const focusables = () => (el ? [...el.querySelectorAll<HTMLElement>(FOCUSABLE)] : []);
    (focusables().find((f) => f.closest("[data-drawer-body]")) ?? el)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== "Tab") return;
      const f = focusables();
      if (f.length === 0) return;
      const first = f[0]!;
      const last = f[f.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className="drawer">
        <header className="panel-header">
          <h2 id={titleId} className="panel-title">
            {title}
          </h2>
          {subtitle && <span className="panel-meta">{subtitle}</span>}
          <div className="panel-actions">
            <Button variant="ghost" icon onClick={onClose} aria-label="Close">
              <X size={16} />
            </Button>
          </div>
        </header>
        <div data-drawer-body className="min-h-0 flex-1 overflow-y-auto p-4">
          {children}
        </div>
        {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>}
      </div>
    </>,
    document.body,
  );
}

// ── Small pieces ──────────────────────────────────────────────────

export function Divider({ className }: { className?: string }) {
  return <div role="separator" className={cx("divider my-3", className)} />;
}

/**
 * Hover / focus tooltip. The trigger keeps its own semantics; the text is
 * linked with aria-describedby. `align="end"` anchors it to the trigger's
 * right edge, for triggers near the right of the screen.
 */
export function Tooltip({
  content,
  side = "top",
  align = "center",
  className,
  children,
}: {
  content: ReactNode;
  side?: "top" | "bottom";
  align?: "center" | "end";
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const trigger = isValidElement<{ "aria-describedby"?: string }>(children) ? cloneElement(children, { "aria-describedby": id }) : children;
  return (
    <span className={cx("tooltip-host inline-flex", className)}>
      {trigger}
      <span id={id} role="tooltip" className="tooltip float" data-side={side} data-align={align === "end" ? "end" : undefined}>
        {content}
      </span>
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={cx("skeleton", className)} style={style} aria-hidden />;
}

/** Circular progress (warm-up, sample collection). `value` is 0…1. */
export function ProgressRing({
  value,
  size = 36,
  stroke = 3,
  children,
  label,
}: {
  value: number;
  size?: number;
  stroke?: number;
  children?: ReactNode;
  label: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.min(1, Math.max(0, value));
  return (
    <span
      className="relative inline-grid shrink-0 place-items-center"
      style={{ width: size, height: size }}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v * 100)}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-control)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - v)}
          style={{ transition: "stroke-dashoffset 600ms var(--ease-out-quint)" }}
        />
      </svg>
      {children && <span className="absolute inset-0 grid place-items-center">{children}</span>}
    </span>
  );
}
