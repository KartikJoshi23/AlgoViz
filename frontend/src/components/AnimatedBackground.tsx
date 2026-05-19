/**
 * AlgoViz — Animated Background
 *
 * Floating gradient orbs + grid mesh overlay for depth.
 */

import { motion } from 'framer-motion';

export function AnimatedBackground() {
    return (
        <div className="animated-bg">
            {/* Gradient mesh */}
            <div className="bg-grid" />

            {/* Floating orbs */}
            <motion.div
                className="bg-orb bg-orb-1"
                animate={{
                    x: [0, 80, -40, 60, 0],
                    y: [0, -60, 30, -80, 0],
                    scale: [1, 1.2, 0.9, 1.1, 1],
                }}
                transition={{ duration: 25, repeat: Infinity, ease: 'linear' }}
            />
            <motion.div
                className="bg-orb bg-orb-2"
                animate={{
                    x: [0, -70, 50, -30, 0],
                    y: [0, 40, -50, 70, 0],
                    scale: [1, 0.8, 1.3, 0.9, 1],
                }}
                transition={{ duration: 30, repeat: Infinity, ease: 'linear' }}
            />
            <motion.div
                className="bg-orb bg-orb-3"
                animate={{
                    x: [0, 50, -80, 20, 0],
                    y: [0, -30, 60, -40, 0],
                    scale: [1, 1.1, 0.85, 1.15, 1],
                }}
                transition={{ duration: 35, repeat: Infinity, ease: 'linear' }}
            />

            {/* Scan line */}
            <motion.div
                className="bg-scanline"
                animate={{ y: ['-100%', '200%'] }}
                transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
            />
        </div>
    );
}
