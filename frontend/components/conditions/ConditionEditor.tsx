"use client";

import { BookOpen, Plus, X } from "lucide-react";
import { useMemo } from "react";

import { Button, SegmentedControl } from "@/components/ds";
import type { FeatureCatalogEntry } from "@/lib/api/hooks";

/** The backend's shared condition language (signals, alerts, strategies). */
export type Leaf = { f: string; op: string; v: number | string | boolean | (string | number)[] };
export type Group = { all: Condition[] } | { any: Condition[] } | { not: Condition };
export type Condition = Leaf | Group;

export const isLeaf = (c: Condition): c is Leaf => "f" in c;

export interface FieldSpec {
  name: string;
  label: string;
  unit: string;
  kind: FeatureCatalogEntry["kind"];
  group: string;
  values: string[];
  description: string;
}

/** Evaluation-context fields that are not in the catalog (backtest / signal state). */
export const CONTEXT_FIELDS: FieldSpec[] = [
  {
    name: "bars_held",
    label: "Bars held",
    unit: "bars",
    kind: "quantity",
    group: "position",
    values: [],
    description: "Bars since the position was opened.",
  },
  {
    name: "unrealised_bps",
    label: "Unrealised P&L",
    unit: "bps",
    kind: "bps",
    group: "position",
    values: [],
    description: "Open profit or loss of the position.",
  },
  {
    name: "position",
    label: "Position (1 / −1 / 0)",
    unit: "",
    kind: "ratio",
    group: "position",
    values: [],
    description: "1 long, −1 short, 0 flat.",
  },
];

const NUMERIC_OPS: { op: string; label: string }[] = [
  { op: ">", label: ">" },
  { op: ">=", label: "≥" },
  { op: "<", label: "<" },
  { op: "<=", label: "≤" },
  { op: "==", label: "=" },
  { op: "!=", label: "≠" },
];
const CATEGORICAL_OPS: { op: string; label: string }[] = [
  { op: "==", label: "is" },
  { op: "!=", label: "is not" },
  { op: "in", label: "in" },
  { op: "not_in", label: "not in" },
];

export function toFieldSpecs(catalog: FeatureCatalogEntry[] | undefined, extra: FieldSpec[] = []): FieldSpec[] {
  const base = (catalog ?? []).map((f) => ({
    name: f.name,
    label: f.label,
    unit: f.unit,
    kind: f.kind,
    group: f.group,
    values: f.values,
    description: f.description,
  }));
  return [...base, ...extra];
}

/** Human-readable form, mirroring the backend's `describe()`. */
export function describe(c: Condition | null | undefined): string {
  if (!c) return "—";
  if (isLeaf(c)) {
    const v = Array.isArray(c.v) ? `[${c.v.join(", ")}]` : String(c.v);
    return `${c.f} ${c.op.replace("_", " ")} ${v}`;
  }
  if ("not" in c) return `NOT ${describe(c.not)}`;
  const [kind, items] = "all" in c ? ["AND", c.all] : ["OR", c.any];
  if (items.length === 0) return "—";
  return `(${items.map(describe).join(` ${kind} `)})`;
}

/** A sensible first condition on `field` (or the default field). */
export function leafFor(fields: FieldSpec[], name?: string): Leaf {
  const f = fields.find((x) => x.name === (name ?? "ofi_z")) ?? fields[0];
  if (!f) return { f: name ?? "ofi_z", op: ">", v: 1.5 };
  if (f.kind === "categorical") return { f: f.name, op: "==", v: f.values[0] ?? "" };
  return { f: f.name, op: ">", v: f.kind === "zscore" ? 1.5 : f.kind === "probability" ? 0.5 : 0 };
}

/** Adds `leaf` to a condition tree: a leaf becomes an AND pair, a group gains a member. */
export function addLeaf(c: Condition | null, leaf: Leaf): Condition {
  if (!c) return leaf;
  if (isLeaf(c) || "not" in c) return { all: [c, leaf] };
  return "all" in c ? { all: [...c.all, leaf] } : { any: [...c.any, leaf] };
}

function LeafChip({
  leaf,
  fields,
  onChange,
  onRemove,
}: {
  leaf: Leaf;
  fields: FieldSpec[];
  onChange: (l: Leaf) => void;
  onRemove: () => void;
}) {
  const spec = fields.find((f) => f.name === leaf.f);
  const categorical = spec?.kind === "categorical";
  const ops = categorical ? CATEGORICAL_OPS : NUMERIC_OPS;
  const groups = useMemo(() => {
    const m = new Map<string, FieldSpec[]>();
    for (const f of fields) m.set(f.group, [...(m.get(f.group) ?? []), f]);
    return [...m.entries()];
  }, [fields]);

  const setField = (name: string) => {
    const next = fields.find((f) => f.name === name);
    if (!next) return;
    if (next.kind === "categorical") onChange({ f: name, op: "==", v: next.values[0] ?? "" });
    else onChange({ f: name, op: categorical ? ">" : leaf.op, v: typeof leaf.v === "number" ? leaf.v : 0 });
  };
  const setOp = (op: string) => {
    if (categorical) {
      const multi = op === "in" || op === "not_in";
      const cur = Array.isArray(leaf.v) ? leaf.v : [leaf.v];
      onChange({ f: leaf.f, op, v: multi ? cur.map(String) : String(cur[0] ?? spec?.values[0] ?? "") });
    } else onChange({ ...leaf, op });
  };

  return (
    <span className="cond-chip" title={spec?.description}>
      <select
        value={leaf.f}
        onChange={(e) => setField(e.target.value)}
        className="cond-part max-w-[14rem] shrink font-medium"
        aria-label="Feature"
      >
        {groups.map(([g, fs]) => (
          <optgroup key={g} label={g}>
            {fs.map((f) => (
              <option key={f.name} value={f.name}>
                {f.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <select value={leaf.op} onChange={(e) => setOp(e.target.value)} className="cond-part cond-op" aria-label="Operator">
        {ops.map((o) => (
          <option key={o.op} value={o.op}>
            {o.label}
          </option>
        ))}
      </select>
      {categorical ? (
        leaf.op === "in" || leaf.op === "not_in" ? (
          <span className="flex flex-wrap gap-1 px-1">
            {spec!.values.map((v) => {
              const on = Array.isArray(leaf.v) && leaf.v.map(String).includes(v);
              return (
                <button
                  key={v}
                  type="button"
                  className="badge h-6"
                  data-tone={on ? "accent" : undefined}
                  aria-pressed={on}
                  onClick={() => {
                    const cur = Array.isArray(leaf.v) ? leaf.v.map(String) : [];
                    onChange({ ...leaf, v: on ? cur.filter((x) => x !== v) : [...cur, v] });
                  }}
                >
                  {v}
                </button>
              );
            })}
          </span>
        ) : (
          <select
            value={String(leaf.v)}
            onChange={(e) => onChange({ ...leaf, v: e.target.value })}
            className="cond-part"
            aria-label="Value"
          >
            {spec!.values.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        )
      ) : (
        <>
          <input
            type="number"
            step="any"
            value={typeof leaf.v === "number" ? leaf.v : Number(leaf.v) || 0}
            onChange={(e) => onChange({ ...leaf, v: e.target.value === "" ? 0 : Number(e.target.value) })}
            className="cond-value"
            aria-label="Threshold"
          />
          {spec?.unit && <span className="px-1 text-caption text-ink-faint">{spec.unit}</span>}
        </>
      )}
      <Button variant="ghost" size="sm" icon onClick={onRemove} aria-label="Remove condition" className="h-6 w-6 rounded-full">
        <X size={13} />
      </Button>
    </span>
  );
}

function GroupEditor({
  group,
  fields,
  onChange,
  onRemove,
  onBrowse,
  depth,
}: {
  group: Exclude<Group, { not: Condition }>;
  fields: FieldSpec[];
  onChange: (g: Exclude<Group, { not: Condition }>) => void;
  onRemove?: () => void;
  onBrowse?: () => void;
  depth: number;
}) {
  const mode: "all" | "any" = "all" in group ? "all" : "any";
  const items = "all" in group ? group.all : group.any;
  const emit = (m: "all" | "any", list: Condition[]) => onChange(m === "all" ? { all: list } : { any: list });
  const setItem = (i: number, c: Condition) =>
    emit(
      mode,
      items.map((x, j) => (j === i ? c : x)),
    );
  const removeItem = (i: number) =>
    emit(
      mode,
      items.filter((_, j) => j !== i),
    );
  const joiner = mode === "all" ? "and" : "or";

  return (
    <div className={depth > 0 ? "rounded-lg border-l-2 border-line-strong bg-page/40 py-2 pl-3 pr-2" : ""}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SegmentedControl<"all" | "any">
          label={depth > 0 ? "Nested group matches" : "Matches"}
          value={mode}
          onChange={(m) => emit(m, items)}
          items={[
            { value: "all", label: "all of" },
            { value: "any", label: "any of" },
          ]}
        />
        <div className="ml-auto flex items-center gap-1">
          {onBrowse && (
            <Button variant="ghost" size="sm" onClick={onBrowse}>
              <BookOpen size={13} /> Browse features
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => emit(mode, [...items, leafFor(fields)])}>
            <Plus size={13} /> Condition
          </Button>
          {depth < 2 && (
            <Button variant="ghost" size="sm" onClick={() => emit(mode, [...items, { all: [leafFor(fields)] }])}>
              <Plus size={13} /> Group
            </Button>
          )}
          {onRemove && (
            <Button variant="ghost" size="sm" icon onClick={onRemove} aria-label="Remove group">
              <X size={14} />
            </Button>
          )}
        </div>
      </div>
      {items.length === 0 && <div className="text-meta text-ink-faint">No conditions — never true.</div>}
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
        {items.map((c, i) => (
          <span key={i} className={`flex items-center gap-1.5 ${isLeaf(c) || "not" in c ? "" : "basis-full"}`}>
            {i > 0 && <span className="text-caption font-medium uppercase tracking-wide text-ink-faint">{joiner}</span>}
            {isLeaf(c) ? (
              <LeafChip leaf={c} fields={fields} onChange={(l) => setItem(i, l)} onRemove={() => removeItem(i)} />
            ) : "not" in c ? (
              <span className="text-meta text-ink-faint">NOT groups are read-only here: {describe(c)}</span>
            ) : (
              <span className="flex-1">
                <GroupEditor group={c} fields={fields} onChange={(g) => setItem(i, g)} onRemove={() => removeItem(i)} depth={depth + 1} />
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Editor for one condition tree, as chips. A bare leaf is edited as
 * `{all:[leaf]}` and collapsed back to the leaf on output so stored JSON
 * stays minimal. `onBrowse` opens a feature catalog to add from.
 */
export function ConditionEditor({
  value,
  onChange,
  fields,
  onBrowse,
  emptyLabel = "No condition",
}: {
  value: Condition | null;
  onChange: (c: Condition | null) => void;
  fields: FieldSpec[];
  onBrowse?: () => void;
  emptyLabel?: string;
}) {
  if (!value) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed border-line-strong px-3 py-2">
        <span className="text-meta text-ink-faint">{emptyLabel}</span>
        <span className="flex items-center gap-1">
          {onBrowse && (
            <Button variant="ghost" size="sm" onClick={onBrowse}>
              <BookOpen size={13} /> Browse features
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => onChange(leafFor(fields))}>
            <Plus size={13} /> Condition
          </Button>
        </span>
      </div>
    );
  }
  const group: Exclude<Group, { not: Condition }> = isLeaf(value) || "not" in value ? { all: [value] } : value;
  const handle = (g: Exclude<Group, { not: Condition }>) => {
    const items = "all" in g ? g.all : g.any;
    if (items.length === 0) onChange(null);
    else if (items.length === 1 && isLeaf(items[0]!)) onChange(items[0]!);
    else onChange(g);
  };
  return <GroupEditor group={group} fields={fields} onChange={handle} onBrowse={onBrowse} depth={0} />;
}
