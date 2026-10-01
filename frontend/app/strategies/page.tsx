"use client";

import { BookMarked, FlaskConical, LayoutTemplate, Plus, Search } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Input, Panel, Skeleton } from "@/components/ds";
import { BacktestSection } from "@/components/strategies/BacktestSection";
import { StrategyEditor } from "@/components/strategies/StrategyEditor";
import { EmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useStrategies, useStrategyExamples, type Strategy, type StrategyExample } from "@/lib/api/hooks";

const TEMPLATE_TITLE: Record<string, string> = {
  ofi_momentum: "OFI momentum",
  queue_imbalance_scalp: "Queue-imbalance scalp",
  model_signal: "Model signal",
};
const TEMPLATE_BLURB: Record<string, string> = {
  ofi_momentum:
    "Follow order-flow imbalance when it leaves its baseline by 1.5σ, outside calm markets. Stop 15 bps, target 30 bps, 30-bar time stop.",
  queue_imbalance_scalp:
    "Lean on the touch: enter when L1 queue imbalance exceeds ±0.8, hold at most 10 s. Tight 3 bps target, 5 bps stop.",
  model_signal:
    "Trade the calibrated model: go with the side whose probability clears 0.5 while the other stays under 0.3. 30 s max hold, 10 bps stop.",
};
const templateTitle = (id: string) => TEMPLATE_TITLE[id] ?? id.replace(/_/g, " ");

function TemplateGallery({ onPick, className }: { onPick: (ex: StrategyExample) => void; className?: string }) {
  const examples = useStrategyExamples();
  return (
    <Panel
      className={className}
      icon={LayoutTemplate}
      title="Start from a template"
      subtitle="complete strategies in the shared condition language"
    >
      <div className="grid gap-3 md:grid-cols-3">
        {(examples.data ?? []).map((ex) => {
          const d = ex.description as Record<string, string | null>;
          return (
            <button key={ex.id} type="button" onClick={() => onPick(ex)} className="raised flex flex-col gap-2 p-4 text-left">
              <span className="flex items-center gap-2">
                <span className="text-ui font-medium text-ink">{templateTitle(ex.id)}</span>
                <Badge tone={ex.id === "model_signal" ? "brand" : "neutral"} className="ml-auto">
                  {ex.id === "model_signal" ? "model" : "rules"}
                </Badge>
              </span>
              <span className="text-meta leading-snug text-ink-muted">{TEMPLATE_BLURB[ex.id] ?? ""}</span>
              <span className="num mt-auto pt-1 text-caption text-ink-faint">{d.entry_long ?? d.entry_short ?? ""}</span>
            </button>
          );
        })}
        {examples.isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-32" />)}
      </div>
    </Panel>
  );
}

/** Saved strategies (searchable) and the templates to start a new one from. */
function Library({
  rows,
  loading,
  failed,
  selectedId,
  onSelect,
  onTemplate,
}: {
  rows: Strategy[];
  loading: boolean;
  failed: boolean;
  selectedId: number | "new" | null;
  onSelect: (id: number) => void;
  onTemplate: (ex: StrategyExample) => void;
}) {
  const examples = useStrategyExamples();
  const [q, setQ] = useState("");
  const shown = rows.filter((s) => s.name.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <Panel className="self-start lg:sticky lg:top-[72px]" icon={BookMarked} title="Library" subtitle={`${rows.length} saved`}>
      {rows.length > 4 && (
        <label className="relative mb-3 block">
          <span className="sr-only">Search saved strategies</span>
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search" className="pl-8" />
        </label>
      )}
      {loading && <Skeleton className="h-24" />}
      {failed && <p className="text-meta text-ink">Could not load strategies.</p>}
      {rows.length === 0 && !loading && <p className="text-meta text-ink-faint">Nothing saved yet.</p>}
      <ul className="space-y-px">
        {shown.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onSelect(s.id)}
              aria-current={s.id === selectedId}
              className="row flex w-full flex-col gap-0.5 px-2.5 py-2 text-left"
            >
              <span className="flex items-center gap-2">
                <span className="truncate text-body text-ink">{s.name}</span>
                <Badge tone={s.strategy_type === "ml_signal" ? "brand" : "neutral"} className="ml-auto">
                  {s.strategy_type === "ml_signal" ? "model" : "rules"}
                </Badge>
              </span>
              {s.description && <span className="line-clamp-1 text-caption text-ink-faint">{s.description}</span>}
            </button>
          </li>
        ))}
      </ul>
      {(examples.data?.length ?? 0) > 0 && (
        <>
          <h3 className="col-head mb-1.5 mt-4">New from a template</h3>
          <ul className="space-y-px">
            {examples.data!.map((ex) => (
              <li key={ex.id}>
                <button
                  type="button"
                  onClick={() => onTemplate(ex)}
                  className="row flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-body text-ink-muted hover:text-ink"
                >
                  <Plus size={13} aria-hidden /> {templateTitle(ex.id)}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

export default function StrategiesPage() {
  const strategies = useStrategies();
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [template, setTemplate] = useState<StrategyExample | null>(null);
  const rows = strategies.data ?? [];
  const effectiveId: number | "new" | null = selectedId ?? rows[0]?.id ?? null;
  const selected = typeof effectiveId === "number" ? (rows.find((s) => s.id === effectiveId) ?? null) : null;
  const startNew = (ex: StrategyExample | null) => {
    setTemplate(ex);
    setSelectedId("new");
  };

  return (
    <div className="space-y-3">
      <PageHeader
        eyebrow="Research"
        title="Strategies"
        subtitle="declarative entries and exits on the live feature catalog · event-driven backtests on 1-second bars"
        actions={
          <Button variant="primary" onClick={() => startNew(null)}>
            <Plus size={14} /> New strategy
          </Button>
        }
      />

      <div className="grid gap-3 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_minmax(0,1.15fr)]">
        <Library
          rows={rows}
          loading={strategies.isLoading}
          failed={strategies.isError}
          selectedId={effectiveId}
          onSelect={setSelectedId}
          onTemplate={startNew}
        />

        {effectiveId === "new" && (
          <>
            <StrategyEditor
              key={`new:${template?.id ?? "blank"}`}
              strategy={null}
              template={template}
              onSaved={(s) => setSelectedId(s.id)}
              onDeleted={() => setSelectedId(null)}
            />
            <div className="self-start lg:col-start-2 xl:col-start-auto">
              <EmptyState
                title={
                  <span className="flex items-center gap-2">
                    <FlaskConical size={16} aria-hidden /> Results appear here
                  </span>
                }
                body="Create the strategy, then run a backtest on recorded 1-second bars to see its equity, drawdown and trades."
              />
            </div>
          </>
        )}
        {selected && (
          <>
            <StrategyEditor
              key={`${selected.id}:${selected.updated_at}`}
              strategy={selected}
              onSaved={(s) => setSelectedId(s.id)}
              onDeleted={() => setSelectedId(null)}
            />
            <div className="lg:col-start-2 xl:col-start-auto">
              <BacktestSection strategyId={selected.id} />
            </div>
          </>
        )}
        {effectiveId === null && !strategies.isLoading && <TemplateGallery className="self-start xl:col-span-2" onPick={startNew} />}
      </div>
    </div>
  );
}
