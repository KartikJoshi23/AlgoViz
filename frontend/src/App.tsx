/**
 * AlgoViz — Main Application
 *
 * Root component with routing, WebSocket connection,
 * top navbar layout, command palette, and toast notifications.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navbar } from './components/Navbar';
import { DashboardPage } from './pages/Dashboard';
import { AnalyticsPage } from './pages/Analytics';
import { StrategiesPage } from './pages/Strategies';
import { AlertsPage } from './pages/Alerts';
import { OnChainPage } from './pages/OnChain';
import { SettingsPage } from './pages/Settings';
import { useWebSocket } from './hooks/useWebSocket';
import { CommandPalette } from './components/CommandPalette';
import { ToastProvider } from './components/ToastProvider';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5000,
    },
  },
});

function AppContent() {
  // Establish WebSocket connection
  useWebSocket();

  return (
    <div className="app-layout">
      <Navbar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/strategies" element={<StrategiesPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/onchain" element={<OnChainPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
      <CommandPalette />
      <ToastProvider />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
