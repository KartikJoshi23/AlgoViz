/**
 * AlgoViz — Premium Navbar Component
 *
 * Glassmorphism top navigation bar with animated indicators,
 * live connection pulse, and trading terminal aesthetics.
 */

import { useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { motion, AnimatePresence } from 'framer-motion';
import {
    LayoutDashboard,
    BarChart3,
    Bell,
    Settings,
    GitBranch,
    Link as LinkIcon,
    Wifi,
    WifiOff,
    Menu,
    X,
} from 'lucide-react';
import { useState, useEffect } from 'react';

const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/analytics', icon: BarChart3, label: 'Analytics' },
    { path: '/strategies', icon: GitBranch, label: 'Strategies' },
    { path: '/alerts', icon: Bell, label: 'Alerts' },
    { path: '/onchain', icon: LinkIcon, label: 'On-Chain' },
    { path: '/settings', icon: Settings, label: 'Settings' },
];

/* ── Animated background particles ─────────────────────────────── */
function NavParticles() {
    return (
        <div className="nav-particles">
            {[...Array(3)].map((_, i) => (
                <motion.div
                    key={i}
                    className="nav-particle"
                    animate={{
                        x: [0, 100, -50, 0],
                        y: [0, -20, 10, 0],
                        opacity: [0.08, 0.15, 0.05, 0.08],
                    }}
                    transition={{
                        duration: 12 + i * 3,
                        repeat: Infinity,
                        ease: 'linear',
                    }}
                    style={{
                        left: `${20 + i * 30}%`,
                        width: 120 + i * 40,
                        height: 120 + i * 40,
                    }}
                />
            ))}
        </div>
    );
}

/* ── Live connection pulse ─────────────────────────────────────── */
function LivePulse({ connected }: { connected: boolean }) {
    const [tick, setTick] = useState(0);

    useEffect(() => {
        if (!connected) return;
        const interval = setInterval(() => setTick(t => t + 1), 1000);
        return () => clearInterval(interval);
    }, [connected]);

    return (
        <div className={`nav-live-badge ${connected ? 'live' : 'offline'}`}>
            <motion.div
                className="live-dot"
                animate={connected ? {
                    scale: [1, 1.4, 1],
                    opacity: [1, 0.5, 1],
                } : {}}
                transition={{ duration: 1.5, repeat: Infinity }}
            />
            <span className="live-text">{connected ? 'LIVE' : 'OFFLINE'}</span>
            {connected && (
                <motion.span
                    key={tick}
                    className="live-tick"
                    initial={{ opacity: 0.8, scale: 1.2 }}
                    animate={{ opacity: 0.4, scale: 1 }}
                    transition={{ duration: 0.5 }}
                >
                    ●
                </motion.span>
            )}
        </div>
    );
}

/* ── Logo ──────────────────────────────────────────────────────── */
function NavLogo() {
    return (
        <motion.div
            className="nav-logo"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
        >
            <div className="nav-logo-icon">
                <motion.svg
                    width="22" height="22" viewBox="0 0 24 24" fill="none"
                    animate={{ rotate: [0, 360] }}
                    transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
                >
                    <path
                        d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"
                        stroke="url(#logoGrad)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                        fill="url(#logoGradFill)" fillOpacity="0.15"
                    />
                    <defs>
                        <linearGradient id="logoGrad" x1="0" y1="0" x2="24" y2="24">
                            <stop stopColor="#06b6d4" />
                            <stop offset="1" stopColor="#8b5cf6" />
                        </linearGradient>
                        <linearGradient id="logoGradFill" x1="0" y1="0" x2="24" y2="24">
                            <stop stopColor="#06b6d4" />
                            <stop offset="1" stopColor="#8b5cf6" />
                        </linearGradient>
                    </defs>
                </motion.svg>
            </div>
            <div className="nav-logo-text">
                <span className="nav-logo-algoviz">AlgoViz</span>
                <span className="nav-logo-pro">PRO</span>
            </div>
        </motion.div>
    );
}

/* ── Main Navbar Component ─────────────────────────────────────── */
export function Navbar() {
    const location = useLocation();
    const navigate = useNavigate();
    const { connected } = useStore();
    const [mobileOpen, setMobileOpen] = useState(false);

    return (
        <>
            <nav className="navbar">
                <NavParticles />
                <div className="navbar-inner">
                    {/* Left: Logo */}
                    <NavLogo />

                    {/* Center: Navigation */}
                    <div className="nav-links">
                        {navItems.map((item) => {
                            const isActive = location.pathname === item.path;
                            return (
                                <motion.button
                                    key={item.path}
                                    className={`nav-link ${isActive ? 'active' : ''}`}
                                    onClick={() => navigate(item.path)}
                                    whileHover={{ y: -1 }}
                                    whileTap={{ scale: 0.97 }}
                                >
                                    <item.icon size={16} />
                                    <span>{item.label}</span>
                                    {isActive && (
                                        <motion.div
                                            className="nav-active-indicator"
                                            layoutId="activeTab"
                                            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                                        />
                                    )}
                                </motion.button>
                            );
                        })}
                    </div>

                    {/* Right: Status */}
                    <div className="nav-right">
                        <LivePulse connected={connected} />

                        {/* Mobile hamburger */}
                        <button
                            className="nav-mobile-toggle"
                            onClick={() => setMobileOpen(!mobileOpen)}
                        >
                            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
                        </button>
                    </div>
                </div>

                {/* Bottom glow line */}
                <div className="navbar-glow-line" />
            </nav>

            {/* Mobile menu overlay */}
            <AnimatePresence>
                {mobileOpen && (
                    <motion.div
                        className="nav-mobile-overlay"
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.2 }}
                    >
                        {navItems.map((item) => {
                            const isActive = location.pathname === item.path;
                            return (
                                <button
                                    key={item.path}
                                    className={`nav-mobile-link ${isActive ? 'active' : ''}`}
                                    onClick={() => {
                                        navigate(item.path);
                                        setMobileOpen(false);
                                    }}
                                >
                                    <item.icon size={18} />
                                    <span>{item.label}</span>
                                </button>
                            );
                        })}
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}
