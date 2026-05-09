/**
 * AlgoViz — Toast Notification Provider
 *
 * Priority-based stacking toast system.
 * Auto-dismiss with smooth animations.
 */

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, AlertTriangle, CheckCircle, Info, XCircle } from 'lucide-react';
import { useStore, type Toast } from '../store';

const TOAST_CONFIG: Record<Toast['type'], { icon: React.ReactNode; color: string; bg: string }> = {
    info: { icon: <Info size={16} />, color: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
    success: { icon: <CheckCircle size={16} />, color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    warning: { icon: <AlertTriangle size={16} />, color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    error: { icon: <XCircle size={16} />, color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
};

function ToastItem({ toast }: { toast: Toast }) {
    const removeToast = useStore((s) => s.removeToast);
    const config = TOAST_CONFIG[toast.type];
    const duration = toast.duration ?? 5000;

    useEffect(() => {
        const timer = setTimeout(() => removeToast(toast.id), duration);
        return () => clearTimeout(timer);
    }, [toast.id, duration, removeToast]);

    return (
        <motion.div
            layout
            initial={{ opacity: 0, x: 60, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 10,
                padding: '12px 16px',
                borderRadius: 12,
                background: 'var(--bg-glass, rgba(22,22,34,0.92))',
                border: `1px solid ${config.color}30`,
                backdropFilter: 'blur(12px)',
                boxShadow: `0 4px 20px rgba(0,0,0,0.3), 0 0 20px ${config.color}10`,
                maxWidth: 360,
                minWidth: 260,
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* Progress bar */}
            <motion.div
                initial={{ scaleX: 1 }}
                animate={{ scaleX: 0 }}
                transition={{ duration: duration / 1000, ease: 'linear' }}
                style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: 2,
                    background: config.color,
                    transformOrigin: 'left',
                    opacity: 0.5,
                }}
            />

            {/* Icon */}
            <div style={{ color: config.color, flexShrink: 0, marginTop: 1 }}>
                {config.icon}
            </div>

            {/* Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    color: 'var(--text-primary)',
                    marginBottom: toast.message ? 2 : 0,
                }}>
                    {toast.title}
                </div>
                {toast.message && (
                    <div style={{
                        fontSize: '0.78rem',
                        color: 'var(--text-secondary)',
                        lineHeight: 1.4,
                    }}>
                        {toast.message}
                    </div>
                )}
            </div>

            {/* Close */}
            <button
                onClick={() => removeToast(toast.id)}
                style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', padding: 2, flexShrink: 0,
                }}
            >
                <X size={14} />
            </button>
        </motion.div>
    );
}

export function ToastProvider() {
    const toasts = useStore((s) => s.toasts);

    return (
        <div style={{
            position: 'fixed',
            bottom: 20,
            right: 20,
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            pointerEvents: toasts.length > 0 ? 'auto' : 'none',
        }}>
            <AnimatePresence mode="popLayout">
                {toasts.map((toast) => (
                    <ToastItem key={toast.id} toast={toast} />
                ))}
            </AnimatePresence>
        </div>
    );
}
