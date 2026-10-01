"use client";

import { Activity, BarChart3, Bell, Brain, Command, Layers3, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";

import { Kbd, Tooltip, cx } from "@/components/ds";
import { fmtBps, fmtPrice } from "@/lib/format";
import { gsap } from "@/lib/gsap";
import { useCounter } from "@/lib/gsap/useCounter";
import { useBars, useConnection, useEffectiveMotion, useFeatures, useStore } from "@/lib/store";

export const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/book", label: "Book", icon: Layers3 },
  { href: "/intelligence", label: "Intelligence", icon: Brain },
  { href: "/strategies", label: "Strategies", icon: BarChart3 },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings2 },
] as const;

type Health = "good" | "warning" | "critical";

/** One verdict for "can I trust what I see": socket open and the exchange feed flowing. */
export function useFeedHealth(): { health: Health; text: string } {
  const conn = useConnection();
  const source = useStore((s) => s.sourceStatus?.status);
  if (conn.status === "closed" || source === "failed" || source === "geo_blocked") {
    return { health: "critical", text: conn.status === "closed" ? "disconnected" : (source ?? "").replace("_", " ") };
  }
  if (conn.status !== "open") return { health: "warning", text: conn.status };
  if (source && source !== "connected" && source !== "idle") return { health: "warning", text: source.replace("_", " ") };
  return { health: "good", text: conn.source };
}

function Wordmark() {
  return (
    <Link href="/" className="group flex shrink-0 items-center gap-2.5 rounded-md" aria-label="AlgoViz home">
      <span className="brand-mark" aria-hidden>
        <span>
          <span className="absolute inset-x-[7px] top-[7px] h-[3px] rounded-full bg-ask transition-transform group-hover:-translate-y-px" />
          <span className="absolute inset-x-[5px] top-1/2 h-px -translate-y-1/2 bg-mid" />
          <span className="absolute inset-x-[7px] bottom-[7px] h-[3px] rounded-full bg-bid transition-transform group-hover:translate-y-px" />
        </span>
      </span>
      <span className="text-title font-semibold tracking-tight">
        Algo<span className="brand-text">Viz</span>
      </span>
    </Link>
  );
}

/** Symbol, live mid with tick flash, 5-minute change and spread. */
function MarketTicker() {
  const conn = useConnection();
  const setPrefs = useStore((s) => s.setPrefs);
  const f = useFeatures();
  const { bars, head } = useBars();
  const price = useCounter(f?.mid, (v) => fmtPrice(v, 2));

  const change = useMemo(() => {
    void head;
    const n = bars.length;
    if (n < 2) return null;
    const close = bars.cols.close;
    const last = close.at(n - 1);
    const first = close.at(Math.max(0, n - 300));
    return Number.isFinite(last) && Number.isFinite(first) && first > 0 ? (last / first - 1) * 100 : null;
  }, [bars, head]);

  return (
    <div className="flex min-w-0 items-center gap-3">
      {conn.symbols.length > 1 ? (
        <label className="relative">
          <span className="sr-only">Symbol</span>
          <select
            className="input select h-8 w-auto border-transparent bg-transparent pl-2 font-semibold hover:bg-control"
            value={conn.symbol}
            onChange={(e) => setPrefs({ symbol: e.target.value })}
          >
            {conn.symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <span className="text-body font-semibold">{conn.symbol}</span>
      )}
      <span ref={price} className="num rounded px-1 text-title font-semibold" aria-label="Mid price">
        —
      </span>
      <Tooltip content="Change of the mid over the last 5 minutes of 1-second bars" side="bottom" align="end">
        <span
          tabIndex={0}
          className={cx(
            "num hidden rounded px-1 text-meta sm:inline",
            change == null ? "text-ink-faint" : change >= 0 ? "text-bid-text" : "text-ask-text",
          )}
        >
          {change == null ? "5m —" : `5m ${change >= 0 ? "+" : "−"}${Math.abs(change).toFixed(3)}%`}
        </span>
      </Tooltip>
      <span className="num hidden text-meta text-ink-faint xl:inline">spread {fmtBps(f?.spread_bps)}</span>
    </div>
  );
}

function FeedHealth() {
  const conn = useConnection();
  const { health, text } = useFeedHealth();
  const label = conn.source === "live" ? "Binance" : conn.source;
  return (
    <Tooltip
      side="bottom"
      align="end"
      content={
        <span className="flex flex-col gap-0.5">
          <span>
            Socket {conn.status} · feed {text}
          </span>
          <span className="text-ink-faint">round trip {conn.latencyMs != null ? `${conn.latencyMs} ms` : "—"}</span>
        </span>
      }
    >
      <span tabIndex={0} className="flex h-8 items-center gap-2 rounded-md px-2 text-meta text-ink-muted hover:bg-control">
        <span className="status-dot" data-status={health} />
        <span className="hidden capitalize sm:inline">{health === "good" ? label : text}</span>
        {conn.latencyMs != null && <span className="num hidden text-ink-faint md:inline">{conn.latencyMs} ms</span>}
      </span>
    </Tooltip>
  );
}

export function AppBar() {
  const pathname = usePathname();
  const setPaletteOpen = useStore((s) => s.setPaletteOpen);
  const motion = useEffectiveMotion();
  const indicator = useRef<HTMLSpanElement>(null);
  const list = useRef<HTMLDivElement>(null);

  // Active-route underline slides between links.
  useEffect(() => {
    const host = list.current;
    const ind = indicator.current;
    if (!host || !ind) return;
    const active = host.querySelector<HTMLAnchorElement>('[data-active="true"]');
    if (!active) {
      gsap.set(ind, { opacity: 0 });
      return;
    }
    const to = { x: active.offsetLeft + 8, width: active.offsetWidth - 16, opacity: 1 };
    if (motion) gsap.to(ind, { ...to, duration: 0.35, ease: "power3.out" });
    else gsap.set(ind, to);
  }, [pathname, motion]);

  return (
    <>
      <header className="float appbar sticky top-0 z-40 border-x-0 border-t-0">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 md:px-6">
          <Wordmark />
          <nav ref={list} className="relative hidden h-full items-center gap-0.5 md:flex" aria-label="Sections">
            <span ref={indicator} className="nav-indicator" style={{ width: 0 }} />
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                  className="nav-link"
                  title={label}
                >
                  <Icon size={15} strokeWidth={1.8} aria-hidden />
                  <span className="hidden xl:inline">{label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex min-w-0 items-center gap-2 md:gap-3">
            <MarketTicker />
            <span className="hidden h-5 w-px bg-line sm:block" aria-hidden />
            <FeedHealth />
            <button
              type="button"
              className="btn btn-ghost h-8 gap-1.5 px-2"
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette (Ctrl/⌘ K)"
              title="Command palette"
            >
              <Command size={15} aria-hidden />
              <span className="hidden lg:inline-flex">
                <Kbd>Ctrl K</Kbd>
              </span>
            </button>
          </div>
        </div>
      </header>
      <MobileTabBar pathname={pathname} />
    </>
  );
}

function MobileTabBar({ pathname }: { pathname: string }) {
  return (
    <nav
      className="float fixed inset-x-0 bottom-0 z-40 border-x-0 border-b-0 pb-[env(safe-area-inset-bottom)] md:hidden"
      aria-label="Sections"
    >
      <ul className="grid grid-cols-6">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <li key={href}>
              <Link
                href={href}
                data-active={active}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex h-14 flex-col items-center justify-center gap-1 text-caption font-medium transition-colors",
                  active ? "text-ink" : "text-ink-faint hover:text-ink-muted",
                )}
              >
                <Icon size={18} strokeWidth={active ? 2 : 1.7} aria-hidden className={active ? "text-accent-text" : undefined} />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
