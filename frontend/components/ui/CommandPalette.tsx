"use client";

import { ArrowRight, Layers3, MoonStar, Search, Sparkles, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Kbd } from "@/components/ds";
import { gsap, useGSAP } from "@/lib/gsap";
import { useConnection, useEffectiveMotion, useStore } from "@/lib/store";
import { NAV_ITEMS } from "./AppBar";

interface Command {
  id: string;
  group: string;
  label: string;
  hint?: string;
  keywords?: string;
  run: () => void;
  icon?: React.ReactNode;
}

export function CommandPalette() {
  const open = useStore((s) => s.ui.paletteOpen);
  const setOpen = useStore((s) => s.setPaletteOpen);

  // global shortcut
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  if (!open) return null;
  return <PaletteDialog close={() => setOpen(false)} />;
}

function PaletteDialog({ close }: { close: () => void }) {
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const conn = useConnection();
  const router = useRouter();
  const motion = useEffectiveMotion();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  const commands = useMemo<Command[]>(() => {
    const nav: Command[] = NAV_ITEMS.map(({ href, label, icon: Icon }) => ({
      id: `nav:${href}`,
      group: "Go to",
      label,
      hint: href,
      icon: <Icon size={15} />,
      run: () => router.push(href),
    }));
    const symbols: Command[] = conn.symbols.map((s) => ({
      id: `sym:${s}`,
      group: "Symbol",
      label: `Switch to ${s}`,
      keywords: "symbol pair market",
      icon: <Zap size={15} />,
      run: () => setPrefs({ symbol: s }),
    }));
    const actions: Command[] = [
      {
        id: "book",
        group: "Data",
        label: prefs.bookSubscribed ? "Unsubscribe from order book stream" : "Subscribe to order book stream",
        keywords: "depth l2 terrain",
        icon: <Layers3 size={15} />,
        run: () => setPrefs({ bookSubscribed: !prefs.bookSubscribed }),
      },
      {
        id: "motion",
        group: "Display",
        label: prefs.motion === "reduced" ? "Enable motion" : "Reduce motion",
        keywords: "animation performance",
        icon: <MoonStar size={15} />,
        run: () => setPrefs({ motion: prefs.motion === "reduced" ? "auto" : "reduced" }),
      },
      {
        id: "tier",
        group: "Display",
        label: `Performance tier: ${prefs.perfTier} → cycle`,
        keywords: "gpu quality",
        icon: <Sparkles size={15} />,
        run: () => {
          const order = ["auto", "low", "mid", "high"] as const;
          const next = order[(order.indexOf(prefs.perfTier) + 1) % order.length]!;
          setPrefs({ perfTier: next });
        },
      },
    ];
    return [...nav, ...symbols, ...actions];
  }, [conn.symbols, prefs, router, setPrefs]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((c) => `${c.group} ${c.label} ${c.hint ?? ""} ${c.keywords ?? ""}`.toLowerCase().includes(needle));
  }, [commands, q]);

  useGSAP(
    () => {
      if (!panelRef.current || !motion) return;
      gsap.fromTo(
        panelRef.current,
        { y: 10, opacity: 0, scale: 0.985 },
        { y: 0, opacity: 1, scale: 1, duration: 0.28, ease: "power3.out" },
      );
    },
    { dependencies: [] },
  );

  const run = (c: Command) => {
    c.run();
    close();
  };

  return (
    <div
      className="fixed inset-0 z-75 flex items-start justify-center bg-page/60 p-4 pt-[12vh]"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div ref={panelRef} className="float w-full max-w-xl overflow-hidden rounded-[10px]" onClick={(e) => e.stopPropagation()}>
        <div className="flex h-12 items-center gap-2.5 border-b border-line px-4">
          <Search size={16} className="text-ink-faint" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setIdx(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIdx((i) => Math.min(i + 1, filtered.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setIdx((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && filtered[idx]) {
                run(filtered[idx]);
              }
            }}
            placeholder="Jump to a view, switch symbol, toggle display…"
            className="w-full bg-transparent text-ui outline-none placeholder:text-ink-disabled"
          />
          <Kbd>esc</Kbd>
        </div>
        <ul className="max-h-[50vh] overflow-y-auto p-2" role="listbox">
          {filtered.length === 0 && <li className="px-3 py-6 text-center text-body text-ink-faint">No matches</li>}
          {filtered.map((c, i) => (
            <li key={c.id} role="option" aria-selected={i === idx}>
              <button
                type="button"
                className={`row flex h-9 w-full items-center gap-3 px-3 text-left text-body ${i === idx ? "bg-control" : ""}`}
                onMouseEnter={() => setIdx(i)}
                onClick={() => run(c)}
              >
                <span className="text-ink-faint">{c.icon}</span>
                <span className="w-16 shrink-0 text-meta text-ink-faint">{c.group}</span>
                <span className="text-ink">{c.label}</span>
                {c.hint && <span className="num ml-auto text-meta text-ink-faint">{c.hint}</span>}
                <ArrowRight size={14} className={`text-ink-faint ${i === idx ? "opacity-100" : "opacity-0"}`} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
