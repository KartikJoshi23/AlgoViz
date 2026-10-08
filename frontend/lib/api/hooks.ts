"use client";

/**
 * TanStack Query hooks over the typed client. Every hook returns the
 * generated response type — nothing is hand-declared.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useHydrationDone } from "@/lib/useHydrationDone";

import { api, type components } from "./client";

type S = components["schemas"];
export type FeatureCatalogEntry = S["FeatureCatalogEntry"];
export type Strategy = S["StrategyResponse"];
export type StrategyExample = S["StrategyExample"];
export type Backtest = S["BacktestResponse"];
export type BacktestDetail = S["BacktestDetailResponse"];
export type AlertRule = S["AlertRuleResponse"];
export type AlertRuleCreate = S["AlertRuleCreate"];
export type AlertRuleUpdate = S["AlertRuleUpdate"];
export type AlertHistory = S["AlertHistoryResponse"];
export type ModelInfo = S["ModelInfoResponse"];
export type ModelRegistryEntry = S["ModelRegistryEntry"];
export type ShapResponse = S["ShapResponse"];
export type DriftResponse = S["DriftResponse"];
export type EdgeStudy = S["EdgeStudyResponse"];
export type SignalRule = S["SignalRuleResponse"];
export type HealthResponse = S["HealthResponse"];
export type BacktestTrade = S["BacktestTrade"];
export type SymbolStats = S["SymbolStats"];
export type SystemMetrics = S["SystemMetricsResponse"];
export type ReliabilityCurve = S["ReliabilityCurve"];
export type Access = S["AccessResponse"];
export type FoldMetrics = S["FoldMetricsResponse"];

export type Problem = S["Problem"];

/** A failed request, read from the server's RFC 9457 problem details. */
export class ApiError extends Error {
  status: number;
  problem: Problem | null;
  constructor(status: number, body: unknown) {
    const problem = isProblem(body) ? body : null;
    super(problemText(status, problem));
    this.status = status;
    this.problem = problem;
  }
}

function isProblem(body: unknown): body is Problem {
  return !!body && typeof body === "object" && typeof (body as { status?: unknown }).status === "number";
}

function problemText(status: number, p: Problem | null): string {
  if (status === 401) return "This server needs the admin token for changes: add it in Settings → Access.";
  if (p?.errors?.length) return p.errors.map((e) => `${e.loc.slice(1).join(".") || "request"}: ${e.msg}`).join("; ");
  return p?.detail ?? p?.title ?? `HTTP ${status}`;
}

function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.error !== undefined || !r.response.ok) throw new ApiError(r.response.status, r.error);
  return r.data as T;
}

// ── Queries ─────────────────────────────────────────────────────────

export const useCatalog = () =>
  useQuery({
    queryKey: ["catalog"],
    queryFn: async () => unwrap(await api.GET("/api/v1/market/feature-catalog")),
    staleTime: Infinity,
  });

export const useStrategies = () => useQuery({ queryKey: ["strategies"], queryFn: async () => unwrap(await api.GET("/api/v1/strategies")) });

export const useStrategyExamples = () =>
  useQuery({
    queryKey: ["strategy-examples"],
    queryFn: async () => unwrap(await api.GET("/api/v1/strategies/examples")),
    staleTime: Infinity,
  });

const isRunning = (status: string | undefined) => status === "running" || status === "pending";

export const useBacktests = (strategyId: number | null) =>
  useQuery({
    queryKey: ["backtests", strategyId],
    enabled: strategyId != null,
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/strategies/{strategy_id}/backtests", {
          params: { path: { strategy_id: strategyId! } },
          signal,
        }),
      ),
    // WS progress is the fast path; polling covers a frame that raced the first fetch
    refetchInterval: (q) => (q.state.data?.items.some((b) => isRunning(b.status)) ? 2_000 : false),
  });

export const useBacktestDetail = (strategyId: number | null, backtestId: number | null) =>
  useQuery({
    queryKey: ["backtest", strategyId, backtestId],
    enabled: strategyId != null && backtestId != null,
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/strategies/{strategy_id}/backtests/{backtest_id}", {
          params: { path: { strategy_id: strategyId!, backtest_id: backtestId! } },
          signal,
        }),
      ),
    refetchInterval: (q) => (isRunning(q.state.data?.status) ? 2_000 : false),
  });

export const useAlertRules = () =>
  useQuery({
    queryKey: ["alert-rules"],
    queryFn: async () => unwrap(await api.GET("/api/v1/alerts/rules")),
    refetchInterval: 15_000, // last_fired_at moves without a mutation
  });

/** Alert history, newest first, a page at a time (`fetchNextPage` loads older alerts). */
export const useAlertHistory = (opts: { limit?: number; priority?: string; unacknowledged_only?: boolean } = {}) =>
  useInfiniteQuery({
    queryKey: ["alert-history", opts],
    initialPageParam: null as number | null,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET("/api/v1/alerts/history", { params: { query: { ...opts, ...(pageParam ? { before: pageParam } : {}) } } })),
    getNextPageParam: (last) => last.next_before,
    refetchInterval: 15_000,
  });

/** Whether this server gates changes, and whether this browser's token passes. */
export const useAccess = () =>
  useQuery({ queryKey: ["access"], queryFn: async () => unwrap(await api.GET("/api/v1/auth/access")), staleTime: 60_000 });

export const useModelInfo = (symbol: string | null) =>
  useQuery({
    queryKey: ["model-info", symbol],
    queryFn: async () => unwrap(await api.GET("/api/v1/analytics/model-info", { params: { query: symbol ? { symbol } : {} } })),
    refetchInterval: 20_000,
  });

export const useModelRegistry = (symbol: string | null) =>
  useQuery({
    queryKey: ["model-registry", symbol],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/analytics/model-registry", {
          params: { query: { limit: 20, ...(symbol ? { symbol } : {}) } },
        }),
      ),
    refetchInterval: 30_000,
  });

export const useShap = (symbol: string | null, enabled = true) =>
  useQuery({
    queryKey: ["shap", symbol],
    enabled,
    queryFn: async () => unwrap(await api.GET("/api/v1/analytics/shap", { params: { query: symbol ? { symbol } : {} } })),
    refetchInterval: 10_000,
  });

export const useDrift = (symbol: string | null) =>
  useQuery({
    queryKey: ["drift", symbol],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/analytics/drift", {
          params: { query: { limit: 300, ...(symbol ? { symbol } : {}) } },
        }),
      ),
    refetchInterval: 10_000,
  });

/** The latest edge study on this host, and how far the bars that decide it have come. */
export const useEdgeStudy = (symbol: string | null) =>
  useQuery({
    queryKey: ["edge-study", symbol],
    queryFn: async () => unwrap(await api.GET("/api/v1/analytics/edge-study", { params: { query: symbol ? { symbol } : {} } })),
    refetchInterval: 60_000, // bars accrue at one a second; the study changes when someone runs it
  });

/** Active signals plus the engine's recent transitions — the history the live feed extends. */
export const useSignalHistory = (symbol: string | null) =>
  useQuery({
    queryKey: ["signal-history", symbol],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/analytics/signals", { params: { query: { limit: 200, ...(symbol ? { symbol } : {}) } } })),
    staleTime: 60_000,
  });

export const useSignalRules = (symbol: string | null) =>
  useQuery({
    queryKey: ["signal-rules", symbol],
    queryFn: async () => unwrap(await api.GET("/api/v1/analytics/signals/rules", { params: { query: symbol ? { symbol } : {} } })),
    refetchInterval: 10_000,
  });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: async () => unwrap(await api.GET("/health")), refetchInterval: 10_000 });

/**
 * The status bar (layout) and the settings page share this query. The layout
 * hydrates first and starts the poll, so the page can hydrate with data already
 * cached; until hydration is done it is reported as not yet loaded.
 */
export function useSystemMetrics() {
  const q = useQuery({
    queryKey: ["system-metrics"],
    queryFn: async () => unwrap(await api.GET("/api/v1/system/metrics")),
    refetchInterval: 5_000,
  });
  return useHydrationDone() ? q : { ...q, data: undefined };
}

export const useMarketStats = () =>
  useQuery({
    queryKey: ["market-stats"],
    queryFn: async () => unwrap(await api.GET("/api/v1/market/stats")),
    refetchInterval: 5_000,
  });

// ── Mutations ───────────────────────────────────────────────────────

export function useStrategyMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["strategies"] });
  const create = useMutation({
    mutationFn: async (body: S["StrategyCreate"]) => unwrap(await api.POST("/api/v1/strategies", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: S["StrategyUpdate"] }) =>
      unwrap(await api.PATCH("/api/v1/strategies/{strategy_id}", { params: { path: { strategy_id: id } }, body })),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      // stop polling the rows that are about to disappear (avoids 404s racing the delete)
      await Promise.all([qc.cancelQueries({ queryKey: ["backtests", id] }), qc.cancelQueries({ queryKey: ["backtest", id] })]);
      qc.removeQueries({ queryKey: ["backtests", id] });
      qc.removeQueries({ queryKey: ["backtest", id] });
      const out = unwrap(await api.DELETE("/api/v1/strategies/{strategy_id}", { params: { path: { strategy_id: id } } }));
      // drop it from the list immediately so nothing re-selects the dead row before the refetch lands
      qc.setQueryData<Strategy[]>(["strategies"], (old) => old?.filter((s) => s.id !== id));
      return out;
    },
    onSuccess: invalidate,
  });
  const backtest = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: S["BacktestRequest"] }) =>
      unwrap(
        await api.POST("/api/v1/strategies/{strategy_id}/backtest", {
          params: { path: { strategy_id: id } },
          body,
        }),
      ),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ["backtests", v.id] }),
  });
  return { create, update, remove, backtest };
}

export function useAlertMutations() {
  const qc = useQueryClient();
  const rules = () => qc.invalidateQueries({ queryKey: ["alert-rules"] });
  const history = () => qc.invalidateQueries({ queryKey: ["alert-history"] });
  const create = useMutation({
    mutationFn: async (body: AlertRuleCreate) => unwrap(await api.POST("/api/v1/alerts/rules", { body })),
    onSuccess: rules,
  });
  const update = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: AlertRuleUpdate }) =>
      unwrap(await api.PATCH("/api/v1/alerts/rules/{rule_id}", { params: { path: { rule_id: id } }, body })),
    onSuccess: rules,
  });
  const remove = useMutation({
    mutationFn: async (id: number) => unwrap(await api.DELETE("/api/v1/alerts/rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: rules,
  });
  const acknowledge = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.POST("/api/v1/alerts/history/{alert_id}/acknowledge", { params: { path: { alert_id: id } } })),
    onSuccess: history,
  });
  const acknowledgeAll = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/alerts/history/acknowledge-all")),
    onSuccess: history,
  });
  return { create, update, remove, acknowledge, acknowledgeAll };
}
