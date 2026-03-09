/**
 * AlgoViz — Settings Page
 *
 * App preferences, theme toggle, connection info, and about section.
 */

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Settings as SettingsIcon, Sun, Moon, Wifi, WifiOff, Info, Monitor } from 'lucide-react';
import { useStore } from '../store';

export function SettingsPage() {
    const theme = useStore((s) => s.theme);
    const connected = useStore((s) => s.connected);
    const wsStatus = useStore((s) => s.wsStatus);

    return (
        <div>
            <div className="page-header">
                <h1 className="page-title">
                    <SettingsIcon size={24} style={{ marginRight: 10, verticalAlign: 'middle' }} />
                    Settings
                </h1>
                <p className="page-subtitle">Configure your trading preferences</p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 700 }}>
                <AppearanceSection theme={theme} />
                <ConnectionSection connected={connected} wsStatus={wsStatus} />
                <PreferencesSection />
                <AboutSection />
            </div>
        </div>
    );
}

function AppearanceSection({ theme }: { theme: string }) {
    const [currentTheme, setCurrentTheme] = useState(theme);

    const toggleTheme = (newTheme: string) => {
        setCurrentTheme(newTheme);
        // Apply theme to document
        document.documentElement.setAttribute('data-theme', newTheme);
    };

    const themes = [
        { value: 'dark', label: 'Dark', icon: <Moon size={18} />, color: '#8b5cf6' },
        { value: 'light', label: 'Light', icon: <Sun size={18} />, color: '#f59e0b' },
        { value: 'system', label: 'System', icon: <Monitor size={18} />, color: '#06b6d4' },
    ];

    return (
        <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <div className="card-header">
                <div className="card-title">🎨 Appearance</div>
            </div>
            <div style={{ padding: '8px 0' }}>
                <div style={{ marginBottom: 12, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Theme
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                    {themes.map(t => (
                        <button
                            key={t.value}
                            onClick={() => toggleTheme(t.value)}
                            style={{
                                flex: 1, padding: '14px 16px', borderRadius: 10, cursor: 'pointer',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                                border: currentTheme === t.value ? `2px solid ${t.color}` : '2px solid var(--border-color)',
                                background: currentTheme === t.value ? `${t.color}15` : 'var(--bg-secondary)',
                                color: currentTheme === t.value ? t.color : 'var(--text-secondary)',
                                fontWeight: currentTheme === t.value ? 700 : 500,
                                fontSize: '0.88rem',
                                transition: 'all 0.2s ease',
                            }}
                        >
                            {t.icon} {t.label}
                        </button>
                    ))}
                </div>
            </div>
        </motion.div>
    );
}

function ConnectionSection({ connected, wsStatus }: { connected: boolean; wsStatus: string }) {
    const wsUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
        connected: { color: '#10b981', icon: <Wifi size={18} />, label: 'Connected' },
        connecting: { color: '#f59e0b', icon: <Wifi size={18} />, label: 'Connecting…' },
        disconnected: { color: '#ef4444', icon: <WifiOff size={18} />, label: 'Disconnected' },
    };

    const cfg = statusConfig[wsStatus] || statusConfig.disconnected;

    return (
        <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <div className="card-header">
                <div className="card-title">🔌 Connection</div>
                <span className="badge" style={{ background: `${cfg.color}20`, color: cfg.color }}>
                    {cfg.label}
                </span>
            </div>
            <div style={{ padding: '8px 0' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '10px 16px', fontSize: '0.85rem' }}>
                    <div style={{ color: 'var(--text-muted)' }}>API URL</div>
                    <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{wsUrl}</div>

                    <div style={{ color: 'var(--text-muted)' }}>WebSocket</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ color: cfg.color }}>{cfg.icon}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', color: cfg.color }}>{wsStatus}</span>
                    </div>

                    <div style={{ color: 'var(--text-muted)' }}>Exchange</div>
                    <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>Binance (BTC/USDT)</div>

                    <div style={{ color: 'var(--text-muted)' }}>Market Feed</div>
                    <div style={{ fontFamily: 'var(--font-mono)', color: connected ? '#10b981' : '#ef4444' }}>
                        {connected ? '● Streaming' : '○ Offline'}
                    </div>
                </div>
            </div>
        </motion.div>
    );
}

function PreferencesSection() {
    const [chartWindow, setChartWindow] = useState('120');
    const [refreshRate, setRefreshRate] = useState('500');

    return (
        <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <div className="card-header">
                <div className="card-title">⚙️ Preferences</div>
            </div>
            <div style={{ padding: '8px 0', display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                    <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 6 }}>
                        Chart Window (seconds)
                    </label>
                    <input
                        type="number" value={chartWindow} onChange={(e) => setChartWindow(e.target.value)}
                        min="30" max="3600" step="30"
                        style={{
                            width: 160, padding: '8px 12px', background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-color)', borderRadius: 8,
                            color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.85rem',
                        }}
                    />
                    <span style={{ marginLeft: 10, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        ({(parseInt(chartWindow) / 60).toFixed(1)} min)
                    </span>
                </div>
                <div>
                    <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 6 }}>
                        Data Refresh Rate (ms)
                    </label>
                    <div style={{ display: 'flex', gap: 8 }}>
                        {['250', '500', '1000', '2000'].map(r => (
                            <button
                                key={r}
                                onClick={() => setRefreshRate(r)}
                                style={{
                                    padding: '6px 14px', borderRadius: 6, fontSize: '0.82rem', cursor: 'pointer',
                                    border: refreshRate === r ? '2px solid #06b6d4' : '2px solid var(--border-color)',
                                    background: refreshRate === r ? 'rgba(6, 182, 212, 0.12)' : 'transparent',
                                    color: refreshRate === r ? '#06b6d4' : 'var(--text-secondary)',
                                    fontFamily: 'var(--font-mono)', fontWeight: 600,
                                }}
                            >
                                {r}ms
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </motion.div>
    );
}

function AboutSection() {
    const techStack = [
        { label: 'Frontend', value: 'React 18 + Vite + TypeScript' },
        { label: 'Charts', value: 'TradingView Lightweight Charts' },
        { label: 'State', value: 'Zustand + TanStack Query' },
        { label: 'Backend', value: 'FastAPI + SQLAlchemy + SQLite' },
        { label: 'ML Engine', value: 'scikit-learn + SHAP' },
        { label: 'Real-Time', value: 'WebSocket + Binance API' },
    ];

    return (
        <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <div className="card-header">
                <div className="card-title">
                    <Info size={16} style={{ marginRight: 6 }} />
                    About AlgoViz
                </div>
                <span className="badge badge-cyan" style={{ fontSize: '0.72rem' }}>v2.0.0</span>
            </div>
            <div style={{ padding: '8px 0' }}>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.6, marginBottom: 16 }}>
                    Professional-grade algorithmic trading intelligence platform. Real-time market data,
                    AI-powered predictions, and on-chain analytics — all built with free, open-source tools.
                </p>
                <div style={{
                    display: 'grid', gridTemplateColumns: '120px 1fr', gap: '8px 16px',
                    padding: '12px 16px', background: 'var(--bg-secondary)', borderRadius: 8, fontSize: '0.82rem',
                }}>
                    {techStack.map((item, i) => (
                        <div key={i} style={{ display: 'contents' }}>
                            <div style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{item.label}</div>
                            <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{item.value}</div>
                        </div>
                    ))}
                </div>
            </div>
        </motion.div>
    );
}
