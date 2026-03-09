"""
AlgoViz - Professional UI Components
=================================================

Premium Streamlit UI components for the trading dashboard.
Features glassmorphism design and professional trading aesthetics.

Components:
- Dashboard Header with branding
- Connection Status Banner
- KPI Metrics Bar
- Insight & Action Panel (Key Differentiator)
- Trading Summary Statistics
"""

import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import COLORS, SYMBOL_DISPLAY
from ui.theme import Theme
from decision.insight_generator import Insight, generate_default_insights
from features.feature_engine import Features


class Components:
    """
    Professional UI Components for the AlgoViz Dashboard.
    
    All methods are static and return Streamlit elements.
    """
    
    # ==========================================================================
    # DASHBOARD HEADER WITH BRANDING
    # ==========================================================================
    
    @staticmethod
    def render_dashboard_header(is_connected: bool = True):
        """
        Render professional dashboard header with logo and live indicator.
        Features gradient branding and status indicators.
        """
        connection_color = "#10b981" if is_connected else "#ef4444"
        connection_text = "LIVE" if is_connected else "OFFLINE"
        
        st.markdown(f"""
        <div class="dashboard-header" style="background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(30, 25, 45, 0.95)); border: 1px solid rgba(139, 92, 246, 0.3);">
            <div class="logo-section">
                <div class="logo-icon" style="background: linear-gradient(135deg, #f59e0b, #f97316);">📈</div>
                <div class="logo-text">
                    <div class="logo-title" style="background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 50%, #8b5cf6 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">AlgoViz</div>
                    <div class="logo-subtitle" style="color: #a0aec0;">See the Signal in the Noise • <span style="color: #f59e0b;">BTC/USDT</span></div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="text-align: right;">
                    <div style="font-family: 'Inter', sans-serif; font-size: 10px; color: #718096; text-transform: uppercase; letter-spacing: 1px;">Data Source</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #8b5cf6; font-weight: 600;">Binance WebSocket</div>
                </div>
                <div class="live-badge" style="background: rgba({16 if is_connected else 239}, {185 if is_connected else 68}, {129 if is_connected else 68}, 0.15); border-color: {connection_color};">
                    <div class="live-dot" style="background: {connection_color}; box-shadow: 0 0 10px {connection_color};"></div>
                    <span class="live-text" style="color: {connection_color};">{connection_text}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # CONNECTION STATUS BANNER
    # ==========================================================================
    
    @staticmethod
    def render_connection_status(status: str, last_update: Optional[datetime] = None):
        """
        Render connection status banner with animated indicator.
        
        Args:
            status: 'connected', 'reconnecting', or 'disconnected'
            last_update: Timestamp of last data update
        """
        if status == "connected":
            status_class = "connected"
            text = "Connected to Binance Exchange"
            icon = "🟢"
        elif status == "reconnecting":
            status_class = "reconnecting"
            text = "Reconnecting to Exchange..."
            icon = "🟡"
        else:
            status_class = "disconnected"
            text = "Disconnected from Exchange"
            icon = "🔴"
        
        # Format timestamp
        if last_update:
            time_str = last_update.strftime("%H:%M:%S.%f")[:-3]
            date_str = last_update.strftime("%Y-%m-%d")
        else:
            time_str = "--:--:--.---"
            date_str = "----/--/--"
        
        st.markdown(f"""
        <div class="status-bar">
            <div class="status-indicator">
                <div class="status-dot {status_class}"></div>
                <span style="font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 500; color: var(--text-primary);">
                    {text}
                </span>
            </div>
            <div style="display: flex; align-items: center; gap: 24px;">
                <div style="text-align: right;">
                    <div style="font-family: 'Inter', sans-serif; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">
                        Last Update
                    </div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 14px; color: var(--accent-cyan); font-weight: 500;">
                        {time_str}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-family: 'Inter', sans-serif; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">
                        Date
                    </div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 14px; color: var(--text-secondary); font-weight: 500;">
                        {date_str}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # KPI HEADER - PREMIUM METRICS BAR
    # ==========================================================================
    
    @staticmethod
    def format_price(value: float) -> str:
        """Format price for display: 87.3K instead of 87,319.43"""
        if value >= 1_000_000:
            return f"${value/1_000_000:.2f}M"
        elif value >= 1_000:
            return f"${value/1_000:.2f}K"
        else:
            return f"${value:.2f}"
    
    @staticmethod
    def render_kpi_header(features: Features):
        """
        Render premium KPI metrics bar with glassmorphism cards.
        Each card has a unique color accent for visual distinction.
        Organized in two rows for better readability.
        """
        # Check if we're still waiting for data (current_price == 0)
        is_loading = features.current_price <= 0
        
        # Card style for uniformity
        card_style = "min-height:100px; display:flex; flex-direction:column; justify-content:center;"
        label_style = "font-size:10px; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;"
        value_style = "font-size:20px; font-weight:700; line-height:1.2;"
        delta_style = "font-size:10px; margin-top:4px;"
        
        # Helper for price formatting
        def fmt_price(val):
            if val <= 0:
                return "---"  # Show loading placeholder
            if val >= 1_000_000:
                return f"${val/1_000_000:.2f}M"
            elif val >= 10_000:
                return f"${val/1_000:.1f}K"
            else:
                return f"${val:,.2f}"
        
        # Show loading banner if no data yet
        if is_loading:
            st.markdown("""
            <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(59, 130, 246, 0.15)); 
                        border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 8px; 
                        padding: 12px 20px; margin-bottom: 16px; text-align: center;">
                <span style="color: #a78bfa; font-size: 14px;">⏳ Waiting for market data... WebSocket connecting...</span>
            </div>
            """, unsafe_allow_html=True)
        
        # ===================== ROW 1: Price & Core Metrics (4 KPIs) =====================
        row1_cols = st.columns(4)
        
        # 1. Current Price - GOLD accent
        with row1_cols[0]:
            price_display = fmt_price(features.current_price)
            price_color = "#a0aec0" if is_loading else "#fbbf24"
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #f59e0b; {card_style}">
                <div style="color: #f59e0b; {label_style}">💰 PRICE</div>
                <div style="color: {price_color}; {value_style}">{price_display}</div>
                <div style="color: #a0aec0; {delta_style}">BTC/USDT</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 2. Price Change - GREEN/RED based on value
        with row1_cols[1]:
            if is_loading:
                change_display = "---"
                delta_display = "---"
                color = "#a0aec0"
                arrow = "•"
            else:
                is_positive = features.price_change_pct >= 0
                arrow = "▲" if is_positive else "▼"
                color = "#10b981" if is_positive else "#ef4444"
                change_display = f"{abs(features.price_change_pct):.2f}%"
                delta_display = f"{'+' if is_positive else ''}{features.price_change:.2f}"
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid {color}; {card_style}">
                <div style="color: {color}; {label_style}">📊 CHANGE</div>
                <div style="color: {color}; {value_style}">{arrow} {change_display}</div>
                <div style="color: {color}; {delta_style}">{delta_display}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 3. Spread (bps) - PURPLE accent
        with row1_cols[2]:
            if is_loading:
                spread_display = "---"
                spread_color = "#a0aec0"
                status = "Waiting..."
            else:
                # Use more precision for very small spreads (< 0.1 bps)
                if features.spread_bps < 0.1:
                    spread_display = f"{features.spread_bps:.4f} bps"
                else:
                    spread_display = f"{features.spread_bps:.2f} bps"
                spread_color = Theme.get_spread_color(features.spread_bps)
                status = "Ultra-Tight" if features.spread_bps < 0.01 else ("Tight" if features.spread_bps < 3 else ("Normal" if features.spread_bps < 6 else "Wide"))
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #8b5cf6; {card_style}">
                <div style="color: #a78bfa; {label_style}">📏 SPREAD</div>
                <div style="color: {spread_color}; {value_style}">{spread_display}</div>
                <div style="color: {spread_color}; {delta_style}">{status}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 4. Velocity - ORANGE accent
        with row1_cols[3]:
            if is_loading:
                velocity_display = "---"
                velocity_color = "#a0aec0"
                status = "Waiting..."
            else:
                velocity_display = f"{features.velocity:.1f}/s"
                velocity_color = Theme.get_velocity_color(features.velocity)
                ratio = features.velocity / features.velocity_baseline if features.velocity_baseline > 0 else 1
                status = "Spike!" if ratio > 2 else ("High" if ratio > 1.5 else "Normal")
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #f97316; {card_style}">
                <div style="color: #fb923c; {label_style}">⚡ VELOCITY</div>
                <div style="color: {velocity_color}; {value_style}">{velocity_display}</div>
                <div style="color: {velocity_color}; {delta_style}">{status}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Small spacing between rows
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        
        # ===================== ROW 2: Weighted Averages & Imbalance (4 KPIs) =====================
        row2_cols = st.columns(4)
        
        # 5. VWAP - CYAN accent
        with row2_cols[0]:
            if is_loading:
                vwap_display = "---"
                vwap_color = "#a0aec0"
                vwap_status_display = "Waiting..."
            else:
                vwap_display = fmt_price(features.vwap)
                vwap_diff = features.price_vs_vwap
                vwap_status = "Above" if vwap_diff > 0.1 else ("Below" if vwap_diff < -0.1 else "Fair")
                vwap_color = "#ef4444" if vwap_diff > 0.1 else ("#10b981" if vwap_diff < -0.1 else "#06b6d4")
                vwap_status_display = f"{vwap_status} ({vwap_diff:+.1f}%)"
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #06b6d4; {card_style}">
                <div style="color: #22d3ee; {label_style}">📌 VWAP</div>
                <div style="color: #06b6d4; {value_style}">{vwap_display}</div>
                <div style="color: {vwap_color}; {delta_style}">{vwap_status_display}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 6. TWAP - TEAL accent (NEW)
        with row2_cols[1]:
            if is_loading:
                twap_display = "---"
                twap_color = "#a0aec0"
                twap_status_display = "Waiting..."
            else:
                twap_display = fmt_price(features.twap)
                twap_diff = features.price_vs_twap
                twap_status = "Above" if twap_diff > 0.1 else ("Below" if twap_diff < -0.1 else "Fair")
                twap_color = "#ef4444" if twap_diff > 0.1 else ("#10b981" if twap_diff < -0.1 else "#14b8a6")
                twap_status_display = f"{twap_status} ({twap_diff:+.1f}%)"
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #14b8a6; {card_style}">
                <div style="color: #2dd4bf; {label_style}">⏱️ TWAP</div>
                <div style="color: #14b8a6; {value_style}">{twap_display}</div>
                <div style="color: {twap_color}; {delta_style}">{twap_status_display}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 7. Imbalance - PINK accent
        with row2_cols[2]:
            if is_loading:
                imbalance_display = "---"
                imbalance_color = "#a0aec0"
                imbalance_label = "Waiting..."
            else:
                imbalance_display = f"{features.imbalance_pct:+.1f}%"
                imbalance_color = Theme.get_imbalance_color(features.imbalance)
                imbalance_label = "BUY" if features.imbalance > 0.3 else ("SELL" if features.imbalance < -0.3 else ("Buy" if features.imbalance > 0 else "Sell"))
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #ec4899; {card_style}">
                <div style="color: #f472b6; {label_style}">⚖️ IMBALANCE</div>
                <div style="color: {imbalance_color}; {value_style}">{imbalance_display}</div>
                <div style="color: {imbalance_color}; {delta_style}">{imbalance_label}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 8. Buy Pressure - INDIGO accent (NEW)
        with row2_cols[3]:
            if is_loading:
                pressure_display = "---"
                pressure_color = "#a0aec0"
                pressure_label = "Waiting..."
            else:
                pressure_pct = features.buy_pressure * 100
                pressure_color = "#10b981" if pressure_pct > 55 else ("#ef4444" if pressure_pct < 45 else "#6366f1")
                pressure_label = "Buyers" if pressure_pct > 55 else ("Sellers" if pressure_pct < 45 else "Neutral")
                pressure_display = f"{pressure_pct:.1f}%"
            
            st.markdown(f"""
            <div class="kpi-card" style="border-top: 3px solid #6366f1; {card_style}">
                <div style="color: #818cf8; {label_style}">🔥 BUY PRESSURE</div>
                <div style="color: {pressure_color}; {value_style}">{pressure_display}</div>
                <div style="color: {pressure_color}; {delta_style}">{pressure_label}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Add spacing after KPIs
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    
    # ==========================================================================
    # INSIGHT PANEL (KEY DIFFERENTIATOR) - PREMIUM VERSION
    # ==========================================================================
    
    @staticmethod
    def render_insight_panel(insights: List[Insight], height: int = 300):
        """
        Render the professional Insight & Action Panel.
        
        This is the KEY DIFFERENTIATOR of the dashboard.
        Shows insights with:
        - Priority badge with gradient
        - Insight description
        - Action recommendation
        - How to overcome
        - Expected impact
        
        Args:
            insights: List of Insight objects (sorted by priority)
            height: Panel height in pixels
        """
        # Panel header
        st.markdown("""
        <div class="insight-container">
            <div class="insight-header">
                <span class="insight-header-icon">🎯</span>
                <span class="insight-header-text">Trading Intelligence & Actions</span>
            </div>
        """, unsafe_allow_html=True)
        
        if not insights:
            insights = generate_default_insights()
        
        # Render each insight card
        for insight in insights[:3]:  # Limit to top 3
            priority_class = insight.priority.lower()
            
            st.markdown(f"""
            <div class="insight-card {priority_class}">
                <div class="priority-badge {priority_class}">
                    {insight.priority_emoji} {insight.priority}
                </div>
                <div class="insight-title">{insight.insight}</div>
                <div class="insight-row">
                    <span class="insight-label">Action</span>
                    <span class="insight-value action">{insight.action}</span>
                </div>
                <div class="insight-row">
                    <span class="insight-label">How</span>
                    <span class="insight-value">{insight.how_to_overcome}</span>
                </div>
                <div class="insight-row">
                    <span class="insight-label">Impact</span>
                    <span class="insight-value impact">{insight.expected_impact}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Close container
        st.markdown("</div>", unsafe_allow_html=True)
    
    # ==========================================================================
    # TRADING SUMMARY STATISTICS
    # ==========================================================================
    
    @staticmethod
    def render_trading_summary(features: Features, trade_count: int = 0, volume_24h: float = 0):
        """
        Render trading summary statistics row with vibrant colors.
        """
        # Determine volatility color
        if features.volatility_bps < 15:
            vol_color = "#10b981"
        elif features.volatility_bps < 20:
            vol_color = "#f59e0b"
        else:
            vol_color = "#ef4444"
        
        st.markdown(f"""
        <div class="metrics-summary" style="border: 1px solid rgba(139, 92, 246, 0.2);">
            <div class="metric-item" style="border-left: 3px solid #10b981;">
                <div class="metric-label" style="color: #34d399;">📈 Buy Pressure</div>
                <div class="metric-value" style="color: {'#10b981' if features.buy_pressure > 0.5 else '#ef4444'};">
                    {features.buy_pressure * 100:.1f}%
                </div>
            </div>
            <div class="metric-item" style="border-left: 3px solid #8b5cf6;">
                <div class="metric-label" style="color: #a78bfa;">📉 Volatility (60s)</div>
                <div class="metric-value" style="color: {vol_color};">
                    {features.volatility_bps:.2f} bps
                </div>
            </div>
            <div class="metric-item" style="border-left: 3px solid #06b6d4;">
                <div class="metric-label" style="color: #22d3ee;">💹 Bid Volume</div>
                <div class="metric-value" style="color: #10b981;">
                    {features.bid_volume:.3f}
                </div>
            </div>
            <div class="metric-item" style="border-left: 3px solid #f97316;">
                <div class="metric-label" style="color: #fb923c;">💹 Ask Volume</div>
                <div class="metric-value" style="color: #ef4444;">
                    {features.ask_volume:.3f}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # CHART WRAPPER WITH PROFESSIONAL STYLING
    # ==========================================================================
    
    @staticmethod
    def render_chart_container(title: str, icon: str = "📊"):
        """
        Start a chart container with professional styling.
        Returns HTML string for the container start.
        """
        return f"""
        <div class="chart-container">
            <div class="section-header">
                <span class="section-icon">{icon}</span>
                <span class="section-title">{title}</span>
            </div>
        """
    
    @staticmethod
    def close_chart_container():
        """Close the chart container."""
        return "</div>"
    
    # ==========================================================================
    # SECTION HEADERS
    # ==========================================================================
    
    @staticmethod
    def render_section_header(title: str, icon: str = "📈"):
        """Render a professional section header."""
        st.markdown(f"""
        <div class="section-header" style="margin-bottom: 20px; margin-top: 24px;">
            <span class="section-icon">{icon}</span>
            <span class="section-title">{title}</span>
        </div>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # LOADING STATES
    # ==========================================================================
    
    @staticmethod
    def render_loading_card(message: str = "Loading market data..."):
        """Render a premium loading placeholder."""
        st.markdown(f"""
        <div class="glass-card" style="text-align: center; padding: 60px;">
            <div style="font-size: 32px; margin-bottom: 16px;">⏳</div>
            <div style="
                font-family: 'Inter', sans-serif;
                font-size: 16px;
                color: var(--text-secondary);
            ">
                {message}
            </div>
            <div style="
                margin-top: 16px;
                width: 120px;
                height: 4px;
                background: var(--border-default);
                border-radius: 2px;
                margin: 16px auto 0;
                overflow: hidden;
            ">
                <div style="
                    width: 40%;
                    height: 100%;
                    background: linear-gradient(90deg, #4ecdc4, #667eea);
                    border-radius: 2px;
                    animation: loading 1.5s ease-in-out infinite;
                "></div>
            </div>
        </div>
        <style>
            @keyframes loading {{
                0% {{ transform: translateX(-100%); }}
                100% {{ transform: translateX(350%); }}
            }}
        </style>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # ERROR STATES
    # ==========================================================================
    
    @staticmethod
    def render_error_banner(message: str):
        """Render a premium error banner."""
        st.markdown(f"""
        <div style="
            background: linear-gradient(145deg, rgba(255, 107, 107, 0.1), rgba(255, 107, 107, 0.05));
            border: 1px solid rgba(255, 107, 107, 0.3);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 12px;
        ">
            <span style="font-size: 20px;">⚠️</span>
            <span style="
                font-family: 'Inter', sans-serif;
                font-size: 14px;
                font-weight: 500;
                color: #ff6b6b;
            ">{message}</span>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def render_warning_banner(message: str):
        """Render a premium warning banner."""
        st.markdown(f"""
        <div style="
            background: linear-gradient(145deg, rgba(255, 217, 61, 0.1), rgba(255, 217, 61, 0.05));
            border: 1px solid rgba(255, 217, 61, 0.3);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 12px;
        ">
            <span style="font-size: 20px;">⚠️</span>
            <span style="
                font-family: 'Inter', sans-serif;
                font-size: 14px;
                font-weight: 500;
                color: #ffd93d;
            ">{message}</span>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def render_success_banner(message: str):
        """Render a premium success banner."""
        st.markdown(f"""
        <div style="
            background: linear-gradient(145deg, rgba(0, 212, 170, 0.1), rgba(0, 212, 170, 0.05));
            border: 1px solid rgba(0, 212, 170, 0.3);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 12px;
        ">
            <span style="font-size: 20px;">✅</span>
            <span style="
                font-family: 'Inter', sans-serif;
                font-size: 14px;
                font-weight: 500;
                color: #00d4aa;
            ">{message}</span>
        </div>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # FOOTER
    # ==========================================================================
    
    # ==========================================================================
    # LIVE DATA FEED - REAL-TIME STREAMING TABLE (Using Streamlit Native)
    # ==========================================================================
    
    @staticmethod
    def render_live_data_feed(trades: list, depth_snapshot):
        """
        Render live data feed with streaming trades table and order book.
        Uses native Streamlit components for proper rendering.
        
        Args:
            trades: List of Trade objects (recent trades)
            depth_snapshot: Latest DepthSnapshot object
        """
        import pandas as pd
        
        col1, col2 = st.columns([3, 2])
        
        with col1:
            # Header with pulsing indicator
            st.markdown("""
                <div style="display: flex; align-items: center; margin-bottom: 16px;">
                    <div style="width: 12px; height: 12px; background: #10b981; border-radius: 50%; 
                                margin-right: 10px; animation: pulse 1.5s infinite;
                                box-shadow: 0 0 10px #10b981;"></div>
                    <span style="font-size: 18px; font-weight: 600; color: #fafafa;">Live Trade Stream</span>
                    <span style="margin-left: auto; font-size: 12px; color: #718096;">BTC/USDT • Binance</span>
                </div>
                <style>
                    @keyframes pulse {
                        0%, 100% { opacity: 1; box-shadow: 0 0 5px #10b981; }
                        50% { opacity: 0.5; box-shadow: 0 0 15px #10b981; }
                    }
                </style>
            """, unsafe_allow_html=True)
            
            if trades and len(trades) > 0:
                # Build DataFrame for trades
                recent_trades = list(trades)[-15:][::-1]
                
                trade_data = []
                for trade in recent_trades:
                    trade_data.append({
                        'Time': trade.timestamp.strftime("%H:%M:%S.%f")[:-3],
                        'Price': f"${trade.price:,.2f}",
                        'Quantity': f"{trade.quantity:.6f}",
                        'Side': "🟢 BUY" if not trade.is_buyer_maker else "🔴 SELL",
                        'Value': f"${trade.price * trade.quantity:,.2f}"
                    })
                
                df = pd.DataFrame(trade_data)
                
                # Style the dataframe
                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    height=400,
                    column_config={
                        "Time": st.column_config.TextColumn("Time", width="medium"),
                        "Price": st.column_config.TextColumn("Price (USD)", width="medium"),
                        "Quantity": st.column_config.TextColumn("Qty (BTC)", width="small"),
                        "Side": st.column_config.TextColumn("Side", width="small"),
                        "Value": st.column_config.TextColumn("Value (USD)", width="medium"),
                    }
                )
            else:
                st.info("⏳ Connecting to Binance WebSocket... Waiting for trade data.")
        
        with col2:
            st.markdown("""
                <div style="display: flex; align-items: center; margin-bottom: 16px;">
                    <span style="font-size: 18px; font-weight: 600; color: #fafafa;">📊 Order Book</span>
                    <span style="margin-left: auto; font-size: 12px; color: #718096;">Top 5 Levels</span>
                </div>
            """, unsafe_allow_html=True)
            
            if depth_snapshot and depth_snapshot.asks and depth_snapshot.bids:
                asks = depth_snapshot.asks[:5]
                bids = depth_snapshot.bids[:5]
                
                # Calculate max volume for bar width
                all_vols = [q for _, q in asks] + [q for _, q in bids]
                max_vol = max(all_vols) if all_vols else 1
                
                # ASKS Header
                st.markdown("<div style='background: rgba(239,68,68,0.15); padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;'><span style='color: #ef4444; font-weight: 600; font-size: 12px;'>🔴 ASKS (Sells)</span></div>", unsafe_allow_html=True)
                
                # Asks (reversed)
                for price, qty in reversed(asks):
                    bar_pct = int((qty / max_vol) * 100)
                    st.markdown(f"""
                        <div style="display: flex; justify-content: space-between; padding: 6px 12px; margin: 2px 0;
                                    background: linear-gradient(270deg, rgba(239,68,68,0.25) {bar_pct}%, transparent {bar_pct}%);
                                    border-radius: 4px; font-family: monospace; font-size: 13px;">
                            <span style="color: #ef4444; font-weight: 600;">${price:,.2f}</span>
                            <span style="color: #a0aec0;">{qty:.4f}</span>
                        </div>
                    """, unsafe_allow_html=True)
                
                # Spread
                spread = depth_snapshot.best_ask - depth_snapshot.best_bid
                mid = (depth_snapshot.best_ask + depth_snapshot.best_bid) / 2
                spread_bps = (spread / mid) * 10000 if mid > 0 else 0
                
                st.markdown(f"""
                    <div style="text-align: center; padding: 10px; margin: 10px 0; 
                                background: rgba(255,230,109,0.15); border-radius: 6px;
                                font-family: monospace; font-size: 13px; color: #ffe66d; font-weight: 600;">
                        Spread: ${spread:.2f} ({spread_bps:.2f} bps)
                    </div>
                """, unsafe_allow_html=True)
                
                # BIDS Header
                st.markdown("<div style='background: rgba(16,185,129,0.15); padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;'><span style='color: #10b981; font-weight: 600; font-size: 12px;'>🟢 BIDS (Buys)</span></div>", unsafe_allow_html=True)
                
                # Bids
                for price, qty in bids:
                    bar_pct = int((qty / max_vol) * 100)
                    st.markdown(f"""
                        <div style="display: flex; justify-content: space-between; padding: 6px 12px; margin: 2px 0;
                                    background: linear-gradient(90deg, rgba(16,185,129,0.25) {bar_pct}%, transparent {bar_pct}%);
                                    border-radius: 4px; font-family: monospace; font-size: 13px;">
                            <span style="color: #10b981; font-weight: 600;">${price:,.2f}</span>
                            <span style="color: #a0aec0;">{qty:.4f}</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("⏳ Waiting for order book data...")
    
    # ==========================================================================
    # SIDEBAR NAVIGATION
    # ==========================================================================
    
    @staticmethod
    def render_sidebar():
        """
        Render premium sidebar navigation with enhanced visuals.
        DATA SOURCE comes FIRST, then navigation adapts based on selected mode.
        Returns tuple of (selected_page, data_mode, scenario).
        """
        with st.sidebar:
            # Initialize navigation state
            if "current_page" not in st.session_state:
                st.session_state.current_page = "Home"
            
            # Inject sidebar-specific CSS
            st.markdown("""
                <style>
                    /* Disable text cursor on selectbox inputs */
                    [data-testid="stSidebar"] input {
                        caret-color: transparent !important;
                        cursor: pointer !important;
                    }
                    [data-testid="stSidebar"] .stSelectbox > div > div {
                        cursor: pointer !important;
                    }
                    
                    /* Enhanced sidebar styling */
                    [data-testid="stSidebar"] {
                        background: linear-gradient(180deg, #0f1419 0%, #151b24 50%, #1a2130 100%) !important;
                    }
                    [data-testid="stSidebar"] > div:first-child {
                        background: transparent !important;
                    }
                    
                    /* Navigation button styling */
                    .nav-btn {
                        display: block;
                        width: 100%;
                        padding: 12px 16px;
                        margin: 4px 0;
                        background: rgba(30, 41, 59, 0.6);
                        border: 1px solid rgba(71, 85, 105, 0.4);
                        border-radius: 10px;
                        color: #e2e8f0;
                        font-size: 14px;
                        font-weight: 500;
                        text-align: left;
                        cursor: pointer;
                        transition: all 0.2s ease;
                        text-decoration: none;
                    }
                    .nav-btn:hover {
                        background: rgba(59, 130, 246, 0.2);
                        border-color: rgba(59, 130, 246, 0.5);
                        transform: translateX(4px);
                    }
                    .nav-btn.active {
                        background: linear-gradient(135deg, rgba(139, 92, 246, 0.25), rgba(59, 130, 246, 0.25));
                        border-color: rgba(139, 92, 246, 0.6);
                        box-shadow: 0 0 12px rgba(139, 92, 246, 0.2);
                    }
                </style>
            """, unsafe_allow_html=True)
            
            # Premium Logo Section with gradient
            st.markdown("""
                <div style="
                    text-align: center; 
                    padding: 20px 10px; 
                    margin-bottom: 20px;
                    background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(59, 130, 246, 0.1));
                    border-radius: 12px;
                    border: 1px solid rgba(139, 92, 246, 0.2);
                ">
                    <div style="
                        font-size: 36px; 
                        margin-bottom: 8px;
                        filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.5));
                    ">📈</div>
                    <div style="
                        font-size: 16px; 
                        font-weight: 700; 
                        background: linear-gradient(135deg, #fbbf24, #f59e0b, #8b5cf6);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                        letter-spacing: 0.5px;
                    ">AlgoViz</div>
                    <div style="font-size: 9px; color: #64748b; margin-top: 4px; letter-spacing: 0.5px;">SEE THE SIGNAL IN THE NOISE</div>
                </div>
            """, unsafe_allow_html=True)
            
            # ==========================================================
            # 1. DATA SOURCE - Premium styled section
            # ==========================================================
            st.markdown("""
                <div style="
                    font-size: 10px; 
                    color: #8b5cf6; 
                    font-weight: 600;
                    letter-spacing: 1.5px;
                    margin-bottom: 8px;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                ">
                    <span style="font-size: 12px;">⚡</span> DATA SOURCE
                </div>
            """, unsafe_allow_html=True)
            
            data_mode = st.selectbox(
                "Mode",
                options=["📊 Static Demo", "📡 Live Data"],
                index=0,
                label_visibility="collapsed"
            )
            
            is_static_mode = "Static" in data_mode
            
            # Scenario for static mode - premium styled
            scenario = "normal"
            if is_static_mode:
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                scenario = st.selectbox(
                    "Scenario",
                    options=["Normal", "Bullish", "Bearish", "Volatile", "Ranging"],
                    index=0,
                    label_visibility="collapsed"
                ).lower()
            
            # Premium status indicator
            if is_static_mode:
                st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(99, 102, 241, 0.1));
                        border-left: 3px solid #3b82f6;
                        padding: 12px 14px;
                        border-radius: 0 8px 8px 0;
                        margin-top: 12px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    ">
                        <span style="font-size: 14px;">📊</span>
                        <span style="color: #60a5fa; font-size: 12px; font-weight: 500;">Synthetic Data Mode</span>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div style="
                        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.1));
                        border-left: 3px solid #10b981;
                        padding: 12px 14px;
                        border-radius: 0 8px 8px 0;
                        margin-top: 12px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    ">
                        <div style="
                            width: 8px;
                            height: 8px;
                            background: #10b981;
                            border-radius: 50%;
                            animation: pulse 2s infinite;
                            box-shadow: 0 0 8px #10b981;
                        "></div>
                        <span style="color: #34d399; font-size: 12px; font-weight: 500;">Live Binance Feed</span>
                    </div>
                    <style>
                        @keyframes pulse {
                            0%, 100% { opacity: 1; transform: scale(1); }
                            50% { opacity: 0.6; transform: scale(1.1); }
                        }
                    </style>
                """, unsafe_allow_html=True)
            
            st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
            
            # ==========================================================
            # 2. NAVIGATION - Using buttons with proper labels
            # ==========================================================
            st.markdown("""
                <div style="
                    font-size: 10px; 
                    color: #8b5cf6; 
                    font-weight: 600;
                    letter-spacing: 1.5px;
                    margin-bottom: 12px;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                ">
                    <span style="font-size: 12px;">🧭</span> NAVIGATION
                </div>
            """, unsafe_allow_html=True)
            
            # Define navigation options based on mode
            if is_static_mode:
                nav_items = [
                    ("🏠 Home", "Home"),
                    ("📊 Dashboard", "Dashboard"),
                    ("📈 Analytics", "Analytics"),
                    ("⚙️ Settings", "Settings")
                ]
            else:
                nav_items = [
                    ("🏠 Home", "Home"),
                    ("📊 Dashboard", "Dashboard"),
                    ("📡 Live Feed", "Live Feed"),
                    ("📈 Analytics", "Analytics"),
                    ("⚙️ Settings", "Settings")
                ]
            
            # Create navigation buttons
            for label, page_name in nav_items:
                is_active = st.session_state.current_page == page_name
                btn_type = "primary" if is_active else "secondary"
                if st.button(label, key=f"nav_{page_name}", width='stretch', type=btn_type):
                    st.session_state.current_page = page_name
                    st.rerun()
            
            selected_page = st.session_state.current_page
            
            # Validate selected page exists in current mode
            valid_pages = [item[1] for item in nav_items]
            if selected_page not in valid_pages:
                selected_page = "Home"
                st.session_state.current_page = "Home"
            
            st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
            
            # ==========================================================
            # 3. TRADING PAIR - Premium styled
            # ==========================================================
            st.markdown("""
                <div style="
                    font-size: 10px; 
                    color: #8b5cf6; 
                    font-weight: 600;
                    letter-spacing: 1.5px;
                    margin-bottom: 8px;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                ">
                    <span style="font-size: 12px;">💎</span> SYMBOL
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
                <div style="
                    background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(251, 191, 36, 0.05));
                    padding: 14px;
                    border-radius: 10px;
                    text-align: center;
                    border: 1px solid rgba(245, 158, 11, 0.2);
                ">
                    <div style="
                        font-size: 18px;
                        font-weight: 700;
                        background: linear-gradient(135deg, #fbbf24, #f59e0b);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                    ">BTC/USDT</div>
                    <div style="font-size: 10px; color: #64748b; margin-top: 4px;">Binance Spot</div>
                </div>
            """, unsafe_allow_html=True)
            
            # ==========================================================
            # 4. DOWNLOAD DATA (Only in Static/Demo Mode)
            # ==========================================================
            if is_static_mode:
                st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
                
                st.markdown("""
                    <div style="
                        font-size: 10px; 
                        color: #8b5cf6; 
                        font-weight: 600;
                        letter-spacing: 1.5px;
                        margin-bottom: 8px;
                        display: flex;
                        align-items: center;
                        gap: 6px;
                    ">
                        <span style="font-size: 12px;">📥</span> DOWNLOAD DATA
                    </div>
                """, unsafe_allow_html=True)
                
                # Get synthetic generator from session state
                if 'synthetic_generator' in st.session_state and st.session_state.synthetic_generator:
                    generator = st.session_state.synthetic_generator
                    
                    # Number of trades selector
                    num_trades = st.selectbox(
                        "Trades",
                        options=[100, 500, 1000, 5000],
                        index=2,
                        label_visibility="collapsed"
                    )
                    
                    # Generate CSV data
                    csv_data = generator.get_csv_data(num_trades=num_trades, include_features=True)
                    
                    # Download button
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv_data,
                        file_name=f"algoviz_synthetic_data_{num_trades}_trades.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    st.markdown("""
                        <div style="
                            font-size: 10px;
                            color: #64748b;
                            margin-top: 8px;
                            text-align: center;
                        ">
                            Includes price, volume, VWAP, volatility & more
                        </div>
                    """, unsafe_allow_html=True)
            
            return selected_page, data_mode, scenario
    
    @staticmethod
    def render_footer():
        """Render dashboard footer with credits."""
        st.markdown("""
        <div style="
            margin-top: 40px;
            padding: 20px;
            text-align: center;
            border-top: 1px solid var(--border-default);
        ">
            <div style="
                font-family: 'Inter', sans-serif;
                font-size: 12px;
                color: var(--text-muted);
            ">
                Made with ❤️ by Kartik Joshi, Aditya Chitale & Krishna Patel
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ==========================================================================
    # ML PREDICTION PANEL (NEW)
    # ==========================================================================
    
    @staticmethod
    def render_ml_prediction_panel(prediction):
        """
        Render the ML prediction panel with direction, confidence, and momentum.
        
        Args:
            prediction: PredictionResult from ML predictor
        """
        if prediction is None:
            st.markdown("""
            <div class="ml-panel" style="background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(30, 25, 45, 0.95)); 
                 border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 16px; padding: 20px;">
                <div style="text-align: center; color: #a0aec0;">
                    <span style="font-size: 24px;">🤖</span><br>
                    <span>ML Prediction Engine Initializing...</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            return
        
        # Direction styling
        direction_styles = {
            "strong_up": ("🚀 STRONG BUY", "#10b981", "linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(16, 185, 129, 0.1))"),
            "up": ("📈 BUY", "#22c55e", "linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(34, 197, 94, 0.05))"),
            "neutral": ("➡️ HOLD", "#6b7280", "linear-gradient(135deg, rgba(107, 114, 128, 0.15), rgba(107, 114, 128, 0.05))"),
            "down": ("📉 SELL", "#f97316", "linear-gradient(135deg, rgba(249, 115, 22, 0.15), rgba(249, 115, 22, 0.05))"),
            "strong_down": ("🔻 STRONG SELL", "#ef4444", "linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(239, 68, 68, 0.1))")
        }
        
        direction_key = prediction.direction.value if hasattr(prediction.direction, 'value') else str(prediction.direction)
        direction_text, direction_color, direction_bg = direction_styles.get(
            direction_key, ("➡️ ANALYZING", "#6b7280", "linear-gradient(135deg, rgba(107, 114, 128, 0.15), rgba(107, 114, 128, 0.05))")
        )
        
        # Regime styling
        regime_styles = {
            "trending_up": ("📈 Trending Up", "#10b981"),
            "trending_down": ("📉 Trending Down", "#ef4444"),
            "ranging": ("↔️ Ranging", "#6b7280"),
            "volatile": ("⚡ Volatile", "#f59e0b"),
            "breakout": ("🚀 Breakout", "#8b5cf6")
        }
        
        regime_key = prediction.regime.value if hasattr(prediction.regime, 'value') else str(prediction.regime)
        regime_text, regime_color = regime_styles.get(
            regime_key, ("❓ Analyzing", "#6b7280")
        )
        
        # Momentum bar color
        momentum = prediction.momentum_score
        if momentum > 30:
            momentum_color = "#10b981"
        elif momentum > 0:
            momentum_color = "#22c55e"
        elif momentum > -30:
            momentum_color = "#f97316"
        else:
            momentum_color = "#ef4444"
        
        # Feature importance (top 3)
        top_features = sorted(prediction.feature_importance.items(), key=lambda x: x[1], reverse=True)[:3] if prediction.feature_importance else []
        
        features_html = ""
        for feat_name, feat_val in top_features:
            features_html += f"""<div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #a0aec0; font-size: 11px;">{feat_name}</span><span style="color: #8b5cf6; font-size: 11px; font-family: monospace;">{feat_val:.1f}%</span></div>"""
        
        # Pre-compute conditional colors to avoid f-string issues
        accuracy_color = '#10b981' if prediction.model_accuracy > 55 else '#f59e0b'
        reversal_color = '#ef4444' if prediction.reversal_probability > 0.6 else '#f59e0b' if prediction.reversal_probability > 0.3 else '#10b981'
        confidence_pct = prediction.direction_confidence * 100
        reversal_pct = prediction.reversal_probability * 100
        momentum_left = 50 + momentum/2
        
        # Build HTML without comments and with pre-computed values
        html_content = f"""<div style="background: {direction_bg}; border: 1px solid {direction_color}40; border-radius: 16px; padding: 20px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 12px;">
<div><span style="font-size: 10px; color: #a0aec0; text-transform: uppercase; letter-spacing: 1px;">🤖 ML PREDICTION</span><div style="font-size: 11px; color: #718096; margin-top: 2px;">5-second horizon</div></div>
<div style="text-align: right;"><div style="font-size: 10px; color: #a0aec0;">Accuracy</div><div style="font-size: 14px; color: {accuracy_color}; font-family: monospace;">{prediction.model_accuracy:.1f}%</div></div>
</div>
<div style="text-align: center; margin-bottom: 16px;">
<div style="font-size: 24px; font-weight: 700; color: {direction_color};">{direction_text}</div>
<div style="font-size: 32px; font-weight: 700; color: {direction_color}; font-family: monospace;">{confidence_pct:.0f}%</div>
<div style="font-size: 11px; color: #a0aec0;">Confidence</div>
</div>
<div style="margin-bottom: 16px;">
<div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #ef4444; font-size: 10px;">Bearish</span><span style="color: #a0aec0; font-size: 10px;">Momentum</span><span style="color: #10b981; font-size: 10px;">Bullish</span></div>
<div style="background: rgba(30, 41, 59, 0.8); height: 8px; border-radius: 4px; position: relative;">
<div style="position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: rgba(255,255,255,0.3);"></div>
<div style="position: absolute; left: {momentum_left}%; top: -2px; width: 12px; height: 12px; background: {momentum_color}; border-radius: 50%; transform: translateX(-50%); box-shadow: 0 0 8px {momentum_color};"></div>
</div>
<div style="text-align: center; margin-top: 4px;"><span style="color: {momentum_color}; font-size: 14px; font-family: monospace;">{momentum:+.0f}</span></div>
</div>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
<div style="background: rgba(20, 25, 35, 0.6); padding: 10px; border-radius: 8px;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase;">Regime</div><div style="font-size: 13px; color: {regime_color}; font-weight: 600;">{regime_text}</div></div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 10px; border-radius: 8px;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase;">Reversal Risk</div><div style="font-size: 13px; color: {reversal_color}; font-weight: 600;">{reversal_pct:.0f}%</div></div>
</div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 10px; border-radius: 8px;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase; margin-bottom: 8px;">Top Contributing Factors</div>{features_html}</div>
</div>"""
        
        st.markdown(html_content, unsafe_allow_html=True)
    
    # ==========================================================================
    # DEEP LEARNING PREDICTION PANEL (NEW)
    # ==========================================================================
    
    @staticmethod
    def render_deep_learning_panel(prediction):
        """
        Render the Deep Learning Neural Network prediction panel.
        
        Args:
            prediction: DeepPredictionResult from deep learning predictor
        """
        if prediction is None:
            st.markdown("""
            <div class="dl-panel" style="background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(88, 28, 135, 0.2)); 
                 border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 16px; padding: 20px;">
                <div style="text-align: center; color: #a0aec0;">
                    <span style="font-size: 24px;">🧠</span><br>
                    <span>Neural Network Initializing...</span><br>
                    <span style="font-size: 10px; color: #8b5cf6;">LSTM + Attention layers loading...</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            return
        
        # Direction styling with neural network theme
        direction_styles = {
            "strong_up": ("🚀 STRONG BUY", "#10b981", "linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(88, 28, 135, 0.15))"),
            "up": ("📈 BUY", "#22c55e", "linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(88, 28, 135, 0.1))"),
            "neutral": ("➡️ HOLD", "#a78bfa", "linear-gradient(135deg, rgba(167, 139, 250, 0.15), rgba(88, 28, 135, 0.1))"),
            "down": ("📉 SELL", "#f97316", "linear-gradient(135deg, rgba(249, 115, 22, 0.2), rgba(88, 28, 135, 0.1))"),
            "strong_down": ("🔻 STRONG SELL", "#ef4444", "linear-gradient(135deg, rgba(239, 68, 68, 0.25), rgba(88, 28, 135, 0.15))")
        }
        
        direction_key = prediction.direction.value if hasattr(prediction.direction, 'value') else str(prediction.direction)
        direction_text, direction_color, direction_bg = direction_styles.get(
            direction_key, ("➡️ ANALYZING", "#a78bfa", "linear-gradient(135deg, rgba(167, 139, 250, 0.15), rgba(88, 28, 135, 0.1))")
        )
        
        # Regime styling
        regime_styles = {
            "trending_up": ("📈 Trending Up", "#10b981"),
            "trending_down": ("📉 Trending Down", "#ef4444"),
            "ranging": ("↔️ Ranging", "#a78bfa"),
            "volatile": ("⚡ Volatile", "#f59e0b"),
            "breakout": ("🚀 Breakout", "#8b5cf6")
        }
        
        regime_key = prediction.regime.value if hasattr(prediction.regime, 'value') else str(prediction.regime)
        regime_text, regime_color = regime_styles.get(regime_key, ("❓ Analyzing", "#a78bfa"))
        
        # Probability bar values
        up_pct = prediction.up_probability * 100
        down_pct = prediction.down_probability * 100
        neutral_pct = prediction.neutral_probability * 100
        
        # Momentum styling
        momentum = prediction.momentum_score
        if momentum > 30:
            momentum_color = "#10b981"
        elif momentum > 0:
            momentum_color = "#22c55e"
        elif momentum > -30:
            momentum_color = "#f97316"
        else:
            momentum_color = "#ef4444"
        
        # Pre-compute values
        accuracy_color = '#10b981' if prediction.model_accuracy > 55 else '#f59e0b'
        uncertainty_color = '#10b981' if prediction.prediction_uncertainty < 30 else '#f59e0b' if prediction.prediction_uncertainty < 50 else '#ef4444'
        confidence_pct = prediction.direction_confidence * 100
        momentum_left = 50 + momentum/2
        
        # Feature importance (top 4)
        top_features = sorted(prediction.feature_importance.items(), key=lambda x: x[1], reverse=True)[:4] if prediction.feature_importance else []
        
        features_html = ""
        for feat_name, feat_val in top_features:
            bar_width = min(feat_val, 100)
            features_html += f"""<div style="margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                    <span style="color: #a0aec0; font-size: 10px;">{feat_name}</span>
                    <span style="color: #a78bfa; font-size: 10px; font-family: monospace;">{feat_val:.1f}%</span>
                </div>
                <div style="background: rgba(30, 41, 59, 0.8); height: 4px; border-radius: 2px;">
                    <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, #8b5cf6, #a78bfa); border-radius: 2px;"></div>
                </div>
            </div>"""
        
        # Attention visualization (simplified)
        attention_html = ""
        if prediction.attention_weights and len(prediction.attention_weights) > 0:
            # Show last 10 attention weights as bars
            weights = prediction.attention_weights[-10:] if len(prediction.attention_weights) > 10 else prediction.attention_weights
            max_weight = max(weights) if weights else 1
            for i, w in enumerate(weights):
                height = int(w / max_weight * 24)
                opacity = 0.4 + (w / max_weight) * 0.6
                attention_html += f"""<div style="width: 6px; height: {height}px; background: rgba(139, 92, 246, {opacity}); border-radius: 2px; margin: 0 1px;"></div>"""
        
        # Layer activations
        layer_html = ""
        if prediction.layer_activations:
            for layer_name, activation in list(prediction.layer_activations.items())[:3]:
                layer_width = min(activation * 100, 100)
                layer_html += f"""<div style="display: flex; align-items: center; margin-bottom: 4px;">
                    <span style="color: #718096; font-size: 9px; width: 70px;">{layer_name}</span>
                    <div style="flex: 1; background: rgba(30, 41, 59, 0.8); height: 4px; border-radius: 2px; margin-left: 8px;">
                        <div style="width: {layer_width}%; height: 100%; background: #a78bfa; border-radius: 2px;"></div>
                    </div>
                </div>"""
        
        html_content = f"""<div style="background: {direction_bg}; border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 16px; padding: 20px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid rgba(168, 85, 247, 0.2); padding-bottom: 12px;">
<div><span style="font-size: 10px; color: #a78bfa; text-transform: uppercase; letter-spacing: 1px;">🧠 DEEP LEARNING</span><div style="font-size: 11px; color: #718096; margin-top: 2px;">{prediction.model_type} • {prediction.total_parameters:,} params</div></div>
<div style="text-align: right;"><div style="font-size: 10px; color: #a0aec0;">Hist. Accuracy</div><div style="font-size: 14px; color: {accuracy_color}; font-family: monospace;">{prediction.model_accuracy:.1f}%</div></div>
</div>
<div style="text-align: center; margin-bottom: 16px;">
<div style="font-size: 24px; font-weight: 700; color: {direction_color};">{direction_text}</div>
<div style="font-size: 32px; font-weight: 700; color: {direction_color}; font-family: monospace;">{confidence_pct:.0f}%</div>
<div style="font-size: 11px; color: #a0aec0;">Neural Network Confidence</div>
</div>
<div style="margin-bottom: 16px; background: rgba(20, 25, 35, 0.6); padding: 12px; border-radius: 8px;">
<div style="font-size: 10px; color: #a0aec0; text-transform: uppercase; margin-bottom: 8px;">Output Probabilities</div>
<div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #10b981; font-size: 10px;">↑ UP</span><span style="color: #a78bfa; font-size: 10px;">→ HOLD</span><span style="color: #ef4444; font-size: 10px;">↓ DOWN</span></div>
<div style="display: flex; height: 8px; border-radius: 4px; overflow: hidden;"><div style="width: {up_pct}%; background: linear-gradient(90deg, #10b981, #22c55e);"></div><div style="width: {neutral_pct}%; background: #a78bfa;"></div><div style="width: {down_pct}%; background: linear-gradient(90deg, #f97316, #ef4444);"></div></div>
<div style="display: flex; justify-content: space-between; margin-top: 4px;"><span style="color: #10b981; font-size: 11px; font-family: monospace;">{up_pct:.1f}%</span><span style="color: #a78bfa; font-size: 11px; font-family: monospace;">{neutral_pct:.1f}%</span><span style="color: #ef4444; font-size: 11px; font-family: monospace;">{down_pct:.1f}%</span></div>
</div>
<div style="margin-bottom: 16px;">
<div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #ef4444; font-size: 10px;">Bearish</span><span style="color: #a0aec0; font-size: 10px;">LSTM Momentum</span><span style="color: #10b981; font-size: 10px;">Bullish</span></div>
<div style="background: rgba(30, 41, 59, 0.8); height: 8px; border-radius: 4px; position: relative;"><div style="position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: rgba(255,255,255,0.3);"></div><div style="position: absolute; left: {momentum_left}%; top: -2px; width: 12px; height: 12px; background: {momentum_color}; border-radius: 50%; transform: translateX(-50%); box-shadow: 0 0 8px {momentum_color};"></div></div>
<div style="text-align: center; margin-top: 4px;"><span style="color: {momentum_color}; font-size: 14px; font-family: monospace;">{momentum:+.0f}</span></div>
</div>
<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 12px;">
<div style="background: rgba(20, 25, 35, 0.6); padding: 8px; border-radius: 8px; text-align: center;"><div style="font-size: 9px; color: #a0aec0; text-transform: uppercase;">Regime</div><div style="font-size: 11px; color: {regime_color}; font-weight: 600;">{regime_text}</div></div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 8px; border-radius: 8px; text-align: center;"><div style="font-size: 9px; color: #a0aec0; text-transform: uppercase;">Uncertainty</div><div style="font-size: 11px; color: {uncertainty_color}; font-weight: 600;">{prediction.prediction_uncertainty:.0f}%</div></div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 8px; border-radius: 8px; text-align: center;"><div style="font-size: 9px; color: #a0aec0; text-transform: uppercase;">Pred. Move</div><div style="font-size: 11px; color: {'#10b981' if prediction.predicted_move_bps > 0 else '#ef4444'}; font-weight: 600;">{prediction.predicted_move_bps:+.1f} bps</div></div>
</div>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
<div style="background: rgba(20, 25, 35, 0.6); padding: 10px; border-radius: 8px;"><div style="font-size: 9px; color: #a78bfa; text-transform: uppercase; margin-bottom: 8px;">🎯 Feature Importance</div>{features_html}</div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 10px; border-radius: 8px;"><div style="font-size: 9px; color: #a78bfa; text-transform: uppercase; margin-bottom: 8px;">👁️ Attention Weights</div><div style="display: flex; align-items: flex-end; justify-content: center; height: 28px; margin-bottom: 8px;">{attention_html}</div><div style="font-size: 9px; color: #a78bfa; text-transform: uppercase; margin-bottom: 4px; margin-top: 8px;">📊 Layer Activations</div>{layer_html}</div>
</div>
<div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(168, 85, 247, 0.2); display: flex; justify-content: space-between;"><span style="font-size: 9px; color: #718096;">Inference: {prediction.inference_time_ms:.1f}ms</span><span style="font-size: 9px; color: #718096;">Horizon: {prediction.prediction_horizon_seconds}s</span><span style="font-size: 9px; color: #718096;">Layers: {prediction.hidden_layers}</span></div>
</div>"""
        
        st.markdown(html_content, unsafe_allow_html=True)
    
    # ==========================================================================
    # ALERT PANEL (NEW)
    # ==========================================================================
    
    @staticmethod
    def render_alert_panel(alerts, max_alerts: int = 5):
        """
        Render the alert notification panel.
        
        Args:
            alerts: List of Alert objects
            max_alerts: Maximum alerts to display
        """
        # Priority colors
        priority_styles = {
            "critical": ("#ef4444", "🚨", "rgba(239, 68, 68, 0.15)"),
            "high": ("#f97316", "🔴", "rgba(249, 115, 22, 0.15)"),
            "medium": ("#eab308", "🟡", "rgba(234, 179, 8, 0.12)"),
            "low": ("#22c55e", "🟢", "rgba(34, 197, 94, 0.12)"),
            "info": ("#3b82f6", "ℹ️", "rgba(59, 130, 246, 0.12)")
        }
        
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(30, 25, 45, 0.95)); 
             border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 16px; padding: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px;">
                <span style="font-size: 12px; color: #fafafa; font-weight: 600;">🔔 ALERTS</span>
                <span style="font-size: 10px; color: #a0aec0;">Real-time notifications</span>
            </div>
        """, unsafe_allow_html=True)
        
        if not alerts:
            st.markdown("""
                <div style="text-align: center; padding: 20px; color: #6b7280;">
                    <span style="font-size: 20px;">✨</span><br>
                    <span style="font-size: 12px;">No active alerts</span>
                </div>
            """, unsafe_allow_html=True)
        else:
            for alert in alerts[:max_alerts]:
                priority_key = alert.priority.value if hasattr(alert.priority, 'value') else str(alert.priority).lower()
                color, icon, bg = priority_styles.get(priority_key, ("#6b7280", "⚪", "rgba(107, 114, 128, 0.1)"))
                
                time_str = alert.timestamp.strftime("%H:%M:%S") if hasattr(alert, 'timestamp') else "now"
                
                st.markdown(f"""
                <div style="background: {bg}; border-left: 3px solid {color}; border-radius: 0 8px 8px 0; padding: 10px 12px; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <span style="color: {color}; font-size: 10px; font-weight: 600;">{icon} {priority_key.upper()}</span>
                            <div style="color: #fafafa; font-size: 12px; margin-top: 4px;">{alert.message}</div>
                        </div>
                        <span style="color: #6b7280; font-size: 10px; font-family: 'JetBrains Mono';">{time_str}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # ==========================================================================
    # NOTIFICATION BELL ICON (NEW)
    # ==========================================================================
    
    @staticmethod
    def render_notification_bell_header(alert_count: int = 0, is_live_mode: bool = True):
        """
        Render the notification bell icon that displays in the header area.
        Shows a badge with alert count if there are active alerts.
        
        Args:
            alert_count: Number of active alerts
            is_live_mode: Whether dashboard is in live mode (bell active) or static mode (bell disabled)
        """
        if is_live_mode:
            # Active bell with potential alerts
            if alert_count > 0:
                badge_html = f'<span style="position: absolute; top: -5px; right: -5px; background: #ef4444; color: white; font-size: 10px; font-weight: 700; min-width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-family: monospace; box-shadow: 0 2px 8px rgba(239, 68, 68, 0.5);">{alert_count}</span>'
                bell_color = "#f59e0b"
                shake_animation = "animation: shake 0.5s ease-in-out;"
            else:
                badge_html = ""
                bell_color = "#a0aec0"
                shake_animation = ""
            
            st.markdown(f"""
            <style>
            @keyframes shake {{
                0%, 100% {{ transform: rotate(0deg); }}
                25% {{ transform: rotate(-10deg); }}
                50% {{ transform: rotate(10deg); }}
                75% {{ transform: rotate(-5deg); }}
            }}
            </style>
            <div style="position: relative; display: inline-block; cursor: pointer; {shake_animation}">
                <span style="font-size: 24px; color: {bell_color};">🔔</span>
                {badge_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            # Disabled bell for static mode with tooltip
            st.markdown("""
            <div style="position: relative; display: inline-block; cursor: not-allowed; opacity: 0.5;" 
                 title="Alerts available in Live Mode only">
                <span style="font-size: 24px; color: #4a5568;">🔕</span>
            </div>
            """, unsafe_allow_html=True)
    
    @staticmethod  
    def render_notification_popover(alerts, is_live_mode: bool = True):
        """
        Render the notification popover content showing recent alerts.
        This is meant to be used inside a Streamlit expander or popover.
        
        Args:
            alerts: List of Alert objects
            is_live_mode: Whether dashboard is in live mode
        """
        if not is_live_mode:
            st.markdown("""
            <div style="background: rgba(30, 35, 45, 0.95); border: 1px solid rgba(100, 100, 100, 0.3); 
                 border-radius: 12px; padding: 16px; text-align: center;">
                <span style="font-size: 32px;">🔕</span>
                <p style="color: #718096; margin-top: 10px; font-size: 13px;">
                    Alerts are only available in <strong style="color: #10b981;">Live Mode</strong>
                </p>
                <p style="color: #4a5568; font-size: 11px; margin-top: 5px;">
                    Switch to Live Mode in the sidebar to see real-time trading alerts
                </p>
            </div>
            """, unsafe_allow_html=True)
            return
        
        # Priority colors
        priority_styles = {
            "critical": ("#ef4444", "🚨"),
            "high": ("#f97316", "🔴"),
            "medium": ("#eab308", "🟡"),
            "low": ("#22c55e", "🟢"),
            "info": ("#3b82f6", "ℹ️")
        }
        
        st.markdown("""
        <div style="border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; margin-bottom: 12px;">
            <span style="font-size: 13px; color: #fafafa; font-weight: 600;">🔔 Active Alerts</span>
        </div>
        """, unsafe_allow_html=True)
        
        if not alerts:
            st.markdown("""
            <div style="text-align: center; padding: 20px; color: #6b7280;">
                <span style="font-size: 24px;">✨</span><br>
                <span style="font-size: 12px;">No active alerts - Market is calm</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            for alert in alerts[:6]:  # Max 6 alerts in popover
                priority_key = alert.priority.value if hasattr(alert.priority, 'value') else str(alert.priority).lower()
                color, icon = priority_styles.get(priority_key, ("#6b7280", "⚪"))
                
                time_str = alert.timestamp.strftime("%H:%M:%S") if hasattr(alert, 'timestamp') else "now"
                
                st.markdown(f"""
                <div style="background: rgba(30, 35, 45, 0.6); border-left: 3px solid {color}; 
                     border-radius: 0 8px 8px 0; padding: 8px 10px; margin-bottom: 6px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <span style="color: {color}; font-size: 9px; font-weight: 600;">{icon} {priority_key.upper()}</span>
                            <div style="color: #e2e8f0; font-size: 11px; margin-top: 2px;">{alert.message}</div>
                        </div>
                        <span style="color: #4a5568; font-size: 9px; font-family: 'JetBrains Mono';">{time_str}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
    # ==========================================================================
    # BACKTEST RESULTS PANEL (NEW)
    # ==========================================================================
    
    @staticmethod
    def render_backtest_summary(result):
        """
        Render backtest results summary panel.
        
        Args:
            result: BacktestResult object
        """
        if result is None:
            return
        
        is_profitable = result.total_pnl >= 0
        pnl_color = "#10b981" if is_profitable else "#ef4444"
        
        # Pre-compute conditional colors
        win_rate_color = '#10b981' if result.win_rate > 50 else '#ef4444'
        pf_color = '#10b981' if result.profit_factor > 1 else '#ef4444'
        sharpe_color = '#10b981' if result.sharpe_ratio > 1 else '#f59e0b' if result.sharpe_ratio > 0 else '#ef4444'
        pnl_sign = '+' if is_profitable else ''
        
        html_content = f"""<div style="background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(30, 25, 45, 0.95)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 16px; padding: 20px; margin-bottom: 20px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 12px;">
<div><span style="font-size: 14px; color: #fafafa; font-weight: 600;">🧪 {result.strategy_name}</span><div style="font-size: 11px; color: #718096; margin-top: 2px;">{result.total_trades} trades executed</div></div>
<div style="text-align: right;"><div style="font-size: 24px; color: {pnl_color}; font-weight: 700; font-family: monospace;">{pnl_sign}{result.total_pnl_pct:.2f}%</div><div style="font-size: 11px; color: {pnl_color};">${result.total_pnl:+,.2f}</div></div>
</div>
<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
<div style="background: rgba(20, 25, 35, 0.6); padding: 12px; border-radius: 8px; text-align: center;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase;">Win Rate</div><div style="font-size: 18px; color: {win_rate_color}; font-weight: 600;">{result.win_rate:.1f}%</div></div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 12px; border-radius: 8px; text-align: center;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase;">Profit Factor</div><div style="font-size: 18px; color: {pf_color}; font-weight: 600;">{result.profit_factor:.2f}</div></div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 12px; border-radius: 8px; text-align: center;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase;">Sharpe Ratio</div><div style="font-size: 18px; color: {sharpe_color}; font-weight: 600;">{result.sharpe_ratio:.2f}</div></div>
<div style="background: rgba(20, 25, 35, 0.6); padding: 12px; border-radius: 8px; text-align: center;"><div style="font-size: 10px; color: #a0aec0; text-transform: uppercase;">Max Drawdown</div><div style="font-size: 18px; color: #ef4444; font-weight: 600;">-{result.max_drawdown_pct:.2f}%</div></div>
</div>
<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px;">
<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);"><span style="color: #a0aec0; font-size: 11px;">Wins / Losses</span><span style="color: #fafafa; font-size: 11px; font-family: monospace;"><span style="color: #10b981;">{result.winning_trades}</span> / <span style="color: #ef4444;">{result.losing_trades}</span></span></div>
<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);"><span style="color: #a0aec0; font-size: 11px;">Avg Win</span><span style="color: #10b981; font-size: 11px; font-family: monospace;">${result.avg_win:.2f}</span></div>
<div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);"><span style="color: #a0aec0; font-size: 11px;">Avg Loss</span><span style="color: #ef4444; font-size: 11px; font-family: monospace;">${result.avg_loss:.2f}</span></div>
</div>
</div>"""
        
        st.markdown(html_content, unsafe_allow_html=True)
    
    # ==========================================================================
    # CORRELATION MATRIX PANEL (NEW)
    # ==========================================================================
    
    @staticmethod
    def render_correlation_panel(correlations: dict):
        """
        Render correlation matrix as a styled, easy-to-read panel.
        
        Args:
            correlations: Dict with metric pairs and correlation values
        """
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(30, 25, 45, 0.95)); 
             border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 16px; padding: 28px;">
            <div style="font-size: 20px; color: #fafafa; font-weight: 700; margin-bottom: 24px; display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 24px;">📊</span> Feature Correlations
            </div>
        """, unsafe_allow_html=True)
        
        if not correlations:
            st.markdown("""
                <div style="text-align: center; padding: 40px; color: #6b7280; font-size: 16px;">
                    ⏳ Calculating correlations...
                </div>
            """, unsafe_allow_html=True)
        else:
            for (metric1, metric2), corr in list(correlations.items()):
                # Color based on correlation strength
                if abs(corr) > 0.7:
                    corr_color = "#a78bfa"
                    strength_label = "Strong"
                    strength_bg = "rgba(139, 92, 246, 0.2)"
                elif abs(corr) > 0.4:
                    corr_color = "#60a5fa"
                    strength_label = "Moderate"
                    strength_bg = "rgba(59, 130, 246, 0.2)"
                else:
                    corr_color = "#94a3b8"
                    strength_label = "Weak"
                    strength_bg = "rgba(148, 163, 184, 0.1)"
                
                bar_width = abs(corr) * 100
                bar_color = "#10b981" if corr > 0 else "#ef4444"
                direction = "Positive" if corr > 0 else "Negative"
                direction_icon = "📈" if corr > 0 else "📉"
                
                st.markdown(f"""
                <div style="background: {strength_bg}; border: 1px solid rgba(255,255,255,0.08); 
                            border-radius: 12px; padding: 16px 20px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 16px;">{direction_icon}</span>
                            <span style="font-size: 15px; color: #fafafa; font-weight: 600;">{metric1}</span>
                            <span style="color: #64748b; font-size: 14px;">↔</span>
                            <span style="font-size: 15px; color: #fafafa; font-weight: 600;">{metric2}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <span style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">{strength_label}</span>
                            <span style="font-size: 20px; font-weight: 700; color: {corr_color}; font-family: 'JetBrains Mono', monospace;">
                                {corr:+.2f}
                            </span>
                        </div>
                    </div>
                    <div style="background: rgba(30, 41, 59, 0.6); height: 10px; border-radius: 5px; overflow: hidden;">
                        <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, {bar_color}, {bar_color}aa); 
                                    border-radius: 5px; transition: width 0.3s ease;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                        <span style="font-size: 13px; color: #94a3b8;">0%</span>
                        <span style="font-size: 14px; color: {bar_color}; font-weight: 500;">{direction} correlation: {abs(corr)*100:.0f}%</span>
                        <span style="font-size: 13px; color: #94a3b8;">100%</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
