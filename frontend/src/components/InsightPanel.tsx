/**
 * AlgoViz — Insight Panel Component
 *
 * Displays trading intelligence from the rule engine.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../store';
import { Activity } from 'lucide-react';

function PriorityBadge({ priority }: { priority: string }) {
    const cls = `priority-${priority.toLowerCase()}`;
    return <span className={`insight-priority ${cls}`}>{priority}</span>;
}

export function InsightPanel() {
    const insights = useStore((s) => s.insights);

    if (!insights || insights.length === 0) {
        return (
            <div className="chart-container" style={{ minHeight: '200px' }}>
                <div className="chart-title">
                    <span>🎯</span> Trading Intelligence
                </div>
                <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
                    <Activity size={32} style={{ marginBottom: 8, opacity: 0.3 }} />
                    <div style={{ fontSize: '0.85rem' }}>Waiting for market data…</div>
                </div>
            </div>
        );
    }

    return (
        <div className="chart-container" style={{ minHeight: '200px' }}>
            <div className="chart-title">
                <span>🎯</span> Trading Intelligence
                <span className="badge badge-cyan" style={{ marginLeft: 'auto' }}>
                    {insights.length} Active
                </span>
            </div>
            <AnimatePresence mode="popLayout">
                {insights.map((insight, i) => (
                    <motion.div
                        key={`${insight.rule_id}-${i}`}
                        className={`insight-card priority-${insight.priority.toLowerCase()}`}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 10 }}
                        transition={{ delay: i * 0.05 }}
                    >
                        <PriorityBadge priority={insight.priority} />
                        <div className="insight-text">
                            {insight.priority_emoji} {insight.insight}
                        </div>
                        <div className="insight-action">
                            <strong>Action:</strong> {insight.action}
                        </div>
                        <div className="insight-action" style={{ opacity: 0.7, marginTop: 4 }}>
                            <strong>Impact:</strong> {insight.expected_impact}
                        </div>
                    </motion.div>
                ))}
            </AnimatePresence>
        </div>
    );
}
