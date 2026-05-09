/**
 * AlgoViz — Command Palette (Ctrl+K)
 *
 * Glassmorphism overlay with fuzzy search — navigate anywhere instantly.
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    LayoutDashboard, BarChart3, GitBranch, Bell, Link, Settings,
    Moon, Sun, Search,
} from 'lucide-react';
import { useStore } from '../store';

interface PaletteCommand {
    id: string;
    label: string;
    section: string;
    icon: React.ReactNode;
    action: () => void;
    keywords?: string;
}

export function CommandPalette() {
    const open = useStore((s) => s.commandPaletteOpen);
    const setOpen = useStore((s) => s.setCommandPaletteOpen);
    const toggleTheme = useStore((s) => s.toggleTheme);
    const theme = useStore((s) => s.theme);

    const [query, setQuery] = useState('');
    const [selectedIdx, setSelectedIdx] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const navigate = useNavigate();

    const commands = useMemo<PaletteCommand[]>(() => [
        { id: 'nav-dashboard', label: 'Go to Dashboard', section: 'Navigation', icon: <LayoutDashboard size={16} />, action: () => { navigate('/'); setOpen(false); }, keywords: 'home main live' },
        { id: 'nav-analytics', label: 'Go to Analytics', section: 'Navigation', icon: <BarChart3 size={16} />, action: () => { navigate('/analytics'); setOpen(false); }, keywords: 'ml prediction shap model' },
        { id: 'nav-strategies', label: 'Go to Strategies', section: 'Navigation', icon: <GitBranch size={16} />, action: () => { navigate('/strategies'); setOpen(false); }, keywords: 'backtest trade algo' },
        { id: 'nav-alerts', label: 'Go to Alerts', section: 'Navigation', icon: <Bell size={16} />, action: () => { navigate('/alerts'); setOpen(false); }, keywords: 'notification warning' },
        { id: 'nav-onchain', label: 'Go to On-Chain', section: 'Navigation', icon: <Link size={16} />, action: () => { navigate('/onchain'); setOpen(false); }, keywords: 'blockchain foundry ethereum' },
        { id: 'nav-settings', label: 'Go to Settings', section: 'Navigation', icon: <Settings size={16} />, action: () => { navigate('/settings'); setOpen(false); }, keywords: 'config preferences' },
        { id: 'toggle-theme', label: `Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`, section: 'Actions', icon: theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />, action: () => { toggleTheme(); setOpen(false); }, keywords: 'theme mode color' },
    ], [navigate, setOpen, toggleTheme, theme]);

    const filtered = useMemo(() => {
        if (!query.trim()) return commands;
        const q = query.toLowerCase();
        return commands.filter((c) => {
            const text = `${c.label} ${c.keywords || ''} ${c.section}`.toLowerCase();
            return text.includes(q);
        });
    }, [commands, query]);

    // Reset selection when filter changes
    useEffect(() => {
        setSelectedIdx(0);
    }, [filtered.length]);

    // Global keyboard shortcut
    useEffect(() => {
        function handleKeyDown(e: KeyboardEvent) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                setOpen(!open);
            }
            if (e.key === 'Escape' && open) {
                setOpen(false);
            }
        }
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [open, setOpen]);

    // Focus input when opened
    useEffect(() => {
        if (open) {
            setQuery('');
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open]);

    function handleKeyNav(e: React.KeyboardEvent) {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSelectedIdx((i) => Math.max(i - 1, 0));
        } else if (e.key === 'Enter' && filtered[selectedIdx]) {
            filtered[selectedIdx].action();
        }
    }

    return (
        <AnimatePresence>
            {open && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        onClick={() => setOpen(false)}
                        style={{
                            position: 'fixed', inset: 0, zIndex: 10000,
                            background: 'rgba(0,0,0,0.6)',
                            backdropFilter: 'blur(4px)',
                        }}
                    />

                    {/* Palette */}
                    <motion.div
                        initial={{ opacity: 0, y: -20, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -10, scale: 0.97 }}
                        transition={{ duration: 0.2, ease: 'easeOut' }}
                        style={{
                            position: 'fixed',
                            top: '18%', left: '50%',
                            transform: 'translateX(-50%)',
                            width: 520, maxWidth: 'calc(100vw - 32px)',
                            zIndex: 10001,
                            background: 'var(--bg-glass, rgba(22,22,34,0.92))',
                            border: '1px solid var(--border-primary, #232336)',
                            borderRadius: 16,
                            boxShadow: '0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(6,182,212,0.08)',
                            backdropFilter: 'blur(20px)',
                            overflow: 'hidden',
                        }}
                    >
                        {/* Search input */}
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 10,
                            padding: '14px 18px',
                            borderBottom: '1px solid var(--border-primary, #232336)',
                        }}>
                            <Search size={18} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                            <input
                                ref={inputRef}
                                type="text"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyDown={handleKeyNav}
                                placeholder="Type a command…"
                                style={{
                                    flex: 1, background: 'none', border: 'none', outline: 'none',
                                    color: 'var(--text-primary, #fafafa)', fontSize: '0.95rem',
                                    fontFamily: 'var(--font-primary)',
                                }}
                            />
                            <kbd style={{
                                fontSize: '0.65rem', padding: '2px 6px',
                                background: 'var(--bg-secondary)', borderRadius: 4,
                                color: 'var(--text-muted)', border: '1px solid var(--border-primary)',
                            }}>
                                ESC
                            </kbd>
                        </div>

                        {/* Results */}
                        <div style={{ maxHeight: 320, overflow: 'auto', padding: '8px' }}>
                            {filtered.length === 0 ? (
                                <div style={{
                                    textAlign: 'center', padding: 28,
                                    color: 'var(--text-muted)', fontSize: '0.85rem',
                                }}>
                                    No results for "{query}"
                                </div>
                            ) : (
                                filtered.map((cmd, i) => (
                                    <div
                                        key={cmd.id}
                                        onClick={cmd.action}
                                        onMouseEnter={() => setSelectedIdx(i)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 12,
                                            padding: '10px 12px', borderRadius: 8,
                                            cursor: 'pointer',
                                            background: i === selectedIdx
                                                ? 'rgba(6,182,212,0.1)'
                                                : 'transparent',
                                            color: i === selectedIdx
                                                ? 'var(--text-primary)'
                                                : 'var(--text-secondary)',
                                            transition: 'background 100ms',
                                        }}
                                    >
                                        <span style={{
                                            opacity: 0.6,
                                            color: i === selectedIdx ? '#06b6d4' : 'inherit',
                                        }}>
                                            {cmd.icon}
                                        </span>
                                        <span style={{ flex: 1, fontSize: '0.88rem' }}>
                                            {cmd.label}
                                        </span>
                                        <span style={{
                                            fontSize: '0.65rem', color: 'var(--text-muted)',
                                        }}>
                                            {cmd.section}
                                        </span>
                                    </div>
                                ))
                            )}
                        </div>

                        {/* Footer */}
                        <div style={{
                            padding: '8px 16px',
                            borderTop: '1px solid var(--border-primary)',
                            display: 'flex', gap: 16,
                            fontSize: '0.65rem', color: 'var(--text-muted)',
                        }}>
                            <span>↑↓ navigate</span>
                            <span>↵ select</span>
                            <span>esc close</span>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}
