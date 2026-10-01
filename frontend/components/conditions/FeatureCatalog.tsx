"use client";

import { Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Input } from "@/components/ds";

import type { FieldSpec } from "./ConditionEditor";

/** The feature catalog, searchable by name, label or description; picking a feature adds a condition on it. */
export function FeatureCatalog({ fields, onPick }: { fields: FieldSpec[]; onPick: (name: string) => void }) {
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const m = new Map<string, FieldSpec[]>();
    for (const f of fields) {
      if (needle && ![f.name, f.label, f.description, f.group].some((s) => s.toLowerCase().includes(needle))) continue;
      m.set(f.group, [...(m.get(f.group) ?? []), f]);
    }
    return [...m.entries()];
  }, [fields, q]);

  return (
    <div className="space-y-4">
      <label className="relative block">
        <span className="sr-only">Search features</span>
        <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="spread, imbalance, regime…" className="pl-8" />
      </label>
      {groups.length === 0 && <p className="text-body text-ink-faint">No feature matches “{q}”.</p>}
      {groups.map(([g, fs]) => (
        <section key={g}>
          <h3 className="col-head mb-1.5 capitalize">{g}</h3>
          <ul className="space-y-px">
            {fs.map((f) => (
              <li key={f.name}>
                <button
                  type="button"
                  onClick={() => onPick(f.name)}
                  className="row group flex w-full items-start gap-3 px-2 py-2 text-left"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <span className="text-body font-medium text-ink">{f.label}</span>
                      {f.unit && <span className="text-caption text-ink-faint">{f.unit}</span>}
                      <span className="num ml-auto text-caption text-ink-faint">{f.name}</span>
                    </span>
                    {f.description && <span className="mt-0.5 block text-meta leading-snug text-ink-muted">{f.description}</span>}
                  </span>
                  <Plus size={14} className="mt-1 shrink-0 text-ink-faint group-hover:text-accent" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
