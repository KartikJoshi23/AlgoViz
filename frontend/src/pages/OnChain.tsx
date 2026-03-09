/**
 * AlgoViz — On-Chain Analytics Page
 *
 * Premium feature preview for Phase 4 (Foundry integration).
 */

import { motion } from 'framer-motion';
import { Link as LinkIcon, Anchor, Fuel, FileCode, GitFork, ExternalLink } from 'lucide-react';

const FEATURES = [
    {
        icon: <Anchor size={28} />,
        title: 'Whale Tracking',
        desc: 'Monitor wallets with >100 ETH for large movements. Correlate whale activity with price action to detect front-running and accumulation patterns.',
        color: '#06b6d4',
        status: 'Planned',
    },
    {
        icon: <LinkIcon size={28} />,
        title: 'DEX Pool Analysis',
        desc: 'Read Uniswap V3 and SushiSwap pool reserves in real-time. Compare DEX vs CEX pricing to identify arbitrage opportunities.',
        color: '#8b5cf6',
        status: 'Planned',
    },
    {
        icon: <Fuel size={28} />,
        title: 'Gas Monitoring',
        desc: 'Track gas price trends and mempool congestion. High gas spikes signal increased on-chain activity and potential volatility.',
        color: '#f59e0b',
        status: 'Planned',
    },
    {
        icon: <FileCode size={28} />,
        title: 'Contract Events',
        desc: 'Watch specific smart contract events — large swaps, liquidity additions, governance votes. Real-time event stream decoded and analyzed.',
        color: '#ec4899',
        status: 'Planned',
    },
    {
        icon: <GitFork size={28} />,
        title: 'Fork Testing',
        desc: 'Backtest strategies against actual historical on-chain state using Foundry\'s fork mode. Simulate trades with real liquidity conditions.',
        color: '#10b981',
        status: 'Planned',
    },
    {
        icon: <ExternalLink size={28} />,
        title: 'Free RPC Integration',
        desc: 'Connect to Alchemy, Infura, or Ankr free tiers for Ethereum mainnet access. Zero cost with generous rate limits.',
        color: '#6366f1',
        status: 'Planned',
    },
];

export function OnChainPage() {
    return (
        <div>
            <div className="page-header">
                <h1 className="page-title">
                    <LinkIcon size={24} style={{ marginRight: 10, verticalAlign: 'middle' }} />
                    On-Chain Analytics
                </h1>
                <p className="page-subtitle">Blockchain intelligence powered by Foundry — Phase 4</p>
            </div>

            {/* Status Banner */}
            <motion.div
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                style={{
                    padding: '16px 24px', borderRadius: 12, marginBottom: 'var(--space-5)',
                    background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.08))',
                    border: '1px solid rgba(99, 102, 241, 0.25)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}
            >
                <div>
                    <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: 4 }}>
                        🔗 Foundry Integration — In Development
                    </div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                        This module will bridge on-chain Ethereum data with market analytics for unique cross-domain intelligence.
                    </div>
                </div>
                <span className="badge" style={{
                    background: 'rgba(99, 102, 241, 0.2)', color: '#818cf8',
                    padding: '6px 16px', borderRadius: 8, fontWeight: 600, flexShrink: 0,
                }}>
                    Phase 4
                </span>
            </motion.div>

            {/* Feature Preview Grid */}
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
                gap: 16,
            }}>
                {FEATURES.map((feature, i) => (
                    <motion.div
                        key={i}
                        className="card"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.08, duration: 0.4 }}
                        style={{ position: 'relative', overflow: 'hidden' }}
                    >
                        {/* Decorative glow */}
                        <div style={{
                            position: 'absolute', top: -30, right: -30, width: 100, height: 100,
                            borderRadius: '50%', background: `${feature.color}10`,
                            filter: 'blur(30px)', pointerEvents: 'none',
                        }} />

                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, position: 'relative' }}>
                            <div style={{
                                width: 48, height: 48, borderRadius: 12, flexShrink: 0,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: `${feature.color}15`, color: feature.color,
                                border: `1px solid ${feature.color}30`,
                            }}>
                                {feature.icon}
                            </div>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: 6 }}>
                                    {feature.title}
                                </div>
                                <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: 1.5 }}>
                                    {feature.desc}
                                </div>
                            </div>
                        </div>
                    </motion.div>
                ))}
            </div>

            {/* Architecture Preview */}
            <motion.div
                className="card" style={{ marginTop: 'var(--space-5)' }}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
            >
                <div className="card-header">
                    <div className="card-title">🏗️ Architecture Overview</div>
                </div>
                <pre style={{
                    padding: '20px', background: 'var(--bg-secondary)', borderRadius: 8,
                    fontSize: '0.78rem', fontFamily: 'var(--font-mono)',
                    color: 'var(--text-secondary)', lineHeight: 1.6, overflow: 'auto',
                }}>
                    {`  Ethereum Mainnet (via free RPC)
          │
          ▼
  ┌───────────────┐
  │   Foundry     │  forge script / cast call
  │  (Local CLI)  │  Fork mainnet state
  └───────┬───────┘
          │  JSON output
          ▼
  ┌───────────────┐
  │   Python      │  onchain_service.py
  │   Bridge      │  Parse & correlate
  └───────┬───────┘
          │  REST API
          ▼
  ┌───────────────┐
  │   Frontend    │  On-Chain Analytics page
  │   Dashboard   │  Whale alerts, gas charts
  └───────────────┘`}
                </pre>
            </motion.div>
        </div>
    );
}
