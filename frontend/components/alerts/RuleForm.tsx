"use client";

import { Save } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { Button, Drawer, Field, Input, Select, Switch } from "@/components/ds";
import { useAlertMutations, useCatalog, type AlertRule, type AlertRuleCreate } from "@/lib/api/hooks";
import { useConnection, useStore } from "@/lib/store";

const COMPARISONS: { v: AlertRuleCreate["comparison"]; label: string }[] = [
  { v: "gt", label: "> greater than" },
  { v: "gte", label: "≥ at least" },
  { v: "lt", label: "< less than" },
  { v: "lte", label: "≤ at most" },
  { v: "eq", label: "= equals" },
];
const PRIORITIES: AlertRuleCreate["priority"][] = ["critical", "high", "medium", "low", "info"];

const PRESETS: { label: string; draft: Partial<Draft> }[] = [
  {
    label: "Spread blow-out",
    draft: { name: "Spread blow-out", condition_field: "spread_z", comparison: "gt", threshold: 2, priority: "high", cooldown_seconds: 60 },
  },
  {
    label: "Velocity spike",
    draft: {
      name: "Velocity spike",
      condition_field: "velocity_z",
      comparison: "gt",
      threshold: 2.5,
      priority: "medium",
      cooldown_seconds: 60,
    },
  },
  {
    label: "Buy-flow surge",
    draft: { name: "Buy-flow surge", condition_field: "ofi_z", comparison: "gt", threshold: 2, priority: "medium", cooldown_seconds: 45 },
  },
  {
    label: "Sell-flow surge",
    draft: { name: "Sell-flow surge", condition_field: "ofi_z", comparison: "lt", threshold: -2, priority: "medium", cooldown_seconds: 45 },
  },
  {
    label: "Liquidity draining",
    draft: {
      name: "Liquidity draining",
      condition_field: "liquidity_z",
      comparison: "lt",
      threshold: -2,
      priority: "high",
      cooldown_seconds: 120,
    },
  },
  {
    label: "Model bullish",
    draft: { name: "Model bullish", condition_field: "p_up", comparison: "gt", threshold: 0.6, priority: "low", cooldown_seconds: 120 },
  },
];

type Draft = {
  name: string;
  condition_field: string;
  comparison: AlertRuleCreate["comparison"];
  threshold: number;
  priority: AlertRuleCreate["priority"];
  cooldown_seconds: number;
  notify_discord: boolean;
  message_template: string;
};

function draftFrom(rule: AlertRule | null): Draft {
  return {
    name: rule?.name ?? "",
    condition_field: rule?.condition_field ?? "spread_z",
    comparison: (rule?.comparison as Draft["comparison"]) ?? "gt",
    threshold: rule?.threshold ?? 2,
    priority: (rule?.priority as Draft["priority"]) ?? "medium",
    cooldown_seconds: rule?.cooldown_seconds ?? 60,
    notify_discord: rule?.notify_discord ?? false,
    message_template: rule?.message_template ?? "",
  };
}

/** Create or edit an alert rule in a side sheet. */
export function RuleDrawer({
  rule,
  open,
  onClose,
  discordConfigured,
}: {
  rule: AlertRule | null;
  open: boolean;
  onClose: () => void;
  discordConfigured: boolean;
}) {
  const catalog = useCatalog();
  const conn = useConnection();
  const addToast = useStore((s) => s.addToast);
  const { create, update } = useAlertMutations();
  const [d, setD] = useState<Draft>(() => draftFrom(rule));
  const patch = (p: Partial<Draft>) => setD((x) => ({ ...x, ...p }));
  const formId = useId();

  const numericFields = useMemo(() => (catalog.data ?? []).filter((f) => f.kind !== "categorical"), [catalog.data]);
  const groups = useMemo(() => {
    const m = new Map<string, typeof numericFields>();
    for (const f of numericFields) m.set(f.group, [...(m.get(f.group) ?? []), f]);
    return [...m.entries()];
  }, [numericFields]);
  const spec = numericFields.find((f) => f.name === d.condition_field);
  const busy = create.isPending || update.isPending;
  const valid = d.name.trim().length > 0 && Number.isFinite(d.threshold) && d.cooldown_seconds >= 0;

  const submit = async () => {
    if (!valid || busy) return;
    const body = {
      name: d.name.trim(),
      condition_field: d.condition_field,
      comparison: d.comparison,
      threshold: d.threshold,
      priority: d.priority,
      cooldown_seconds: d.cooldown_seconds,
      notify_discord: d.notify_discord,
      message_template: d.message_template.trim() || null,
    };
    try {
      if (rule) await update.mutateAsync({ id: rule.id, body });
      else await create.mutateAsync({ ...body, notify_email: false, symbol: conn.symbol, alert_type: "threshold" });
      addToast({ tone: "good", title: rule ? "Rule updated" : "Rule created", body: body.name });
      onClose();
    } catch (e) {
      addToast({ tone: "critical", title: "Could not save rule", body: (e as Error).message });
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={rule ? `Edit rule #${rule.id}` : "New alert rule"}
      subtitle={`checked every second on ${rule?.symbol ?? conn.symbol}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form={formId} variant="primary" disabled={busy || !valid}>
            <Save size={14} /> {rule ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        className="space-y-5"
      >
        {!rule && (
          <fieldset>
            <legend className="field-label mb-2">Start from a preset</legend>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button key={p.label} type="button" className="badge" onClick={() => patch(p.draft)}>
                  {p.label}
                </button>
              ))}
            </div>
          </fieldset>
        )}
        <Field label="Name">
          <Input value={d.name} onChange={(e) => patch({ name: e.target.value })} placeholder="Spread blow-out" maxLength={100} />
        </Field>
        <fieldset className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr]">
          <legend className="field-label mb-2">Fires when</legend>
          <Field label="Feature" hint={spec?.description}>
            <Select value={d.condition_field} onChange={(e) => patch({ condition_field: e.target.value })}>
              {groups.map(([g, fs]) => (
                <optgroup key={g} label={g}>
                  {fs.map((f) => (
                    <option key={f.name} value={f.name}>
                      {f.label} {f.unit ? `(${f.unit})` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Comparison">
            <Select value={d.comparison} onChange={(e) => patch({ comparison: e.target.value as Draft["comparison"] })}>
              {COMPARISONS.map((c) => (
                <option key={c.v} value={c.v}>
                  {c.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={`Threshold${spec?.unit ? ` (${spec.unit})` : ""}`}>
            <Input
              type="number"
              step="any"
              className="num"
              value={d.threshold}
              onChange={(e) => patch({ threshold: Number(e.target.value) })}
            />
          </Field>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Priority">
            <Select value={d.priority} onChange={(e) => patch({ priority: e.target.value as Draft["priority"] })}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Cooldown (s)" hint="the least time between firings">
            <Input
              type="number"
              min={0}
              className="num"
              value={d.cooldown_seconds}
              onChange={(e) => patch({ cooldown_seconds: Number(e.target.value) })}
            />
          </Field>
        </div>
        <Field label="Message" hint="placeholders: {value} {threshold} {field} {symbol}; leave empty for the default">
          <Input
            value={d.message_template}
            onChange={(e) => patch({ message_template: e.target.value })}
            placeholder="{symbol} spread z-score hit {value:.2f} (limit {threshold})"
            maxLength={500}
          />
        </Field>
        <Field
          as="div"
          label="Discord"
          hint={discordConfigured ? "the webhook is configured on the server" : "set DISCORD_WEBHOOK_URL on the backend to deliver"}
        >
          <Switch
            checked={d.notify_discord}
            onChange={(v) => patch({ notify_discord: v })}
            label="Notify on Discord"
            disabled={!discordConfigured && !d.notify_discord}
          />
        </Field>
      </form>
    </Drawer>
  );
}
