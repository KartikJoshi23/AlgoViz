/**
 * AlgoViz — Zustand Store
 *
 * Central state management for market data, connection status,
 * toast notifications, and user preferences.
 */

import { create } from 'zustand';

export interface MarketFeatures {
  symbol: string;
  current_price: number;
  mid_price: number;
  spread: number;
  spread_bps: number;
  vwap: number;
  twap: number;
  imbalance: number;
  imbalance_pct: number;
  volatility_bps: number;
  velocity: number;
  velocity_baseline: number;
  buy_pressure: number;
  price_change: number;
  price_change_pct: number;
  price_vs_vwap: number;
  best_bid: number;
  best_ask: number;
  bid_volume: number;
  ask_volume: number;
  timestamp: string | null;
}

export interface Insight {
  rule_id: number;
  priority: string;
  priority_emoji: string;
  insight: string;
  action: string;
  how_to_overcome: string;
  expected_impact: string;
  triggered_at: string;
}

export interface Trade {
  price: number;
  quantity: number;
  is_buyer_maker: boolean;
  trade_id: number;
  timestamp: string;
}

export interface Alert {
  id: number;
  priority: string;
  message: string;
  triggered_at: string;
  acknowledged: boolean;
}

export interface OrderBookLevel {
  price: number;
  quantity: number;
}

export interface Toast {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message?: string;
  duration?: number;
  createdAt: number;
}

interface AppState {
  // Connection
  connected: boolean;
  wsStatus: 'connecting' | 'connected' | 'disconnected';

  // Market Data
  features: MarketFeatures;
  trades: Trade[];
  insights: Insight[];
  alerts: Alert[];

  // Chart Histories
  priceHistory: { timestamp: string; price: number; vwap: number }[];
  spreadHistory: { timestamp: string; spread_bps: number }[];
  volatilityHistory: { timestamp: string; volatility_bps: number }[];

  // Order Book
  orderBook: { bids: OrderBookLevel[]; asks: OrderBookLevel[] };

  // UI
  sidebarExpanded: boolean;
  theme: 'dark' | 'light';
  commandPaletteOpen: boolean;

  // Toasts
  toasts: Toast[];

  // Actions
  setConnected: (connected: boolean) => void;
  setWsStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  updateFeatures: (features: MarketFeatures) => void;
  addTrade: (trade: Trade) => void;
  setInsights: (insights: Insight[]) => void;
  addAlert: (alert: Alert) => void;
  setOrderBook: (book: { bids: OrderBookLevel[]; asks: OrderBookLevel[] }) => void;
  addPricePoint: (point: { timestamp: string; price: number; vwap: number }) => void;
  toggleSidebar: () => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  addToast: (toast: Omit<Toast, 'id' | 'createdAt'>) => void;
  removeToast: (id: string) => void;
}

const defaultFeatures: MarketFeatures = {
  symbol: 'BTCUSDT',
  current_price: 0,
  mid_price: 0,
  spread: 0,
  spread_bps: 0,
  vwap: 0,
  twap: 0,
  imbalance: 0,
  imbalance_pct: 0,
  volatility_bps: 0,
  velocity: 0,
  velocity_baseline: 20,
  buy_pressure: 0.5,
  price_change: 0,
  price_change_pct: 0,
  price_vs_vwap: 0,
  best_bid: 0,
  best_ask: 0,
  bid_volume: 0,
  ask_volume: 0,
  timestamp: null,
};

let _toastId = 0;

export const useStore = create<AppState>((set) => ({
  connected: false,
  wsStatus: 'disconnected',
  features: defaultFeatures,
  trades: [],
  insights: [],
  alerts: [],
  priceHistory: [],
  spreadHistory: [],
  volatilityHistory: [],
  orderBook: { bids: [], asks: [] },
  sidebarExpanded: true,
  theme: 'dark',
  commandPaletteOpen: false,
  toasts: [],

  setConnected: (connected) => set({ connected }),
  setWsStatus: (status) => set({ wsStatus: status }),

  updateFeatures: (features) =>
    set((state) => {
      const ts = features.timestamp || new Date().toISOString();
      return {
        features,
        priceHistory: [
          ...state.priceHistory.slice(-199),
          { timestamp: ts, price: features.current_price, vwap: features.vwap },
        ],
        spreadHistory: [
          ...state.spreadHistory.slice(-99),
          { timestamp: ts, spread_bps: features.spread_bps },
        ],
        volatilityHistory: [
          ...state.volatilityHistory.slice(-99),
          { timestamp: ts, volatility_bps: features.volatility_bps },
        ],
      };
    }),

  addTrade: (trade) =>
    set((state) => ({
      trades: [...state.trades.slice(-99), trade],
    })),

  setInsights: (insights) => set({ insights }),

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts.slice(0, 49)],
    })),

  setOrderBook: (book) => set({ orderBook: book }),

  addPricePoint: (point) =>
    set((state) => ({
      priceHistory: [...state.priceHistory.slice(-199), point],
    })),

  toggleSidebar: () =>
    set((state) => ({ sidebarExpanded: !state.sidebarExpanded })),

  toggleTheme: () =>
    set((state) => {
      const next = state.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      return { theme: next };
    }),

  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),

  addToast: (toast) =>
    set((state) => ({
      toasts: [
        ...state.toasts.slice(-4),
        { ...toast, id: `toast-${++_toastId}`, createdAt: Date.now() },
      ],
    })),

  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
}));
