/**
 * AlgoViz — Sidebar Component
 */

import { useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import {
    LayoutDashboard,
    BarChart3,
    Bell,
    Settings,
    GitBranch,
    Activity,
    Link as LinkIcon,
} from 'lucide-react';

const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/analytics', icon: BarChart3, label: 'Analytics' },
    { path: '/strategies', icon: GitBranch, label: 'Strategies' },
    { path: '/alerts', icon: Bell, label: 'Alerts' },
    { path: '/onchain', icon: LinkIcon, label: 'On-Chain' },
    { path: '/settings', icon: Settings, label: 'Settings' },
];

export function Sidebar() {
    const location = useLocation();
    const navigate = useNavigate();
    const { connected } = useStore();

    return (
        <aside className="sidebar">
            {/* Logo */}
            <div className="sidebar-header">
                <div className="sidebar-logo">
                    <div className="sidebar-logo-icon">📈</div>
                    <span className="sidebar-logo-text">AlgoViz</span>
                </div>
            </div>

            {/* Connection Status */}
            <div className={`connection-badge ${connected ? 'connected' : 'disconnected'}`}>
                <span className={`pulse-dot ${connected ? 'green' : 'red'}`} />
                <span>{connected ? 'Live' : 'Offline'}</span>
            </div>

            {/* Navigation */}
            <nav className="sidebar-nav">
                <div className="nav-section-label">Navigation</div>
                {navItems.map((item) => (
                    <div
                        key={item.path}
                        className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
                        onClick={() => navigate(item.path)}
                    >
                        <item.icon size={18} />
                        <span>{item.label}</span>
                    </div>
                ))}
            </nav>

            {/* Footer */}
            <div style={{ padding: '16px', borderTop: '1px solid var(--border-primary)' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                    AlgoViz v2.0 · Professional
                </div>
            </div>
        </aside>
    );
}
