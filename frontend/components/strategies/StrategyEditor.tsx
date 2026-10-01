"use client";

import { CircleAlert, Save, Trash2, Wand2, Workflow } from "lucide-react";
import { useMemo, useState } from "react";

import {
  addLeaf,
  ConditionEditor,
  CONTEXT_FIELDS,
  describe,
  leafFor,
  toFieldSpecs,
  type Condition,
} from "@/components/conditions/ConditionEditor";
import { FeatureCatalog } from "@/components/conditions/FeatureCatalog";
import { Badge, Button, Divider, Drawer, Field, Input, Panel, SegmentedControl, Select } from "@/components/ds";
import { useCatalog, useStrategyExamples, useStrategyMutations, type Strategy, type StrategyExample } from "@/lib/api/hooks";
import { useStore } from "@/lib/store";

export interface StrategySpec {
  side: "long" | "short" | "both";
  size_pct: number;
  entry_long: Condition | null;
  entry_short: Condition | null;
  exit: Condition | null;
  stop_loss_bps: number | null;
  take_profit_bps: number | null;
  max_hold_s: number | null;
  cooldown_s: number;
}

const DEFAULT_SPEC: StrategySpec = {
  side: "both",
  size_pct: 50,
  entry_long: { all: [{ f: "ofi_z", op: ">", v: 1.5 }] },
  entry_short: { all: [{ f: "ofi_z", op: "<", v: -1.5 }] },
  exit: null,
  stop_loss_bps: 15,
  take_profit_bps: 30,
  max_hold_s: 120,
  cooldown_s: 0,
};

function specFromConfig(config: Record<string, unknown> | undefined): StrategySpec {
  const c = (config ?? {}) as Partial<Record<keyof StrategySpec, unknown>>;
  const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
  return {
    side: (c.side as StrategySpec["side"]) ?? "both",
    size_pct: num(c.size_pct) ?? 100,
    entry_long: (c.entry_long as Condition | null) ?? null,
    entry_short: (c.entry_short as Condition | null) ?? null,
    exit: (c.exit as Condition | null) ?? null,
    stop_loss_bps: num(c.stop_loss_bps),
    take_profit_bps: num(c.take_profit_bps),
    max_hold_s: num(c.max_hold_s),
    cooldown_s: num(c.cooldown_s) ?? 0,
  };
}

function configFromSpec(s: StrategySpec): Record<string, unknown> {
  const out: Record<string, unknown> = { side: s.side, size_pct: s.size_pct, cooldown_s: s.cooldown_s };
  if (s.side !== "short" && s.entry_long) out.entry_long = s.entry_long;
  if (s.side !== "long" && s.entry_short) out.entry_short = s.entry_short;
  if (s.exit) out.exit = s.exit;
  if (s.stop_loss_bps != null) out.stop_loss_bps = s.stop_loss_bps;
  if (s.take_profit_bps != null) out.take_profit_bps = s.take_profit_bps;
  if (s.max_hold_s != null) out.max_hold_s = s.max_hold_s;
  return out;
}

function usesModel(s: StrategySpec): boolean {
  const txt = JSON.stringify([s.entry_long, s.entry_short, s.exit]);
  return /"f":"p_(up|down)"/.test(txt);
}

function validate(s: StrategySpec, name: string): string[] {
  const errs: string[] = [];
  if (!name.trim()) errs.push("Name is required.");
  if (s.side !== "short" && !s.entry_long) errs.push("A long entry condition is required for side = long / both.");
  if (s.side !== "long" && !s.entry_short) errs.push("A short entry condition is required for side = short / both.");
  if (!s.exit && s.stop_loss_bps == null && s.take_profit_bps == null && s.max_hold_s == null)
    errs.push("At least one exit mechanism is required (exit rule, stop, target or max hold).");
  if (!(s.size_pct > 0 && s.size_pct <= 100)) errs.push("Size must be within (0, 100] % of equity.");
  return errs;
}

function NumberField({
  label,
  value,
  onChange,
  unit,
  hint,
  min,
  step = "any",
  nullable = true,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  unit?: string;
  hint?: string;
  min?: number;
  step?: string | number;
  nullable?: boolean;
}) {
  return (
    <Field label={unit ? `${label} (${unit})` : label} hint={hint}>
      <Input
        type="number"
        step={step}
        min={min}
        value={value ?? ""}
        placeholder={nullable ? "off" : undefined}
        onChange={(e) => onChange(e.target.value === "" ? (nullable ? null : 0) : Number(e.target.value))}
        className="num"
      />
    </Field>
  );
}

function describeExample(ex: StrategyExample): string {
  const d = ex.description as Record<string, string | null>;
  return `${d.entry_long ?? ""}${d.entry_short ? ` / ${d.entry_short}` : ""}${d.exit ? ` → exit ${d.exit}` : ""}`.trim();
}

type Block = "entry_long" | "entry_short" | "exit";
const BLOCKS: { key: Block; title: string; dot: string; empty: string }[] = [
  { key: "entry_long", title: "Enter long when", dot: "bg-bid", empty: "No long entry" },
  { key: "entry_short", title: "Enter short when", dot: "bg-ask", empty: "No short entry" },
  { key: "exit", title: "Exit when (optional)", dot: "bg-ink-faint", empty: "Exit only on the stop, target or max hold" },
];

export function StrategyEditor({
  strategy,
  template = null,
  onSaved,
  onDeleted,
}: {
  strategy: Strategy | null; // null = new
  template?: StrategyExample | null; // prefill a new strategy from a template
  onSaved: (s: Strategy) => void;
  onDeleted: () => void;
}) {
  const catalog = useCatalog();
  const examples = useStrategyExamples();
  const { create, update, remove } = useStrategyMutations();
  const addToast = useStore((s) => s.addToast);

  const [name, setName] = useState(strategy?.name ?? (template ? template.id.replace(/_/g, " ") : ""));
  const [description, setDescription] = useState(strategy?.description ?? (template ? describeExample(template) : ""));
  const [spec, setSpec] = useState<StrategySpec>(() =>
    strategy
      ? specFromConfig(strategy.config as Record<string, unknown>)
      : template
        ? specFromConfig(template.config as Record<string, unknown>)
        : DEFAULT_SPEC,
  );
  const [browsing, setBrowsing] = useState<Block | null>(null);
  const fields = useMemo(() => toFieldSpecs(catalog.data, CONTEXT_FIELDS), [catalog.data]);
  const errors = validate(spec, name);
  const busy = create.isPending || update.isPending || remove.isPending;
  const model = usesModel(spec);

  const loadExample = (ex: StrategyExample) => {
    setSpec(specFromConfig(ex.config as Record<string, unknown>));
    if (!name) setName(ex.id.replace(/_/g, " "));
    setDescription(describeExample(ex));
  };

  const save = async () => {
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      strategy_type: (model ? "ml_signal" : "rule_based") as "ml_signal" | "rule_based",
      config: configFromSpec(spec),
    };
    try {
      const saved = strategy ? await update.mutateAsync({ id: strategy.id, body }) : await create.mutateAsync(body);
      addToast({ tone: "good", title: strategy ? "Strategy updated" : "Strategy created", body: saved.name });
      onSaved(saved);
    } catch (e) {
      addToast({ tone: "critical", title: "Could not save strategy", body: (e as Error).message });
    }
  };

  const del = async () => {
    if (!strategy || !window.confirm(`Delete "${strategy.name}" and its backtests?`)) return;
    try {
      await remove.mutateAsync(strategy.id);
      addToast({ tone: "neutral", title: "Strategy deleted", body: strategy.name });
      onDeleted();
    } catch (e) {
      addToast({ tone: "critical", title: "Could not delete", body: (e as Error).message });
    }
  };

  const patch = (p: Partial<StrategySpec>) => setSpec((s) => ({ ...s, ...p }));
  const shown = BLOCKS.filter((b) =>
    b.key === "entry_long" ? spec.side !== "short" : b.key === "entry_short" ? spec.side !== "long" : true,
  );
  const browsingTitle = BLOCKS.find((b) => b.key === browsing)?.title.toLowerCase();

  return (
    <Panel
      className="@container"
      icon={Workflow}
      title={strategy ? "Definition" : "New strategy"}
      subtitle={
        strategy
          ? `#${strategy.id} · updated ${new Date(strategy.updated_at).toLocaleString([], { hour12: false })}`
          : "rules over the live feature catalog"
      }
      actions={
        <>
          {model && <Badge tone="brand">uses the model</Badge>}
          {examples.data && (
            <Select
              value=""
              onChange={(e) => {
                const ex = examples.data.find((x) => x.id === e.target.value);
                if (ex) loadExample(ex);
              }}
              className="h-8 w-auto text-meta"
              aria-label="Load a template"
            >
              <option value="">Template…</option>
              {examples.data.map((ex) => (
                <option key={ex.id} value={ex.id}>
                  {ex.id.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          )}
          {strategy && (
            <Button variant="ghost" icon onClick={del} disabled={busy} aria-label="Delete strategy">
              <Trash2 size={15} />
            </Button>
          )}
          <Button variant="primary" onClick={save} disabled={busy || errors.length > 0}>
            <Save size={14} /> {strategy ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <div className="grid gap-3 @xl:grid-cols-[1fr_2fr]">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="OFI momentum" maxLength={100} />
        </Field>
        <Field label="Description">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="the edge it is after" maxLength={500} />
        </Field>
      </div>

      <Divider className="my-4" />

      <div className="grid grid-cols-2 gap-3 @lg:grid-cols-3">
        <Field as="div" label="Side" className="col-span-2 @lg:col-span-3">
          <SegmentedControl<StrategySpec["side"]>
            label="Side"
            value={spec.side}
            onChange={(side) => patch({ side })}
            items={[
              { value: "both", label: "Long and short" },
              { value: "long", label: "Long only" },
              { value: "short", label: "Short only" },
            ]}
          />
        </Field>
        <NumberField
          label="Size"
          unit="% of equity"
          value={spec.size_pct}
          onChange={(v) => patch({ size_pct: v ?? 0 })}
          min={1}
          nullable={false}
        />
        <NumberField
          label="Stop loss"
          unit="bps"
          value={spec.stop_loss_bps}
          onChange={(v) => patch({ stop_loss_bps: v })}
          min={0.1}
          hint="on the bar low / high"
        />
        <NumberField
          label="Take profit"
          unit="bps"
          value={spec.take_profit_bps}
          onChange={(v) => patch({ take_profit_bps: v })}
          min={0.1}
        />
        <NumberField label="Max hold" unit="s" value={spec.max_hold_s} onChange={(v) => patch({ max_hold_s: v })} min={1} />
        <NumberField
          label="Cooldown"
          unit="s"
          value={spec.cooldown_s}
          onChange={(v) => patch({ cooldown_s: v ?? 0 })}
          min={0}
          nullable={false}
          hint="after an exit"
        />
      </div>

      <Divider className="my-4" />

      <div className="space-y-5">
        {shown.map((b) => (
          <section key={b.key} aria-label={b.title}>
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className={`h-2 w-2 shrink-0 self-center rounded-full ${b.dot}`} aria-hidden />
              <h3 className="text-ui font-medium text-ink">{b.title}</h3>
              <span className="num min-w-0 truncate text-caption text-ink-faint">{describe(spec[b.key])}</span>
            </div>
            <ConditionEditor
              value={spec[b.key]}
              onChange={(c) => patch({ [b.key]: c })}
              fields={fields}
              onBrowse={() => setBrowsing(b.key)}
              emptyLabel={b.empty}
            />
          </section>
        ))}
      </div>

      {errors.length > 0 && (
        <div role="alert" className="mt-5 rounded-lg border border-critical/40 bg-critical/10 px-3 py-2 text-meta text-ink">
          <ul className="space-y-1">
            {errors.map((e) => (
              <li key={e} className="flex items-start gap-2">
                <CircleAlert size={14} className="mt-0.5 shrink-0 text-critical" aria-hidden />
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="hint mt-4 flex items-start gap-1.5">
        <Wand2 size={13} className="mt-0.5 shrink-0" aria-hidden /> Conditions are evaluated on closed 1-second bars; fills happen at the
        next bar&apos;s open, with slippage and commission.
      </p>

      <Drawer
        open={browsing != null}
        onClose={() => setBrowsing(null)}
        title="Feature catalog"
        subtitle={browsingTitle ? `adds to: ${browsingTitle}` : undefined}
      >
        <FeatureCatalog
          fields={fields}
          onPick={(f) => {
            if (browsing) patch({ [browsing]: addLeaf(spec[browsing], leafFor(fields, f)) });
            setBrowsing(null);
          }}
        />
      </Drawer>
    </Panel>
  );
}
