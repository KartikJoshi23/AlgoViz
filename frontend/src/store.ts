/**
 * AlgoViz — Zustand Store
 *
 * Central state management for market data, connection status,
 * and user preferences.
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

interface AppState {
  // Connection
  connected: boolean;
  wsStatus: 'connecting' | 'connected' | 'disconnected';

  // Market Data
  features: MarketFeatures;
  trades: Trade[];
  insights: Insight[];
  alerts: Alert[];

  // Price History (for chart)
  priceHistory: { timestamp: string; price: number; vwap: number }[];

  // UI
  sidebarExpanded: boolean;
  theme: 'dark' | 'light';

  // Actions
  setConnected: (connected: boolean) => void;
  setWsStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  updateFeatures: (features: MarketFeatures) => void;
  addTrade: (trade: Trade) => void;
  setInsights: (insights: Insight[]) => void;
  addAlert: (alert: Alert) => void;
  addPricePoint: (point: { timestamp: string; price: number; vwap: number }) => void;
  toggleSidebar: () => void;
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

export const useStore = create<AppState>((set) => ({
  connected: false,
  wsStatus: 'disconnected',
  features: defaultFeatures,
  trades: [],
  insights: [],
  alerts: [],
  priceHistory: [],
  sidebarExpanded: true,
  theme: 'dark',

  setConnected: (connected) => set({ connected }),
  setWsStatus: (status) => set({ wsStatus: status }),

  updateFeatures: (features) =>
    set((state) => ({
      features,
      priceHistory: [
        ...state.priceHistory.slice(-199),
        {
          timestamp: features.timestamp || new Date().toISOString(),
          price: features.current_price,
          vwap: features.vwap,
        },
      ],
    })),

  addTrade: (trade) =>
    set((state) => ({
      trades: [...state.trades.slice(-99), trade],
    })),

  setInsights: (insights) => set({ insights }),

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts.slice(0, 49)],
    })),

  addPricePoint: (point) =>
    set((state) => ({
      priceHistory: [...state.priceHistory.slice(-199), point],
    })),

  toggleSidebar: () =>
    set((state) => ({ sidebarExpanded: !state.sidebarExpanded })),
}));
