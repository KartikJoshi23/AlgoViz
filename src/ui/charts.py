"""
AlgoViz - Professional Charts Module
=================================================

Premium Plotly chart creation with professional trading aesthetics.
Features gradient fills, smooth animations, and professional annotations.

Charts:
1. Live Price + VWAP Crossover (Dual line with gradient fill)
2. Bid-Ask Spread Heatmap Timeline (Gradient bar chart)
3. Order Book Imbalance Indicator (Gauge-style bar)
4. Trade Velocity Gauge (Premium speedometer)
5. Rolling Volatility Monitor (Area chart with bands)
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import COLORS, CHART_CONFIG
from ui.theme import Theme


# =============================================================================
# CHART INSIGHT GENERATOR - Provides contextual insights for each chart
# =============================================================================

class ChartInsights:
    """
    Generates dynamic insights for each chart type based on current data.
    Returns HTML-formatted insight boxes for display under charts.
    """
    
    @staticmethod
    def get_insight_html(title: str, insights: List[Tuple[str, str, str]], 
                        accent_color: str = "#06b6d4") -> str:
        """
        Generate styled insight box HTML.
        
        Args:
            title: Main insight title
            insights: List of (emoji, label, text) tuples
            accent_color: Left border accent color
        """
        insights_html = "".join([
            f'<div style="display: flex; align-items: flex-start; margin-bottom: 6px;">'
            f'<span style="font-size: 14px; margin-right: 8px;">{emoji}</span>'
            f'<div><span style="color: #a0aec0; font-weight: 500;">{label}:</span> '
            f'<span style="color: #e2e8f0;">{text}</span></div></div>'
            for emoji, label, text in insights
        ])
        
        return f'''
        <div style="background: rgba(20, 25, 35, 0.85); border-left: 3px solid {accent_color}; 
                    border-radius: 0 8px 8px 0; padding: 12px 16px; margin-top: 12px;">
            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; 
                        color: {accent_color}; font-weight: 600; margin-bottom: 8px;">
                💡 {title}
            </div>
            {insights_html}
        </div>
        '''
    
    @staticmethod
    def price_vwap_insight(prices: List[float], vwaps: List[float]) -> str:
        """Generate insight for Price & VWAP chart."""
        if not prices or not vwaps:
            return ""
        
        current_price = prices[-1]
        current_vwap = vwaps[-1]
        diff_pct = ((current_price - current_vwap) / current_vwap) * 100
        
        # Trend detection
        if len(prices) >= 5:
            recent_trend = (prices[-1] - prices[-5]) / prices[-5] * 100
            trend_text = f"{'📈 Uptrend' if recent_trend > 0.05 else '📉 Downtrend' if recent_trend < -0.05 else '➡️ Sideways'} ({recent_trend:+.2f}%)"
        else:
            trend_text = "Calculating..."
        
        # Position relative to VWAP
        if diff_pct > 0.1:
            position = "Trading ABOVE VWAP - Bullish bias, buyers dominating"
            position_color = "#10b981"
        elif diff_pct < -0.1:
            position = "Trading BELOW VWAP - Bearish bias, sellers dominating"
            position_color = "#ef4444"
        else:
            position = "Near VWAP - Fair value zone, balanced market"
            position_color = "#f59e0b"
        
        insights = [
            ("📊", "VWAP Position", f"{diff_pct:+.2f}% - {position}"),
            ("📈", "Recent Trend", trend_text),
            ("🎯", "How to Read", "Price above VWAP = bullish; below = bearish. Crossovers signal momentum shifts.")
        ]
        
        return ChartInsights.get_insight_html("Price & VWAP Insight", insights, position_color)
    
    @staticmethod
    def spread_insight(spread_data: List[Dict]) -> str:
        """Generate insight for Spread Heatmap chart."""
        if not spread_data:
            return ""
        
        spreads = [d.get("spread_bps", d.get("spread", 0)) for d in spread_data]
        current = spreads[-1] if spreads else 0
        avg = np.mean(spreads) if spreads else 0
        max_spread = max(spreads) if spreads else 0
        
        # Liquidity assessment
        if current < 3:
            liquidity = "Excellent liquidity - tight spreads indicate strong market"
            color = "#10b981"
        elif current < 5:
            liquidity = "Good liquidity - spreads within normal range"
            color = "#f59e0b"
        else:
            liquidity = "Low liquidity - wide spreads suggest caution"
            color = "#ef4444"
        
        insights = [
            ("📏", "Current Spread", f"{current:.2f} bps ({liquidity})"),
            ("📊", "Average", f"{avg:.2f} bps | Max: {max_spread:.2f} bps"),
            ("🎯", "How to Read", "Lower spread = better liquidity. Wide spreads increase trading costs.")
        ]
        
        return ChartInsights.get_insight_html("Spread Analysis", insights, color)
    
    @staticmethod
    def imbalance_insight(imbalance: float, bid_vol: float, ask_vol: float) -> str:
        """Generate insight for Order Book Imbalance chart."""
        total = bid_vol + ask_vol
        bid_pct = (bid_vol / total * 100) if total > 0 else 50
        
        if imbalance > 0.3:
            direction = "Strong BUY pressure - buyers overwhelming sellers"
            color = "#10b981"
        elif imbalance > 0:
            direction = "Mild BUY pressure - slight buyer advantage"
            color = "#22c55e"
        elif imbalance > -0.3:
            direction = "Mild SELL pressure - slight seller advantage"
            color = "#f97316"
        else:
            direction = "Strong SELL pressure - sellers overwhelming buyers"
            color = "#ef4444"
        
        insights = [
            ("⚖️", "Imbalance", f"{imbalance*100:+.1f}% - {direction}"),
            ("📊", "Volume Split", f"Bids: {bid_pct:.1f}% | Asks: {100-bid_pct:.1f}%"),
            ("🎯", "How to Read", "Positive = buy pressure (bullish). Negative = sell pressure (bearish).")
        ]
        
        return ChartInsights.get_insight_html("Order Book Insight", insights, color)
    
    @staticmethod
    def velocity_insight(velocity: float, baseline: float) -> str:
        """Generate insight for Trade Velocity chart."""
        ratio = velocity / baseline if baseline > 0 else 1
        
        if ratio > 2:
            status = "VELOCITY SPIKE - Unusual trading activity detected"
            color = "#ef4444"
        elif ratio > 1.5:
            status = "Elevated velocity - Increased market interest"
            color = "#f97316"
        elif ratio > 1.2:
            status = "Above average - Market picking up momentum"
            color = "#f59e0b"
        else:
            status = "Normal velocity - Typical market conditions"
            color = "#10b981"
        
        insights = [
            ("⚡", "Current Rate", f"{velocity:.1f} trades/sec ({ratio:.1f}x baseline)"),
            ("📊", "Status", status),
            ("🎯", "How to Read", "High velocity often precedes price movements. Spikes may signal news events.")
        ]
        
        return ChartInsights.get_insight_html("Velocity Analysis", insights, color)
    
    @staticmethod
    def volatility_insight(volatility_data: List[Dict]) -> str:
        """Generate insight for Volatility chart."""
        if not volatility_data:
            return ""
        
        vols = [d.get("volatility_bps", d.get("volatility", 0)) for d in volatility_data]
        current = vols[-1] if vols else 0
        avg = np.mean(vols) if vols else 0
        trend = (vols[-1] - vols[0]) / max(vols[0], 1) * 100 if len(vols) > 1 else 0
        
        if current < 15:
            regime = "Low volatility - Market is calm, tight ranges expected"
            color = "#10b981"
        elif current < 20:
            regime = "Moderate volatility - Normal market conditions"
            color = "#f59e0b"
        else:
            regime = "High volatility - Increased risk, wider price swings"
            color = "#ef4444"
        
        trend_text = f"{'Rising ↑' if trend > 5 else 'Falling ↓' if trend < -5 else 'Stable →'} ({trend:+.1f}%)"
        
        insights = [
            ("📉", "Current Level", f"{current:.1f} bps - {regime}"),
            ("📈", "Trend", trend_text + f" | Avg: {avg:.1f} bps"),
            ("🎯", "How to Read", "Higher volatility = larger price moves. Low vol often precedes breakouts.")
        ]
        
        return ChartInsights.get_insight_html("Volatility Analysis", insights, color)
    
    # ==========================================================================
    # ADDITIONAL INSIGHT METHODS FOR ALL CHARTS
    # ==========================================================================
    
    @staticmethod
    def distribution_insight(prices: List[float], data_type: str = "Price") -> str:
        """Generate insight for Distribution charts (histogram)."""
        if not prices or len(prices) < 2:
            return ""
        
        mean_val = np.mean(prices)
        std_val = np.std(prices)
        min_val = np.min(prices)
        max_val = np.max(prices)
        range_val = max_val - min_val
        cv = (std_val / mean_val * 100) if mean_val != 0 else 0
        
        # Assess distribution shape
        if cv < 1:
            shape = "Very tight distribution - Low variability, stable market"
            color = "#10b981"
        elif cv < 3:
            shape = "Normal distribution - Healthy price range"
            color = "#3b82f6"
        else:
            shape = "Wide distribution - High variability, choppy market"
            color = "#f59e0b"
        
        insights = [
            ("📊", "Distribution", f"{shape}"),
            ("📏", "Statistics", f"Mean: ${mean_val:,.2f} | Std: ${std_val:,.2f} | Range: ${range_val:,.2f}"),
            ("🎯", "How to Read", f"Histogram shows {data_type.lower()} frequency. Concentrated peak = stable; wide spread = volatile.")
        ]
        
        return ChartInsights.get_insight_html(f"{data_type} Distribution Insight", insights, color)
    
    @staticmethod
    def returns_insight(returns: List[float]) -> str:
        """Generate insight for Return Distribution chart."""
        if not returns or len(returns) < 2:
            return ""
        
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        skewness = np.mean(((np.array(returns) - mean_ret) / (std_ret if std_ret > 0 else 1)) ** 3) if std_ret > 0 else 0
        
        # Assess return profile
        if mean_ret > 0.01:
            profile = "Positive bias - Bullish momentum in returns"
            color = "#10b981"
        elif mean_ret < -0.01:
            profile = "Negative bias - Bearish momentum in returns"
            color = "#ef4444"
        else:
            profile = "Neutral - Returns centered around zero"
            color = "#f59e0b"
        
        skew_text = "Right-skewed (more upside)" if skewness > 0.5 else "Left-skewed (more downside)" if skewness < -0.5 else "Symmetric"
        
        insights = [
            ("📈", "Return Profile", f"{profile}"),
            ("📊", "Skewness", f"{skew_text} (skew: {skewness:.2f})"),
            ("🎯", "How to Read", "Normal distribution = predictable; fat tails = extreme moves more likely.")
        ]
        
        return ChartInsights.get_insight_html("Return Distribution Insight", insights, color)
    
    @staticmethod
    def correlation_insight(var1_name: str, var2_name: str, corr_value: float) -> str:
        """Generate insight for Correlation/Scatter charts."""
        abs_corr = abs(corr_value)
        
        if abs_corr > 0.7:
            strength = "Strong correlation - High predictive relationship"
            color = "#10b981"
        elif abs_corr > 0.4:
            strength = "Moderate correlation - Some predictive value"
            color = "#f59e0b"
        else:
            strength = "Weak correlation - Limited relationship"
            color = "#6b7280"
        
        direction = "positive (move together)" if corr_value > 0 else "negative (move opposite)"
        
        insights = [
            ("🔗", "Correlation", f"{corr_value:.3f} - {direction}"),
            ("📊", "Strength", strength),
            ("🎯", "How to Read", f"When {var1_name} moves, {var2_name} tends to move {'in same' if corr_value > 0 else 'opposite'} direction.")
        ]
        
        return ChartInsights.get_insight_html(f"{var1_name} vs {var2_name} Insight", insights, color)
    
    @staticmethod
    def ml_prediction_insight(direction: str, confidence: float, momentum: float) -> str:
        """Generate insight for ML Prediction Radar Dial."""
        if "up" in direction.lower():
            signal = "BULLISH signal - Model predicts upward movement"
            color = "#10b981"
        elif "down" in direction.lower():
            signal = "BEARISH signal - Model predicts downward movement"
            color = "#ef4444"
        else:
            signal = "NEUTRAL signal - No clear directional bias"
            color = "#f59e0b"
        
        conf_level = "High confidence" if confidence > 70 else "Moderate confidence" if confidence > 50 else "Low confidence"
        mom_text = f"{'Bullish' if momentum > 10 else 'Bearish' if momentum < -10 else 'Neutral'} momentum ({momentum:+.0f})"
        
        insights = [
            ("🤖", "ML Signal", signal),
            ("🎯", "Confidence", f"{conf_level} at {confidence:.0f}% | {mom_text}"),
            ("💡", "How to Read", "Needle direction shows prediction. Larger radius = higher confidence. Use with other indicators.")
        ]
        
        return ChartInsights.get_insight_html("ML Prediction Insight", insights, color)
    
    @staticmethod
    def momentum_insight(momentum: float) -> str:
        """Generate insight for Momentum Oscilloscope."""
        abs_mom = abs(momentum)
        
        if momentum > 30:
            status = "STRONG BULLISH - Major buying pressure detected"
            color = "#10b981"
        elif momentum > 10:
            status = "Bullish - Moderate upward momentum"
            color = "#22c55e"
        elif momentum < -30:
            status = "STRONG BEARISH - Major selling pressure detected"
            color = "#ef4444"
        elif momentum < -10:
            status = "Bearish - Moderate downward momentum"
            color = "#f97316"
        else:
            status = "Neutral - No significant directional bias"
            color = "#64748b"
        
        wave_text = "High amplitude" if abs_mom > 50 else "Medium amplitude" if abs_mom > 20 else "Low amplitude"
        
        insights = [
            ("⚡", "Momentum", f"{momentum:+.0f} - {status}"),
            ("📊", "Wave Strength", f"{wave_text} oscillation | Baseline deviation: {abs_mom:.0f} pts"),
            ("🎯", "How to Read", "Wave peaks show momentum intensity. Above zero = bullish; below = bearish. Large waves = strong moves.")
        ]
        
        return ChartInsights.get_insight_html("Momentum Oscilloscope Insight", insights, color)
    
    @staticmethod
    def regime_insight(regime: str, confidence: float) -> str:
        """Generate insight for Regime Heartbeat Monitor."""
        regime_descriptions = {
            "trending_up": ("Bullish trend in progress - Follow the momentum", "#10b981"),
            "trending_down": ("Bearish trend in progress - Exercise caution", "#ef4444"),
            "ranging": ("Sideways market - Trade the range boundaries", "#64748b"),
            "volatile": ("High volatility regime - Wider stops needed", "#f59e0b"),
            "breakout": ("Potential breakout forming - Watch for confirmation", "#8b5cf6")
        }
        
        regime_key = regime.lower().replace(" ", "_") if regime else "ranging"
        description, color = regime_descriptions.get(regime_key, ("Unknown regime", "#6b7280"))
        
        pulse_text = "Strong pulse" if confidence > 70 else "Moderate pulse" if confidence > 50 else "Weak pulse"
        
        insights = [
            ("💓", "Regime", f"{regime.replace('_', ' ').title()} - {description}"),
            ("📊", "Confidence", f"{pulse_text} at {confidence:.0f}% certainty"),
            ("🎯", "How to Read", "Heartbeat rhythm shows market character. Tall spikes = high confidence. Flat line = uncertain.")
        ]
        
        return ChartInsights.get_insight_html("Market Regime Insight", insights, color)
    
    @staticmethod
    def candlestick_insight(candles: List[Dict]) -> str:
        """Generate insight for Candlestick chart."""
        if not candles or len(candles) < 2:
            return ""
        
        last_candle = candles[-1]
        prev_candle = candles[-2]
        
        # Determine candle color and pattern
        body_size = abs(last_candle['close'] - last_candle['open'])
        wick_size = last_candle['high'] - last_candle['low']
        is_bullish = last_candle['close'] > last_candle['open']
        
        # Simple pattern detection
        if body_size < wick_size * 0.3:
            pattern = "Doji - Indecision, potential reversal"
            color = "#f59e0b"
        elif is_bullish and body_size > wick_size * 0.6:
            pattern = "Bullish Marubozu - Strong buying pressure"
            color = "#10b981"
        elif not is_bullish and body_size > wick_size * 0.6:
            pattern = "Bearish Marubozu - Strong selling pressure"
            color = "#ef4444"
        elif is_bullish:
            pattern = "Bullish candle - Buyers in control"
            color = "#22c55e"
        else:
            pattern = "Bearish candle - Sellers in control"
            color = "#f97316"
        
        change = ((last_candle['close'] - prev_candle['close']) / prev_candle['close']) * 100
        
        insights = [
            ("🕯️", "Pattern", pattern),
            ("📊", "Change", f"{change:+.2f}% | Open: ${last_candle['open']:,.0f} → Close: ${last_candle['close']:,.0f}"),
            ("🎯", "How to Read", "Green = bullish, Red = bearish. Long body = strong move. Long wicks = rejection.")
        ]
        
        return ChartInsights.get_insight_html("Candlestick Pattern Insight", insights, color)
    
    @staticmethod
    def depth_insight(bids: List, asks: List) -> str:
        """Generate insight for Order Book Depth chart."""
        if not bids or not asks:
            return ""
        
        # Handle both tuple format (price, vol) and dict format {"price": x, "quantity": y}
        def get_price(item):
            if isinstance(item, dict):
                return item.get("price", 0)
            return item[0]
        
        def get_vol(item):
            if isinstance(item, dict):
                return item.get("quantity", item.get("volume", 0))
            return item[1]
        
        total_bid_vol = sum(get_vol(b) for b in bids)
        total_ask_vol = sum(get_vol(a) for a in asks)
        imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol) if (total_bid_vol + total_ask_vol) > 0 else 0
        
        best_bid = max(get_price(b) for b in bids) if bids else 0
        best_ask = min(get_price(a) for a in asks) if asks else 0
        spread = best_ask - best_bid if best_ask > best_bid else 0
        
        if imbalance > 0.2:
            pressure = "Strong BID wall - Significant buy-side support"
            color = "#10b981"
        elif imbalance < -0.2:
            pressure = "Strong ASK wall - Significant sell-side resistance"
            color = "#ef4444"
        else:
            pressure = "Balanced book - Equal buy/sell pressure"
            color = "#3b82f6"
        
        insights = [
            ("📊", "Depth Analysis", pressure),
            ("📏", "Spread", f"${spread:,.2f} | Bid Vol: {total_bid_vol:.2f} | Ask Vol: {total_ask_vol:.2f}"),
            ("🎯", "How to Read", "Steeper slope = more liquidity. Walls show support/resistance. Imbalance predicts short-term direction.")
        ]
        
        return ChartInsights.get_insight_html("Order Book Depth Insight", insights, color)
    
    @staticmethod
    def equity_curve_insight(equity_data: List[Tuple], initial_capital: float) -> str:
        """Generate insight for Backtest Equity Curve."""
        if not equity_data or len(equity_data) < 2:
            return ""
        
        final_equity = equity_data[-1][1]
        total_return = ((final_equity - initial_capital) / initial_capital) * 100
        
        # Calculate max drawdown
        equity_values = [e[1] for e in equity_data]
        peak = equity_values[0]
        max_dd = 0
        for val in equity_values:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        if total_return > 10:
            performance = "Strong performance - Strategy outperforming"
            color = "#10b981"
        elif total_return > 0:
            performance = "Positive return - Strategy is profitable"
            color = "#22c55e"
        elif total_return > -5:
            performance = "Minor loss - Strategy needs optimization"
            color = "#f59e0b"
        else:
            performance = "Significant loss - Review strategy parameters"
            color = "#ef4444"
        
        insights = [
            ("💰", "Performance", performance),
            ("📊", "Returns", f"Total: {total_return:+.2f}% | Max Drawdown: -{max_dd:.2f}%"),
            ("🎯", "How to Read", "Smooth upward curve = consistent profits. Sharp drops = drawdowns. Steeper slope = better returns.")
        ]
        
        return ChartInsights.get_insight_html("Equity Curve Insight", insights, color)
    
    @staticmethod
    def trade_distribution_insight(trades: List) -> str:
        """Generate insight for Trade Distribution chart."""
        if not trades:
            return ""
        
        wins = [t for t in trades if hasattr(t, 'pnl') and t.pnl > 0]
        losses = [t for t in trades if hasattr(t, 'pnl') and t.pnl <= 0]
        
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        if win_rate > 55 and profit_factor > 1.5:
            quality = "Excellent edge - High win rate with good risk/reward"
            color = "#10b981"
        elif win_rate > 50 or profit_factor > 1.2:
            quality = "Positive edge - Strategy has merit"
            color = "#22c55e"
        else:
            quality = "Weak edge - Consider strategy adjustments"
            color = "#f59e0b"
        
        insights = [
            ("🎯", "Trade Quality", quality),
            ("📊", "Statistics", f"Win Rate: {win_rate:.1f}% | Profit Factor: {profit_factor:.2f}"),
            ("💡", "How to Read", "Right-skewed = more winners. Tall bars at positive values = consistent profits. Check for outliers.")
        ]
        
        return ChartInsights.get_insight_html("Trade Distribution Insight", insights, color)


class Charts:
    """
    Creates premium dashboard charts using Plotly Graph Objects.
    
    Each method returns a Plotly Figure ready for display.
    """
    
    # ==========================================================================
    # CHART 1: LIVE PRICE + VWAP CROSSOVER (PREMIUM ENHANCED)
    # ==========================================================================
    
    @staticmethod
    def create_price_vwap_chart(price_data: List[Dict], 
                                 height: int = 300,
                                 line_shape: str = "spline") -> go.Figure:
        """
        Create premium dual line chart showing price and VWAP overlay.
        Features gradient fill, crossover markers, and price channel bands.
        
        Args:
            price_data: List of price data dictionaries
            height: Chart height in pixels
            line_shape: Line interpolation style ('spline', 'linear', 'hv')
        """
        fig = go.Figure()
        
        if not price_data:
            # Show animated loading state
            fig.add_annotation(
                text="📡 Connecting to market feed...",
                xref="paper", yref="paper",
                x=0.5, y=0.55,
                showarrow=False,
                font=dict(size=18, color="#f59e0b", family="Inter")
            )
            fig.add_annotation(
                text="Live data will appear shortly",
                xref="paper", yref="paper",
                x=0.5, y=0.42,
                showarrow=False,
                font=dict(size=12, color=Theme.TEXT_MUTED, family="Inter")
            )
            # Add a pulsing circle effect
            fig.add_shape(
                type="circle",
                xref="paper", yref="paper",
                x0=0.45, y0=0.65, x1=0.55, y1=0.75,
                fillcolor="rgba(245, 158, 11, 0.2)",
                line=dict(color="#f59e0b", width=2)
            )
        else:
            timestamps = [d["timestamp"] for d in price_data]
            prices = [d["price"] for d in price_data]
            vwaps = [d["vwap"] for d in price_data]
            
            # Calculate price channel (high/low envelope)
            window = min(10, len(prices))
            if window > 1:
                upper_channel = []
                lower_channel = []
                for i in range(len(prices)):
                    start_idx = max(0, i - window + 1)
                    window_data = prices[start_idx:i+1]
                    upper_channel.append(max(window_data))
                    lower_channel.append(min(window_data))
                
                # Price channel band (envelope effect)
                fig.add_trace(go.Scatter(
                    x=timestamps + timestamps[::-1],
                    y=upper_channel + lower_channel[::-1],
                    fill="toself",
                    fillcolor="rgba(251, 191, 36, 0.08)",
                    line=dict(color="rgba(0,0,0,0)"),
                    name="Price Channel",
                    hoverinfo="skip",
                    showlegend=True
                ))
            
            # VWAP line first (so price line is on top) - PURPLE color, wider for visibility
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=vwaps,
                mode="lines",
                name="📐 VWAP",
                line=dict(color="#a78bfa", width=3, dash="dash", shape=line_shape),
                hovertemplate="<b>VWAP</b>: $%{y:,.2f}<extra></extra>"
            ))
            
            # Price line with gradient fill - GOLD color, thicker for big screen
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=prices,
                mode="lines",
                name="💰 Price",
                line=dict(color="#fbbf24", width=4, shape=line_shape),
                fill="tonexty",
                fillcolor="rgba(251, 191, 36, 0.15)",
                hovertemplate="<b>Price</b>: $%{y:,.2f}<extra></extra>"
            ))
            
            # Crossover markers with enhanced visibility
            crossovers_x = []
            crossovers_y = []
            crossover_colors = []
            crossover_labels = []
            crossover_symbols = []
            
            for i in range(1, len(prices)):
                prev_diff = prices[i-1] - vwaps[i-1]
                curr_diff = prices[i] - vwaps[i]
                
                if prev_diff * curr_diff < 0:
                    crossovers_x.append(timestamps[i])
                    crossovers_y.append(prices[i])
                    if curr_diff > 0:
                        crossover_colors.append(Theme.GREEN)
                        crossover_labels.append("🔼 Bullish Cross")
                        crossover_symbols.append("triangle-up")
                    else:
                        crossover_colors.append(Theme.RED)
                        crossover_labels.append("🔽 Bearish Cross")
                        crossover_symbols.append("triangle-down")
            
            if crossovers_x:
                fig.add_trace(go.Scatter(
                    x=crossovers_x,
                    y=crossovers_y,
                    mode="markers",
                    name="✨ Crossover",
                    marker=dict(
                        size=16,
                        color=crossover_colors,
                        symbol=crossover_symbols,
                        line=dict(width=2, color="white")
                    ),
                    text=crossover_labels,
                    hovertemplate="<b>%{text}</b><br>Price: $%{y:,.2f}<extra></extra>"
                ))
            
            # Add price annotations with enhanced styling
            if prices:
                last_price = prices[-1]
                first_price = prices[0]
                change = ((last_price - first_price) / first_price) * 100 if first_price else 0
                change_color = "#10b981" if change >= 0 else "#ef4444"
                change_arrow = "▲" if change >= 0 else "▼"
                
                # Current price annotation
                fig.add_annotation(
                    x=timestamps[-1],
                    y=last_price,
                    text=f"${last_price:,.2f}",
                    showarrow=True,
                    arrowhead=0,
                    arrowcolor=Theme.CYAN,
                    arrowwidth=2,
                    ax=50,
                    ay=0,
                    font=dict(color=Theme.CYAN, size=13, family="JetBrains Mono"),
                    bgcolor="rgba(20, 25, 35, 0.95)",
                    borderpad=6,
                    bordercolor=Theme.CYAN,
                    borderwidth=2
                )
                
                # Change indicator at top right
                fig.add_annotation(
                    x=1.0, y=1.05,
                    xref="paper", yref="paper",
                    text=f"<b>{change_arrow} {abs(change):.2f}%</b>",
                    showarrow=False,
                    font=dict(color=change_color, size=14, family="JetBrains Mono"),
                    bgcolor="rgba(20, 25, 35, 0.9)",
                    borderpad=6,
                    bordercolor=change_color,
                    borderwidth=1,
                    xanchor="right"
                )
        
        # Apply premium layout
        layout = Theme.get_base_layout("Live Price & VWAP Crossover", height)
        layout["yaxis"]["title"] = dict(text="Price (USD)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["yaxis"]["tickprefix"] = "$"
        layout["yaxis"]["tickformat"] = ",.0f"
        layout["yaxis"]["gridcolor"] = "rgba(255,255,255,0.08)"
        layout["xaxis"]["title"] = dict(text="Time", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["xaxis"]["gridcolor"] = "rgba(255,255,255,0.05)"
        layout["margin"] = dict(l=80, r=70, t=60, b=70)
        layout["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=-0.18,
            xanchor="center",
            x=0.5,
            font=dict(color=Theme.TEXT_SECONDARY, size=11, family="Inter"),
            bgcolor="rgba(20, 25, 35, 0.8)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1
        )
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 2: SPREAD POLAR RADAR - UNIQUE LIQUIDITY VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_spread_heatmap(spread_data: List[Dict], 
                               height: int = 300) -> go.Figure:
        """
        Create a unique POLAR RADAR chart showing spread over time.
        Each time point is a spoke on the radar, with spread as the radius.
        Color intensity shows liquidity quality.
        """
        fig = go.Figure()
        
        if not spread_data:
            fig.add_annotation(
                text="📊 Collecting spread data...",
                xref="paper", yref="paper",
                x=0.5, y=0.55,
                showarrow=False,
                font=dict(size=18, color="#8b5cf6", family="Inter")
            )
            fig.add_annotation(
                text="Radar will populate shortly",
                xref="paper", yref="paper",
                x=0.5, y=0.42,
                showarrow=False,
                font=dict(size=12, color=Theme.TEXT_MUTED, family="Inter")
            )
            max_spread = 10
            max_val = 10
            display_unit = "bps"
            scale_factor = 1
        else:
            spreads = [d["spread_bps"] for d in spread_data]
            times = [d["timestamp"].strftime("%M:%S") for d in spread_data]
            max_spread_raw = max(spreads) if spreads else 0.001
            
            # Auto-detect scale: if max spread < 0.1 bps, show in micro-bps (0.0001 bps = 1 μbps)
            # This is common for highly liquid pairs like BTC/USDT
            if max_spread_raw < 0.1:
                # Scale to micro-basis points (multiply by 1000)
                scale_factor = 1000
                display_unit = "μbps"
                spreads_scaled = [s * scale_factor for s in spreads]
                max_spread = max(spreads_scaled) if spreads_scaled else 10
                # Adjust thresholds for μbps (1 bps = 1000 μbps)
                tight_threshold = 500  # 0.5 bps
                normal_threshold = 1000  # 1 bps
                wide_threshold = 2000  # 2 bps
            elif max_spread_raw < 1:
                # Scale to milli-basis points (multiply by 100)
                scale_factor = 100
                display_unit = "0.01 bps"
                spreads_scaled = [s * scale_factor for s in spreads]
                max_spread = max(spreads_scaled) if spreads_scaled else 10
                tight_threshold = 50  # 0.5 bps
                normal_threshold = 100  # 1 bps
                wide_threshold = 200  # 2 bps
            else:
                # Normal bps display
                scale_factor = 1
                display_unit = "bps"
                spreads_scaled = spreads
                max_spread = max(spreads) if spreads else 10
                tight_threshold = 3
                normal_threshold = 5
                wide_threshold = 7
            
            # Generate colors based on spread quality (using original bps values)
            colors = []
            for s in spreads:
                if s < 0.01:  # Extremely tight (sub-cent spread)
                    colors.append("#10b981")  # Green
                elif s < 0.1:  # Very tight
                    colors.append("#22c55e")
                elif s < 1:   # Tight
                    colors.append("#14b8a6")
                elif s < 3:   # Normal
                    colors.append("#f59e0b")
                elif s < 5:
                    colors.append("#f97316")
                else:
                    colors.append("#ef4444")  # Wide
            
            # Create polar area chart (radar style)
            # Normalize spreads for better visual (invert so tight = larger area)
            max_val = max(10, max_spread * 1.2)
            inverted_spreads = [max_val - s for s in spreads_scaled]  # Invert so tight spread = bigger
            
            # Main polar area - shows "liquidity quality" (bigger = better)
            fig.add_trace(go.Scatterpolar(
                r=inverted_spreads,
                theta=times,
                fill='toself',
                fillcolor='rgba(16, 185, 129, 0.3)',
                line=dict(color='#10b981', width=2),
                name='Liquidity Quality',
                hovertemplate="<b>Time</b>: %{theta}<br><b>Spread</b>: " + 
                             "%{customdata:.4f} bps<extra></extra>",
                customdata=spreads  # Original bps values
            ))
            
            # Add spread points as markers with color coding
            fig.add_trace(go.Scatterpolar(
                r=inverted_spreads,
                theta=times,
                mode='markers',
                marker=dict(
                    size=12,
                    color=colors,
                    line=dict(width=2, color='white'),
                    symbol='circle'
                ),
                name='Spread Points',
                showlegend=False,
                hoverinfo='skip'
            ))
            
            # Add threshold circles (using scaled thresholds)
            if scale_factor == 1:
                # Normal bps thresholds
                fig.add_trace(go.Scatterpolar(
                    r=[max_val - 3] * len(times) + [max_val - 3],
                    theta=times + [times[0]],
                    mode='lines',
                    line=dict(color='#f59e0b', width=2, dash='dash'),
                    name='Normal (3 bps)',
                    hoverinfo='skip'
                ))
                
                fig.add_trace(go.Scatterpolar(
                    r=[max_val - 5] * len(times) + [max_val - 5],
                    theta=times + [times[0]],
                    mode='lines',
                    line=dict(color='#ef4444', width=2, dash='dash'),
                    name='Wide (5 bps)',
                    hoverinfo='skip'
                ))
            
            # Current spread indicator
            current_spread = spreads[-1] if spreads else 0
            current_spread_scaled = spreads_scaled[-1] if spreads_scaled else 0
            
            # Status based on original bps value
            if current_spread < 0.1:
                status = "🟢 EXCELLENT"
                status_color = "#10b981"
            elif current_spread < 1:
                status = "🟢 TIGHT"
                status_color = "#22c55e"
            elif current_spread < 3:
                status = "🟡 NORMAL"
                status_color = "#f59e0b"
            else:
                status = "🔴 WIDE"
                status_color = "#ef4444"
            
            # Center annotation with current value
            if scale_factor > 1:
                display_value = f"{current_spread_scaled:.1f}"
            else:
                display_value = f"{current_spread:.2f}"
            
            fig.add_annotation(
                x=0.5, y=0.5,
                xref="paper", yref="paper",
                text=f"<b style='font-size:24px;color:{status_color}'>{display_value}</b><br>"
                     f"<span style='font-size:11px;color:#a0aec0'>{display_unit}</span>",
                showarrow=False,
                font=dict(size=14, color=status_color, family="JetBrains Mono"),
                align="center"
            )
        
        # Polar layout
        fig.update_layout(
            polar=dict(
                bgcolor="rgba(20, 25, 35, 0.6)",
                radialaxis=dict(
                    visible=True,
                    range=[0, max_val if spread_data else 10],
                    tickfont=dict(color=Theme.TEXT_MUTED, size=9),
                    gridcolor="rgba(255,255,255,0.1)",
                    linecolor="rgba(255,255,255,0.2)"
                ),
                angularaxis=dict(
                    tickfont=dict(color=Theme.TEXT_PRIMARY, size=11),
                    gridcolor="rgba(255,255,255,0.1)",
                    linecolor="rgba(255,255,255,0.2)",
                    direction="clockwise"
                )
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color=Theme.TEXT_PRIMARY, family="Inter"),
            height=height,
            margin=dict(l=80, r=80, t=60, b=80),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.20,
                xanchor="center",
                x=0.5,
                font=dict(size=10, color=Theme.TEXT_SECONDARY),
                bgcolor="rgba(0,0,0,0)"
            ),
            title=dict(
                text=f"<b>Spread Radar</b> • Unit: {display_unit if spread_data else 'bps'}",
                font=dict(size=14, color=Theme.TEXT_PRIMARY),
                x=0.5,
                xanchor="center"
            )
        )
        
        return fig
    
    # ==========================================================================
    # CHART 3: ORDER BOOK IMBALANCE - TUG OF WAR VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_imbalance_chart(imbalance: float, 
                                bid_volume: float,
                                ask_volume: float,
                                height: int = 250) -> go.Figure:
        """
        Create a unique TUG-OF-WAR style visualization for order book imbalance.
        Shows bulls vs bears as opposing forces with a rope being pulled.
        """
        fig = go.Figure()
        
        imbalance_pct = imbalance * 100
        total_vol = bid_volume + ask_volume
        bid_pct = (bid_volume / total_vol * 100) if total_vol > 0 else 50
        ask_pct = (ask_volume / total_vol * 100) if total_vol > 0 else 50
        
        # Determine winner and colors
        if imbalance > 0.3:
            winner = "BULLS"
            winner_color = "#10b981"
            status = "🐂 BULLS DOMINATING"
            rope_position = imbalance * 40
        elif imbalance > 0:
            winner = "BULLS"
            winner_color = "#22c55e"
            status = "🐂 Bulls Leading"
            rope_position = imbalance * 40
        elif imbalance > -0.3:
            winner = "BEARS"
            winner_color = "#f97316"
            status = "🐻 Bears Leading"
            rope_position = imbalance * 40
        else:
            winner = "BEARS"
            winner_color = "#ef4444"
            status = "🐻 BEARS DOMINATING"
            rope_position = imbalance * 40
        
        # Create the "rope" - a thick horizontal line
        fig.add_trace(go.Scatter(
            x=[-50, 50],
            y=[1, 1],
            mode='lines',
            line=dict(color='#94a3b8', width=8),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Center marker (the "knot")
        fig.add_trace(go.Scatter(
            x=[rope_position],
            y=[1],
            mode='markers',
            marker=dict(
                size=35,
                color=winner_color,
                symbol='diamond',
                line=dict(width=3, color='white')
            ),
            name='Position',
            showlegend=False,
            hovertemplate=f"<b>Imbalance</b>: {imbalance_pct:+.1f}%<extra></extra>"
        ))
        
        # BULLS side (right) - green zone
        fig.add_trace(go.Scatter(
            x=[10, 20, 30, 40, 50],
            y=[1, 1, 1, 1, 1],
            mode='markers+text',
            marker=dict(
                size=[15, 20, 25, 30, 35],
                color=['rgba(16,185,129,0.3)', 'rgba(16,185,129,0.4)', 
                       'rgba(16,185,129,0.5)', 'rgba(16,185,129,0.6)', 'rgba(16,185,129,0.8)'],
                symbol='triangle-right',
                line=dict(width=1, color='#10b981')
            ),
            text=['', '', '', '', '🐂'],
            textposition='middle center',
            textfont=dict(size=20),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # BEARS side (left) - red zone
        fig.add_trace(go.Scatter(
            x=[-10, -20, -30, -40, -50],
            y=[1, 1, 1, 1, 1],
            mode='markers+text',
            marker=dict(
                size=[15, 20, 25, 30, 35],
                color=['rgba(239,68,68,0.3)', 'rgba(239,68,68,0.4)', 
                       'rgba(239,68,68,0.5)', 'rgba(239,68,68,0.6)', 'rgba(239,68,68,0.8)'],
                symbol='triangle-left',
                line=dict(width=1, color='#ef4444')
            ),
            text=['', '', '', '', '🐻'],
            textposition='middle center',
            textfont=dict(size=20),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Zone backgrounds
        fig.add_vrect(x0=-50, x1=0, fillcolor="#ef4444", opacity=0.08, line_width=0)
        fig.add_vrect(x0=0, x1=50, fillcolor="#10b981", opacity=0.08, line_width=0)
        
        # Center line
        fig.add_vline(x=0, line_color="rgba(255,255,255,0.5)", line_width=2, line_dash="dash")
        
        # Volume bars at bottom
        fig.add_trace(go.Bar(
            x=[-bid_pct/2],
            y=[0.3],
            orientation='h',
            marker=dict(color='#ef4444', opacity=0.7),
            width=0.15,
            showlegend=False,
            hovertemplate=f"<b>Ask Volume</b>: {ask_volume:.4f}<extra></extra>"
        ))
        
        fig.add_trace(go.Bar(
            x=[bid_pct/2],
            y=[0.3],
            orientation='h',
            marker=dict(color='#10b981', opacity=0.7),
            width=0.15,
            showlegend=False,
            hovertemplate=f"<b>Bid Volume</b>: {bid_volume:.4f}<extra></extra>"
        ))
        
        # Layout
        layout = Theme.get_base_layout("", height)
        layout["title"] = dict(
            text=f"<b>Order Book Tug-of-War</b> • <span style='color:{winner_color}'>{status}</span>",
            font=dict(size=14, color=Theme.TEXT_PRIMARY),
            x=0.5,
            xanchor="center"
        )
        layout["xaxis"]["range"] = [-55, 55]
        layout["xaxis"]["visible"] = False
        layout["yaxis"]["range"] = [0, 1.5]
        layout["yaxis"]["visible"] = False
        layout["showlegend"] = False
        layout["margin"] = dict(l=40, r=40, t=60, b=40)
        
        # Annotations for volume info
        layout["annotations"] = [
            dict(
                x=-45, y=0.15, xref="x", yref="y",
                text=f"<b>SELL</b><br>{ask_volume:.3f}",
                showarrow=False,
                font=dict(color="#ef4444", size=12, family="JetBrains Mono"),
                align="center"
            ),
            dict(
                x=45, y=0.15, xref="x", yref="y",
                text=f"<b>BUY</b><br>{bid_volume:.3f}",
                showarrow=False,
                font=dict(color="#10b981", size=12, family="JetBrains Mono"),
                align="center"
            ),
            dict(
                x=0, y=1.35, xref="x", yref="y",
                text=f"<b style='font-size:20px;color:{winner_color}'>{imbalance_pct:+.1f}%</b>",
                showarrow=False,
                font=dict(color=winner_color, size=14, family="JetBrains Mono"),
                align="center"
            ),
        ]
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 4: TRADE VELOCITY STREAM - UNIQUE BURST VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_velocity_gauge(velocity: float,
                               baseline: float,
                               height: int = 250,
                               velocity_history: List[float] = None) -> go.Figure:
        """
        Create a unique VELOCITY STREAM chart showing trade bursts over time.
        Instead of a static gauge, shows a flowing stream with burst markers.
        Falls back to enhanced gauge if no history provided.
        """
        fig = go.Figure()
        
        ratio = velocity / baseline if baseline > 0 else 1
        
        # Determine colors based on velocity
        if ratio > 2:
            main_color = "#ef4444"
            status = "🔴 VELOCITY SPIKE"
            glow_color = "rgba(239, 68, 68, 0.4)"
        elif ratio > 1.5:
            main_color = "#f97316"
            status = "🟠 ELEVATED"
            glow_color = "rgba(249, 115, 22, 0.3)"
        elif ratio > 1.2:
            main_color = "#f59e0b"
            status = "🟡 RISING"
            glow_color = "rgba(245, 158, 11, 0.3)"
        else:
            main_color = "#10b981"
            status = "🟢 NORMAL"
            glow_color = "rgba(16, 185, 129, 0.3)"
        
        # Generate synthetic history if not provided (for demo)
        if velocity_history is None:
            # Create realistic velocity pattern
            np.random.seed(int(velocity * 100) % 100)
            base = baseline * 0.8
            velocity_history = []
            for i in range(20):
                noise = np.random.randn() * baseline * 0.3
                trend = (velocity - baseline) * (i / 20)  # Trend towards current
                velocity_history.append(max(1, base + trend + noise))
            velocity_history.append(velocity)  # Current value at end
        
        x_vals = list(range(len(velocity_history)))
        
        # Create flowing stream area
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=velocity_history,
            mode='lines',
            fill='tozeroy',
            fillcolor=glow_color,
            line=dict(color=main_color, width=3, shape='spline'),
            name='Velocity Stream',
            hovertemplate="<b>Velocity</b>: %{y:.1f}/sec<extra></extra>"
        ))
        
        # Add baseline reference line
        fig.add_hline(
            y=baseline,
            line_dash="dash",
            line_color="#22d3ee",
            line_width=2,
            annotation_text=f"Baseline: {baseline:.1f}",
            annotation_position="right",
            annotation_font=dict(color="#22d3ee", size=11)
        )
        
        # Add burst markers for spikes (when velocity > 1.5x baseline)
        burst_x = []
        burst_y = []
        burst_sizes = []
        for i, v in enumerate(velocity_history):
            if baseline > 0 and v > baseline * 1.5:
                burst_x.append(i)
                burst_y.append(v)
                burst_sizes.append(min(30, 10 + (v / baseline) * 8))
        
        if burst_x:
            fig.add_trace(go.Scatter(
                x=burst_x,
                y=burst_y,
                mode='markers',
                marker=dict(
                    size=burst_sizes,
                    color='#ef4444',
                    symbol='star',
                    line=dict(width=2, color='white'),
                    opacity=0.9
                ),
                name='⚡ Burst',
                hovertemplate="<b>BURST!</b><br>Velocity: %{y:.1f}/sec<extra></extra>"
            ))
        
        # Current velocity marker (larger, prominent)
        fig.add_trace(go.Scatter(
            x=[len(velocity_history) - 1],
            y=[velocity],
            mode='markers+text',
            marker=dict(
                size=20,
                color=main_color,
                symbol='diamond',
                line=dict(width=3, color='white')
            ),
            text=[f"{velocity:.1f}"],
            textposition="top center",
            textfont=dict(color=main_color, size=14, family="JetBrains Mono"),
            name='Current',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Threshold zones
        max_val = max(velocity_history) * 1.3 if velocity_history else 100
        fig.add_hrect(y0=0, y1=baseline * 1.2, fillcolor="#10b981", opacity=0.08, line_width=0)
        fig.add_hrect(y0=baseline * 1.2, y1=baseline * 1.5, fillcolor="#f59e0b", opacity=0.08, line_width=0)
        fig.add_hrect(y0=baseline * 1.5, y1=max_val, fillcolor="#ef4444", opacity=0.08, line_width=0)
        
        # Layout
        layout = Theme.get_base_layout("", height)
        layout["title"] = dict(
            text=f"<b>Trade Velocity Stream</b> • <span style='color:{main_color}'>{status}</span>",
            font=dict(size=14, color=Theme.TEXT_PRIMARY),
            x=0.5,
            xanchor="center"
        )
        layout["xaxis"]["visible"] = False
        layout["yaxis"]["title"] = dict(text="Trades/sec", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["yaxis"]["range"] = [0, max_val]
        layout["yaxis"]["gridcolor"] = "rgba(255,255,255,0.08)"
        layout["showlegend"] = True
        layout["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font=dict(size=10, color=Theme.TEXT_SECONDARY),
            bgcolor="rgba(0,0,0,0)"
        )
        layout["margin"] = dict(l=60, r=40, t=60, b=50)
        
        # Add stats annotation
        fig.add_annotation(
            x=0.02, y=0.98,
            xref="paper", yref="paper",
            text=f"<b>Current:</b> {velocity:.1f}/sec<br>"
                 f"<b>Ratio:</b> {ratio:.2f}x baseline",
            showarrow=False,
            font=dict(size=11, color=Theme.TEXT_SECONDARY, family="Inter"),
            align="left",
            bgcolor="rgba(20, 25, 35, 0.9)",
            borderpad=8,
            bordercolor=main_color,
            borderwidth=1
        )
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 5: VOLATILITY REGIME RIBBON - UNIQUE SEGMENTED VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_volatility_chart(volatility_data: List[Dict],
                                 height: int = 300,
                                 line_shape: str = "spline") -> go.Figure:
        """
        Create a unique REGIME RIBBON visualization for volatility.
        Shows volatility as color-coded segments with intensity-based ribbon width.
        Each segment represents a volatility regime (Low/Medium/High/Extreme).
        """
        fig = go.Figure()
        
        y_max = 35
        
        if not volatility_data:
            fig.add_annotation(
                text="📉 Calculating volatility...",
                xref="paper", yref="paper",
                x=0.5, y=0.55,
                showarrow=False,
                font=dict(size=18, color="#ec4899", family="Inter")
            )
            fig.add_annotation(
                text="Building regime ribbon...",
                xref="paper", yref="paper",
                x=0.5, y=0.42,
                showarrow=False,
                font=dict(size=12, color=Theme.TEXT_MUTED, family="Inter")
            )
        else:
            timestamps = [d["timestamp"] for d in volatility_data]
            volatilities = [d["volatility_bps"] for d in volatility_data]
            
            max_vol = max(volatilities) if volatilities else 30
            y_max = max(35, max_vol * 1.2)
            
            # Regime classification function
            def get_regime(vol):
                if vol < 10:
                    return ("CALM", "#10b981", 0)
                elif vol < 15:
                    return ("LOW", "#22c55e", 1)
                elif vol < 20:
                    return ("MODERATE", "#f59e0b", 2)
                elif vol < 25:
                    return ("HIGH", "#f97316", 3)
                else:
                    return ("EXTREME", "#ef4444", 4)
            
            # Build regime segments
            segments = []
            current_regime = None
            segment_start = 0
            
            for i, vol in enumerate(volatilities):
                regime_name, color, level = get_regime(vol)
                if regime_name != current_regime:
                    if current_regime is not None:
                        segments.append({
                            'start': segment_start,
                            'end': i,
                            'regime': current_regime,
                            'color': prev_color,
                            'level': prev_level
                        })
                    segment_start = i
                    current_regime = regime_name
                    prev_color = color
                    prev_level = level
            
            # Add last segment
            if current_regime is not None:
                segments.append({
                    'start': segment_start,
                    'end': len(volatilities),
                    'regime': current_regime,
                    'color': prev_color,
                    'level': prev_level
                })
            
            # Create ribbon segments as filled areas
            for seg in segments:
                seg_times = timestamps[seg['start']:seg['end']+1] if seg['end'] < len(timestamps) else timestamps[seg['start']:]
                seg_vols = volatilities[seg['start']:seg['end']+1] if seg['end'] < len(volatilities) else volatilities[seg['start']:]
                
                if len(seg_times) > 0:
                    # Upper ribbon edge
                    upper_y = [v + 2 + seg['level'] for v in seg_vols]
                    # Lower ribbon edge
                    lower_y = [max(0, v - 2 - seg['level']) for v in seg_vols]
                    
                    # Create filled ribbon area
                    fig.add_trace(go.Scatter(
                        x=seg_times + seg_times[::-1],
                        y=upper_y + lower_y[::-1],
                        fill='toself',
                        fillcolor=f"rgba{tuple(list(int(seg['color'][i:i+2], 16) for i in (1, 3, 5)) + [0.4])}",
                        line=dict(width=0),
                        name=seg['regime'],
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                    
                    # Ribbon border (top)
                    fig.add_trace(go.Scatter(
                        x=seg_times,
                        y=upper_y,
                        mode='lines',
                        line=dict(color=seg['color'], width=2),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
            
            # Main volatility line (center of ribbon)
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=volatilities,
                mode='lines+markers',
                name='Volatility',
                line=dict(color='white', width=2, shape='spline'),
                marker=dict(
                    size=6,
                    color=[get_regime(v)[1] for v in volatilities],
                    line=dict(width=1, color='white')
                ),
                hovertemplate="<b>%{x|%H:%M:%S}</b><br>Volatility: %{y:.2f} bps<extra></extra>"
            ))
            
            # Regime threshold lines
            thresholds = [
                (10, "#22c55e", "CALM"),
                (15, "#f59e0b", "LOW"),
                (20, "#f97316", "MODERATE"),
                (25, "#ef4444", "HIGH")
            ]
            
            for thresh, color, label in thresholds:
                fig.add_hline(
                    y=thresh, line_dash="dot", 
                    line_color=color, line_width=1, opacity=0.5
                )
            
            # Current regime indicator
            current_vol = volatilities[-1] if volatilities else 0
            current_regime, current_color, _ = get_regime(current_vol)
            
            # Regime legend at bottom
            regime_colors = {
                "CALM": "#10b981",
                "LOW": "#22c55e", 
                "MODERATE": "#f59e0b",
                "HIGH": "#f97316",
                "EXTREME": "#ef4444"
            }
            
            # Add regime legend boxes
            legend_x = [0.08, 0.26, 0.48, 0.68, 0.88]
            legend_labels = ["CALM", "LOW", "MOD", "HIGH", "EXTREME"]
            
            for i, (label, full_label) in enumerate(zip(legend_labels, ["CALM", "LOW", "MODERATE", "HIGH", "EXTREME"])):
                fig.add_annotation(
                    x=legend_x[i], y=-0.18,
                    xref="paper", yref="paper",
                    text=f"<b>■</b> {label}",
                    showarrow=False,
                    font=dict(color=regime_colors[full_label], size=10, family="Inter"),
                )
            
            # Current value badge
            fig.add_annotation(
                x=1.0, y=1.02,
                xref="paper", yref="paper",
                text=f"<b>🎯 {current_regime}: {current_vol:.1f} bps</b>",
                showarrow=False,
                font=dict(color=current_color, size=13, family="JetBrains Mono"),
                bgcolor="rgba(20, 25, 35, 0.95)",
                borderpad=6,
                bordercolor=current_color,
                borderwidth=2,
                xanchor="right"
            )
            
            # Stats annotation
            avg_vol = np.mean(volatilities)
            fig.add_annotation(
                x=0.0, y=1.02,
                xref="paper", yref="paper",
                text=f"<b>AVG: {avg_vol:.1f}</b> | <b>MAX: {max_vol:.1f}</b>",
                showarrow=False,
                font=dict(color=Theme.TEXT_SECONDARY, size=11, family="JetBrains Mono"),
                xanchor="left"
            )
        
        # Apply layout
        layout = Theme.get_base_layout("Volatility Regime Ribbon", height)
        layout["yaxis"]["title"] = dict(text="Volatility (bps)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["yaxis"]["range"] = [0, y_max]
        layout["yaxis"]["gridcolor"] = "rgba(255,255,255,0.06)"
        layout["xaxis"]["title"] = dict(text="Time", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["xaxis"]["gridcolor"] = "rgba(255,255,255,0.04)"
        layout["showlegend"] = False
        layout["margin"] = dict(l=55, r=40, t=50, b=60)
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # MINI SPARKLINE CHARTS
    # ==========================================================================
    
    @staticmethod
    def create_mini_sparkline(values: List[float], 
                               color: str = None,
                               height: int = 50) -> go.Figure:
        """Create mini sparkline chart for inline metrics."""
        fig = go.Figure()
        
        if values and len(values) > 1:
            trend_color = color or (Theme.GREEN if values[-1] >= values[0] else Theme.RED)
            
            fig.add_trace(go.Scatter(
                y=values,
                mode="lines",
                line=dict(color=trend_color, width=1.5, shape="spline"),
                fill="tozeroy",
                fillcolor=f"rgba({int(trend_color[1:3], 16)}, {int(trend_color[3:5], 16)}, {int(trend_color[5:7], 16)}, 0.2)",
                hoverinfo="skip"
            ))
        
        fig.update_layout(
            height=height,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            showlegend=False
        )
        
        return fig
    
    # ==========================================================================
    # CHART 6: CANDLESTICK CHART (PREMIUM)
    # ==========================================================================
    
    @staticmethod
    def create_candlestick_chart(candle_data: List[Dict],
                                  height: int = 400,
                                  show_volume: bool = True) -> go.Figure:
        """
        Create premium OHLC candlestick chart with volume bars.
        
        Args:
            candle_data: List of dicts with open, high, low, close, volume, timestamp
            height: Chart height in pixels
            show_volume: Whether to show volume subplot
        """
        if show_volume:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.75, 0.25]
            )
        else:
            fig = go.Figure()
        
        if not candle_data:
            fig.add_annotation(
                text="🕯️ Building candlesticks...",
                xref="paper", yref="paper",
                x=0.5, y=0.55,
                showarrow=False,
                font=dict(size=18, color="#fbbf24", family="Inter")
            )
            fig.add_annotation(
                text="Aggregating trade data into OHLC candles",
                xref="paper", yref="paper",
                x=0.5, y=0.42,
                showarrow=False,
                font=dict(size=12, color=Theme.TEXT_MUTED, family="Inter")
            )
        else:
            timestamps = [d["timestamp"] for d in candle_data]
            opens = [d["open"] for d in candle_data]
            highs = [d["high"] for d in candle_data]
            lows = [d["low"] for d in candle_data]
            closes = [d["close"] for d in candle_data]
            volumes = [d.get("volume", 0) for d in candle_data]
            
            # Determine colors for each candle
            colors = ["#10b981" if c >= o else "#ef4444" 
                      for o, c in zip(opens, closes)]
            
            # Candlestick trace
            candlestick = go.Candlestick(
                x=timestamps,
                open=opens,
                high=highs,
                low=lows,
                close=closes,
                increasing=dict(
                    line=dict(color="#10b981", width=1),
                    fillcolor="#10b981"
                ),
                decreasing=dict(
                    line=dict(color="#ef4444", width=1),
                    fillcolor="#ef4444"
                ),
                name="OHLC",
                hoverinfo="all"
            )
            
            if show_volume:
                fig.add_trace(candlestick, row=1, col=1)
                
                # Volume bars
                fig.add_trace(go.Bar(
                    x=timestamps,
                    y=volumes,
                    marker=dict(
                        color=colors,
                        opacity=0.6,
                        line=dict(width=0)
                    ),
                    name="Volume",
                    hovertemplate="<b>Volume</b>: %{y:.4f} BTC<extra></extra>"
                ), row=2, col=1)
            else:
                fig.add_trace(candlestick)
            
            # Add moving averages
            if len(closes) >= 10:
                ma10 = [np.mean(closes[max(0, i-9):i+1]) for i in range(len(closes))]
                fig.add_trace(go.Scatter(
                    x=timestamps,
                    y=ma10,
                    mode="lines",
                    name="MA(10)",
                    line=dict(color="#8b5cf6", width=1.5, dash="dot"),
                    hovertemplate="<b>MA(10)</b>: $%{y:,.2f}<extra></extra>"
                ), row=1, col=1) if show_volume else fig.add_trace(go.Scatter(
                    x=timestamps,
                    y=ma10,
                    mode="lines",
                    name="MA(10)",
                    line=dict(color="#8b5cf6", width=1.5, dash="dot"),
                    hovertemplate="<b>MA(10)</b>: $%{y:,.2f}<extra></extra>"
                ))
            
            # Current price annotation
            if closes:
                last_price = closes[-1]
                last_open = opens[-1]
                change_pct = (last_price - last_open) / last_open * 100 if last_open else 0
                arrow_color = "#10b981" if change_pct >= 0 else "#ef4444"
                
                fig.add_annotation(
                    x=timestamps[-1],
                    y=last_price,
                    text=f"${last_price:,.2f}",
                    showarrow=True,
                    arrowhead=0,
                    arrowcolor=arrow_color,
                    ax=50,
                    ay=0,
                    font=dict(color=arrow_color, size=11, family="JetBrains Mono"),
                    bgcolor="rgba(20, 25, 35, 0.95)",
                    borderpad=4,
                    bordercolor=arrow_color
                )
        
        # Layout
        layout = Theme.get_base_layout("Live Candlestick Chart (5s candles)", height)
        layout["xaxis"]["title"] = dict(text="Time", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["xaxis"]["rangeslider"] = dict(visible=False)
        layout["yaxis"]["title"] = dict(text="Price (USD)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["yaxis"]["tickprefix"] = "$"
        layout["yaxis"]["tickformat"] = ",.0f"
        layout["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=Theme.TEXT_SECONDARY, size=10, family="Inter"),
            bgcolor="rgba(0,0,0,0)"
        )
        
        if show_volume:
            layout["yaxis2"] = dict(
                title=dict(text="Vol", font=dict(size=10, color=Theme.TEXT_MUTED)),
                tickfont=dict(size=9, color=Theme.TEXT_SECONDARY),
                gridcolor="rgba(255,255,255,0.05)",
                showgrid=True
            )
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 7: ORDER BOOK DEPTH CHART (PREMIUM)
    # ==========================================================================
    
    @staticmethod
    def create_depth_chart(bids: List[Dict], asks: List[Dict],
                           height: int = 350) -> go.Figure:
        """
        Create premium order book depth visualization.
        Shows cumulative bid/ask volume at each price level.
        
        Args:
            bids: List of dicts with price, quantity (sorted high to low)
            asks: List of dicts with price, quantity (sorted low to high)
            height: Chart height in pixels
        """
        fig = go.Figure()
        
        if not bids and not asks:
            fig.add_annotation(
                text="📊 Loading order book depth...",
                xref="paper", yref="paper",
                x=0.5, y=0.55,
                showarrow=False,
                font=dict(size=18, color="#06b6d4", family="Inter")
            )
            fig.add_annotation(
                text="Awaiting order book data",
                xref="paper", yref="paper",
                x=0.5, y=0.42,
                showarrow=False,
                font=dict(size=12, color=Theme.TEXT_MUTED, family="Inter")
            )
        else:
            # Calculate cumulative volumes
            bid_prices = [b["price"] for b in bids]
            bid_volumes = [b["quantity"] for b in bids]
            cumulative_bid = np.cumsum(bid_volumes).tolist()
            
            ask_prices = [a["price"] for a in asks]
            ask_volumes = [a["quantity"] for a in asks]
            cumulative_ask = np.cumsum(ask_volumes).tolist()
            
            # Get mid price for center line
            mid_price = (bid_prices[0] + ask_prices[0]) / 2 if bid_prices and ask_prices else 0
            
            # Bid depth (green area)
            fig.add_trace(go.Scatter(
                x=bid_prices,
                y=cumulative_bid,
                mode="lines",
                name="🟢 Bids",
                line=dict(color="#10b981", width=2),
                fill="tozeroy",
                fillcolor="rgba(16, 185, 129, 0.3)",
                hovertemplate="<b>Bid Price</b>: $%{x:,.2f}<br><b>Cumulative</b>: %{y:.4f} BTC<extra></extra>"
            ))
            
            # Ask depth (red area)
            fig.add_trace(go.Scatter(
                x=ask_prices,
                y=cumulative_ask,
                mode="lines",
                name="🔴 Asks",
                line=dict(color="#ef4444", width=2),
                fill="tozeroy",
                fillcolor="rgba(239, 68, 68, 0.3)",
                hovertemplate="<b>Ask Price</b>: $%{x:,.2f}<br><b>Cumulative</b>: %{y:.4f} BTC<extra></extra>"
            ))
            
            # Mid price line
            if mid_price:
                fig.add_vline(
                    x=mid_price,
                    line_dash="dash",
                    line_color="#fbbf24",
                    line_width=2,
                    annotation_text=f"Mid: ${mid_price:,.2f}",
                    annotation_position="top",
                    annotation_font=dict(color="#fbbf24", size=11, family="JetBrains Mono")
                )
            
            # Wall detection (large cumulative jumps)
            max_bid_vol = max(cumulative_bid) if cumulative_bid else 0
            max_ask_vol = max(cumulative_ask) if cumulative_ask else 0
            
            # Annotate significant walls
            for i, (price, vol) in enumerate(zip(bid_prices, bid_volumes)):
                if vol > max_bid_vol * 0.3:  # Large single order
                    fig.add_annotation(
                        x=price,
                        y=cumulative_bid[i],
                        text=f"🛡️ Wall",
                        showarrow=True,
                        arrowhead=2,
                        arrowcolor="#10b981",
                        ax=-30,
                        ay=-20,
                        font=dict(color="#10b981", size=9, family="Inter"),
                        bgcolor="rgba(20, 25, 35, 0.9)",
                        borderpad=3
                    )
                    break  # Only show first wall
            
            for i, (price, vol) in enumerate(zip(ask_prices, ask_volumes)):
                if vol > max_ask_vol * 0.3:
                    fig.add_annotation(
                        x=price,
                        y=cumulative_ask[i],
                        text=f"🧱 Wall",
                        showarrow=True,
                        arrowhead=2,
                        arrowcolor="#ef4444",
                        ax=30,
                        ay=-20,
                        font=dict(color="#ef4444", size=9, family="Inter"),
                        bgcolor="rgba(20, 25, 35, 0.9)",
                        borderpad=3
                    )
                    break
        
        # Layout
        layout = Theme.get_base_layout("Order Book Depth", height)
        layout["xaxis"]["title"] = dict(text="Price (USD)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["xaxis"]["tickprefix"] = "$"
        layout["xaxis"]["tickformat"] = ",.0f"
        layout["yaxis"]["title"] = dict(text="Cumulative Volume (BTC)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(color=Theme.TEXT_SECONDARY, size=11, family="Inter"),
            bgcolor="rgba(0,0,0,0)"
        )
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 8: ML PREDICTION RADAR DIAL - UNIQUE VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_prediction_gauge(direction: str, confidence: float,
                                 momentum: float, height: int = 200) -> go.Figure:
        """
        Create a unique RADAR DIAL visualization for ML predictions.
        Shows direction as a compass-like dial with confidence as radius.
        """
        fig = go.Figure()
        
        # Determine colors and direction angle
        if "up" in direction.lower():
            main_color = "#10b981"
            direction_text = "📈 BULLISH"
            direction_angle = 90  # North = Up
            bg_gradient = "rgba(16, 185, 129, 0.15)"
        elif "down" in direction.lower():
            main_color = "#ef4444"
            direction_text = "📉 BEARISH"
            direction_angle = 270  # South = Down
            bg_gradient = "rgba(239, 68, 68, 0.15)"
        else:
            main_color = "#f59e0b"
            direction_text = "➡️ NEUTRAL"
            direction_angle = 0  # East = Neutral
            bg_gradient = "rgba(245, 158, 11, 0.15)"
        
        # Add momentum influence to angle (subtle tilt)
        momentum_tilt = momentum * 0.2  # Small tilt based on momentum
        final_angle = direction_angle + momentum_tilt
        
        # Create polar background zones for confidence levels
        confidence_zones = [
            (40, "LOW", "rgba(239, 68, 68, 0.1)"),
            (60, "MED", "rgba(245, 158, 11, 0.1)"),
            (80, "HIGH", "rgba(34, 197, 94, 0.1)"),
            (100, "STRONG", "rgba(16, 185, 129, 0.15)")
        ]
        
        # Background reference circles
        for radius, label, color in confidence_zones:
            theta = list(range(0, 361, 10))
            r = [radius] * len(theta)
            fig.add_trace(go.Scatterpolar(
                r=r,
                theta=theta,
                mode='lines',
                line=dict(color='rgba(255,255,255,0.1)', width=1),
                fill='toself' if radius == 40 else None,
                fillcolor=color if radius == 40 else None,
                showlegend=False,
                hoverinfo='skip'
            ))
        
        # Direction needle (main indicator)
        needle_angles = [final_angle - 8, final_angle, final_angle + 8]
        needle_r = [0, confidence, 0]
        
        fig.add_trace(go.Scatterpolar(
            r=needle_r,
            theta=needle_angles,
            mode='lines',
            fill='toself',
            fillcolor=main_color,
            line=dict(color=main_color, width=3),
            name='Direction',
            showlegend=False,
            hovertemplate=f"<b>{direction_text}</b><br>Confidence: {confidence:.1f}%<extra></extra>"
        ))
        
        # Needle tip marker
        fig.add_trace(go.Scatterpolar(
            r=[confidence],
            theta=[final_angle],
            mode='markers',
            marker=dict(
                size=18,
                color=main_color,
                symbol='triangle-up',
                line=dict(width=2, color='white')
            ),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Center dot
        fig.add_trace(go.Scatterpolar(
            r=[0],
            theta=[0],
            mode='markers',
            marker=dict(size=15, color='#1e293b', line=dict(width=3, color=main_color)),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Cardinal direction markers (N/S for Bull/Bear)
        cardinal_markers = [
            (90, "🐂", "#10b981"),   # North = Bullish
            (270, "🐻", "#ef4444"), # South = Bearish
            (0, "↔", "#f59e0b"),    # East = Neutral
            (180, "↔", "#f59e0b"),  # West = Neutral
        ]
        
        for angle, symbol, color in cardinal_markers:
            fig.add_trace(go.Scatterpolar(
                r=[108],
                theta=[angle],
                mode='text',
                text=[symbol],
                textfont=dict(size=18),
                showlegend=False,
                hoverinfo='skip'
            ))
        
        # Confidence level annotations
        for radius, label, _ in confidence_zones:
            fig.add_annotation(
                x=0.5 + (radius/200) * 0.4,
                y=0.5,
                xref="paper", yref="paper",
                text=f"<b>{label}</b>",
                showarrow=False,
                font=dict(color='rgba(255,255,255,0.3)', size=8),
            )
        
        # Layout
        layout = {
            "polar": {
                "bgcolor": "rgba(20, 25, 35, 0.95)",
                "radialaxis": {
                    "visible": True,
                    "range": [0, 110],
                    "tickfont": {"size": 9, "color": "rgba(255,255,255,0.4)"},
                    "tickvals": [40, 60, 80, 100],
                    "gridcolor": "rgba(255,255,255,0.08)",
                    "linecolor": "rgba(255,255,255,0.1)",
                },
                "angularaxis": {
                    "visible": True,
                    "direction": "clockwise",
                    "rotation": 90,
                    "tickfont": {"size": 10, "color": "rgba(255,255,255,0.5)"},
                    "gridcolor": "rgba(255,255,255,0.08)",
                    "linecolor": "rgba(255,255,255,0.1)",
                    "tickvals": [0, 90, 180, 270],
                    "ticktext": ["→", "▲", "←", "▼"]
                }
            },
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "showlegend": False,
            "height": height,
            "margin": dict(l=40, r=40, t=55, b=35),
            "title": dict(
                text=f"<b>ML Prediction Dial</b> • <span style='color:{main_color}'>{direction_text}</span>",
                font=dict(size=13, color=Theme.TEXT_PRIMARY, family="Inter"),
                x=0.5,
                xanchor="center"
            ),
            "annotations": [
                dict(
                    x=0.5, y=-0.05,
                    xref="paper", yref="paper",
                    text=f"<b style='color:{main_color};font-size:20px'>{confidence:.0f}%</b> <span style='color:#94a3b8;font-size:11px'>confidence</span>",
                    showarrow=False,
                    font=dict(family="JetBrains Mono"),
                )
            ]
        }
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 9: MOMENTUM OSCILLOSCOPE - UNIQUE WAVE VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_momentum_bar(momentum: float, height: int = 120) -> go.Figure:
        """
        Create a unique OSCILLOSCOPE style momentum visualization.
        Shows momentum as a sine-wave pattern with amplitude = momentum strength.
        """
        fig = go.Figure()
        
        # Clamp momentum
        momentum = max(-100, min(100, momentum))
        abs_momentum = abs(momentum)
        
        # Determine color based on direction and strength
        if momentum > 30:
            wave_color = "#10b981"
            status = "STRONG BULLISH"
        elif momentum > 10:
            wave_color = "#22c55e"
            status = "Bullish"
        elif momentum < -30:
            wave_color = "#ef4444"
            status = "STRONG BEARISH"
        elif momentum < -10:
            wave_color = "#f97316"
            status = "Bearish"
        else:
            wave_color = "#64748b"
            status = "Neutral"
        
        # Generate oscilloscope wave
        x_points = np.linspace(0, 4 * np.pi, 100)
        
        # Wave amplitude based on momentum strength
        amplitude = abs_momentum / 100 * 50
        
        # Wave shape - positive momentum = peaks up, negative = peaks down
        if momentum >= 0:
            y_points = amplitude * np.sin(x_points)
        else:
            y_points = -amplitude * np.sin(x_points)
        
        # Add slight randomness to simulate real-time signal
        noise = np.random.normal(0, amplitude * 0.05, len(x_points))
        y_points = y_points + noise
        
        # Background grid lines
        for y_val in [-50, -25, 0, 25, 50]:
            fig.add_hline(y=y_val, line_color="rgba(255,255,255,0.08)", line_width=1)
        
        # Zero line (stronger)
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=2)
        
        # Zone backgrounds
        fig.add_hrect(y0=25, y1=55, fillcolor="#10b981", opacity=0.1, line_width=0)
        fig.add_hrect(y0=-55, y1=-25, fillcolor="#ef4444", opacity=0.1, line_width=0)
        
        # Main wave with glow effect (shadow layer)
        fig.add_trace(go.Scatter(
            x=x_points,
            y=y_points,
            mode='lines',
            line=dict(color=wave_color, width=8),
            opacity=0.3,
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Main wave (crisp line)
        fig.add_trace(go.Scatter(
            x=x_points,
            y=y_points,
            mode='lines',
            line=dict(color=wave_color, width=3, shape='spline'),
            name='Momentum Wave',
            showlegend=False,
            hovertemplate=f"<b>Momentum</b>: {momentum:+.1f}<extra></extra>"
        ))
        
        # Current position marker (end of wave)
        fig.add_trace(go.Scatter(
            x=[x_points[-1]],
            y=[y_points[-1]],
            mode='markers',
            marker=dict(
                size=12,
                color=wave_color,
                symbol='circle',
                line=dict(width=2, color='white')
            ),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Amplitude bars on sides
        fig.add_trace(go.Scatter(
            x=[0.3, 0.3],
            y=[0, momentum / 100 * 50],
            mode='lines',
            line=dict(color=wave_color, width=6),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Layout
        layout = Theme.get_base_layout("", height)
        layout["xaxis"]["visible"] = False
        layout["xaxis"]["range"] = [-0.5, 4 * np.pi + 0.5]
        layout["yaxis"]["range"] = [-55, 55]
        layout["yaxis"]["visible"] = False
        layout["showlegend"] = False
        layout["margin"] = dict(l=15, r=15, t=40, b=20)
        
        # Annotations
        layout["annotations"] = [
            dict(
                x=0.5, y=1.1, xref="paper", yref="paper",
                text=f"<b style='color:{wave_color};font-size:22px'>{momentum:+.0f}</b> <span style='color:#94a3b8;font-size:12px'>• {status}</span>",
                showarrow=False,
                font=dict(family="JetBrains Mono"),
            ),
            dict(
                x=0.02, y=0.85, xref="paper", yref="paper",
                text="🟢 BULL",
                showarrow=False,
                font=dict(color="#10b981", size=9),
            ),
            dict(
                x=0.02, y=0.15, xref="paper", yref="paper",
                text="🔴 BEAR",
                showarrow=False,
                font=dict(color="#ef4444", size=9),
            ),
        ]
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 10: REGIME HEARTBEAT MONITOR - UNIQUE VISUALIZATION
    # ==========================================================================
    
    @staticmethod
    def create_regime_indicator(regime: str, confidence: float,
                                 height: int = 150) -> go.Figure:
        """
        Create a unique HEARTBEAT MONITOR style regime visualization.
        Shows regime as an EKG/heartbeat pattern with pulse intensity = confidence.
        """
        fig = go.Figure()
        
        # Regime styling with heartbeat patterns
        regime_styles = {
            "trending_up": ("📈 TRENDING UP", "#10b981", "Bullish momentum", 1.0),
            "trending_down": ("📉 TRENDING DOWN", "#ef4444", "Bearish momentum", 1.0),
            "ranging": ("↔️ RANGING", "#64748b", "Consolidation", 0.4),
            "volatile": ("⚡ VOLATILE", "#f59e0b", "High volatility", 1.5),
            "breakout": ("🚀 BREAKOUT", "#8b5cf6", "Breakout forming", 1.8)
        }
        
        regime_key = regime.lower().replace(" ", "_") if regime else "ranging"
        title, color, description, intensity = regime_styles.get(
            regime_key, ("❓ UNKNOWN", "#6b7280", "Analyzing...", 0.5)
        )
        
        # Generate heartbeat pattern
        # Base flatline
        x_base = np.linspace(0, 10, 200)
        y_base = np.zeros(200)
        
        # Create heartbeat pulse shape based on regime
        pulse_amplitude = (confidence / 100) * intensity * 50
        
        def heartbeat_shape(x, center, amplitude, width=0.3):
            """Generate a heartbeat pulse shape."""
            result = np.zeros_like(x)
            # P wave (small bump)
            mask = (x > center - width*2) & (x < center - width)
            result[mask] = amplitude * 0.15 * np.sin((x[mask] - (center - width*1.5)) * np.pi / (width))
            # QRS complex (main spike)
            mask = (x > center - width*0.3) & (x < center + width*0.3)
            result[mask] = amplitude * np.sin((x[mask] - center) * np.pi / (width*0.6))
            # Small dip
            mask = (x > center + width*0.3) & (x < center + width*0.8)
            result[mask] = -amplitude * 0.2 * np.sin((x[mask] - (center + width*0.55)) * np.pi / (width*0.5))
            # T wave (recovery bump)
            mask = (x > center + width) & (x < center + width*2)
            result[mask] = amplitude * 0.3 * np.sin((x[mask] - (center + width*1.5)) * np.pi / (width))
            return result
        
        # Add heartbeat pulses
        pulse_positions = [2, 5, 8]
        y_heartbeat = y_base.copy()
        
        for pos in pulse_positions:
            y_heartbeat += heartbeat_shape(x_base, pos, pulse_amplitude, width=0.4)
        
        # Add subtle noise for realism
        noise = np.random.normal(0, pulse_amplitude * 0.02, len(x_base))
        y_heartbeat += noise
        
        # Background grid
        for y_val in [-40, -20, 0, 20, 40]:
            fig.add_hline(y=y_val, line_color="rgba(255,255,255,0.08)", line_width=1)
        
        # Glow effect layer
        fig.add_trace(go.Scatter(
            x=x_base,
            y=y_heartbeat,
            mode='lines',
            line=dict(color=color, width=8),
            opacity=0.3,
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Main heartbeat line
        fig.add_trace(go.Scatter(
            x=x_base,
            y=y_heartbeat,
            mode='lines',
            line=dict(color=color, width=2, shape='spline'),
            name='Regime Pulse',
            showlegend=False,
            hovertemplate=f"<b>{title}</b><br>Confidence: {confidence:.0f}%<extra></extra>"
        ))
        
        # Current position marker (pulsing dot at end)
        fig.add_trace(go.Scatter(
            x=[x_base[-1]],
            y=[y_heartbeat[-1]],
            mode='markers',
            marker=dict(
                size=10,
                color=color,
                symbol='circle',
                line=dict(width=2, color='white')
            ),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Regime badge on left
        fig.add_trace(go.Scatter(
            x=[0.5],
            y=[0],
            mode='markers+text',
            marker=dict(size=35, color=color, opacity=0.3, symbol='circle'),
            text=[title.split()[0]],  # Just the emoji
            textfont=dict(size=18),
            textposition='middle center',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Layout
        layout = Theme.get_base_layout("", height)
        layout["xaxis"]["visible"] = False
        layout["xaxis"]["range"] = [-0.5, 10.5]
        layout["yaxis"]["range"] = [-60, 60]
        layout["yaxis"]["visible"] = False
        layout["showlegend"] = False
        layout["margin"] = dict(l=10, r=10, t=45, b=35)
        
        # Annotations
        layout["annotations"] = [
            dict(
                x=0.5, y=1.1, xref="paper", yref="paper",
                text=f"<b style='color:{color}'>{title}</b> <span style='color:#94a3b8'>• {description}</span>",
                showarrow=False,
                font=dict(size=12, family="Inter"),
            ),
            dict(
                x=0.5, y=-0.12, xref="paper", yref="paper",
                text=f"<b style='color:{color};font-size:18px'>{confidence:.0f}%</b> <span style='color:#64748b;font-size:10px'>confidence</span>",
                showarrow=False,
                font=dict(family="JetBrains Mono"),
            ),
        ]
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 11: BACKTEST EQUITY CURVE (PREMIUM)
    # ==========================================================================
    
    @staticmethod
    def create_equity_curve(equity_data: List[tuple],
                            initial_capital: float = 10000,
                            height: int = 350) -> go.Figure:
        """
        Create backtest equity curve visualization.
        
        Args:
            equity_data: List of (timestamp, equity) tuples
            initial_capital: Starting capital for baseline
            height: Chart height
        """
        fig = go.Figure()
        
        if not equity_data:
            fig.add_annotation(
                text="📊 No backtest data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=16, color=Theme.TEXT_MUTED, family="Inter")
            )
        else:
            timestamps = [d[0] for d in equity_data]
            equity = [d[1] for d in equity_data]
            
            # Determine overall color
            final_equity = equity[-1] if equity else initial_capital
            is_profitable = final_equity >= initial_capital
            main_color = "#10b981" if is_profitable else "#ef4444"
            
            # Equity curve
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=equity,
                mode="lines",
                name="Equity",
                line=dict(color=main_color, width=2.5),
                fill="tozeroy",
                fillcolor=f"rgba({16 if is_profitable else 239}, {185 if is_profitable else 68}, {129 if is_profitable else 68}, 0.2)",
                hovertemplate="<b>Equity</b>: $%{y:,.2f}<extra></extra>"
            ))
            
            # Initial capital baseline
            fig.add_hline(
                y=initial_capital,
                line_dash="dash",
                line_color="#6b7280",
                line_width=1,
                annotation_text=f"Initial: ${initial_capital:,.0f}",
                annotation_position="right",
                annotation_font=dict(color="#6b7280", size=10)
            )
            
            # High water mark
            hwm = max(equity)
            fig.add_hline(
                y=hwm,
                line_dash="dot",
                line_color="#fbbf24",
                line_width=1,
                annotation_text=f"Peak: ${hwm:,.0f}",
                annotation_position="right",
                annotation_font=dict(color="#fbbf24", size=10)
            )
            
            # Final equity annotation
            pnl = final_equity - initial_capital
            pnl_pct = pnl / initial_capital * 100
            
            fig.add_annotation(
                x=timestamps[-1],
                y=final_equity,
                text=f"${final_equity:,.0f}<br><span style='color:{main_color}'>{pnl_pct:+.2f}%</span>",
                showarrow=True,
                arrowhead=0,
                arrowcolor=main_color,
                ax=50,
                ay=-30,
                font=dict(color=main_color, size=12, family="JetBrains Mono"),
                bgcolor="rgba(20, 25, 35, 0.95)",
                borderpad=5,
                bordercolor=main_color
            )
        
        layout = Theme.get_base_layout("Backtest Equity Curve", height)
        layout["yaxis"]["title"] = dict(text="Equity (USD)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["yaxis"]["tickprefix"] = "$"
        layout["yaxis"]["tickformat"] = ",.0f"
        layout["xaxis"]["title"] = dict(text="Time", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["showlegend"] = False
        
        fig.update_layout(**layout)
        return fig
    
    # ==========================================================================
    # CHART 12: TRADE DISTRIBUTION (PREMIUM)
    # ==========================================================================
    
    @staticmethod
    def create_trade_distribution(trades: List,
                                   height: int = 300) -> go.Figure:
        """
        Create trade P&L distribution histogram.
        
        Args:
            trades: List of Trade objects, dicts with pnl_pct, or raw P&L values
            height: Chart height
        """
        fig = go.Figure()
        
        if not trades:
            fig.add_annotation(
                text="📊 No trades to analyze",
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=16, color=Theme.TEXT_MUTED, family="Inter")
            )
        else:
            # Handle different input formats
            pnls = []
            for t in trades:
                if isinstance(t, (int, float)):
                    # Raw numeric value
                    pnls.append(float(t))
                elif hasattr(t, 'pnl_pct'):
                    # Trade object with pnl_pct attribute
                    pnls.append(t.pnl_pct)
                elif isinstance(t, dict):
                    # Dictionary with pnl_pct key
                    pnls.append(t.get("pnl_pct", 0))
                else:
                    pnls.append(0)
            
            # Split wins and losses
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            
            # Wins histogram
            if wins:
                fig.add_trace(go.Histogram(
                    x=wins,
                    name="Wins",
                    marker=dict(color="#10b981", opacity=0.8),
                    nbinsx=15
                ))
            
            # Losses histogram
            if losses:
                fig.add_trace(go.Histogram(
                    x=losses,
                    name="Losses",
                    marker=dict(color="#ef4444", opacity=0.8),
                    nbinsx=15
                ))
            
            # Zero line
            fig.add_vline(x=0, line_color="white", line_width=2)
            
            # Stats annotation
            avg_win = np.mean(wins) if wins else 0
            avg_loss = np.mean(losses) if losses else 0
            win_rate = len(wins) / len(pnls) * 100 if pnls else 0
            
            fig.add_annotation(
                text=f"Win Rate: {win_rate:.1f}% | Avg Win: {avg_win:+.2f}% | Avg Loss: {avg_loss:.2f}%",
                x=0.5, y=1.08,
                xref="paper", yref="paper",
                showarrow=False,
                font=dict(size=11, color=Theme.TEXT_SECONDARY, family="Inter"),
                bgcolor="rgba(20, 25, 35, 0.8)",
                borderpad=5
            )
        
        layout = Theme.get_base_layout("Trade P&L Distribution", height)
        layout["xaxis"]["title"] = dict(text="P&L (%)", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["yaxis"]["title"] = dict(text="Count", font=dict(size=11, color=Theme.TEXT_MUTED))
        layout["barmode"] = "overlay"
        layout["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=Theme.TEXT_SECONDARY, size=10),
            bgcolor="rgba(0,0,0,0)"
        )
        
        fig.update_layout(**layout)
        return fig

    # =========================================================================
    # CONFUSION MATRIX CHART
    # =========================================================================
    
    @staticmethod
    def create_confusion_matrix(
        y_true: List[int],
        y_pred: List[int],
        labels: List[str] = None,
        height: int = 400
    ) -> go.Figure:
        """
        Create a professional confusion matrix heatmap.
        
        Args:
            y_true: True labels (0=UP, 1=HOLD, 2=DOWN)
            y_pred: Predicted labels
            labels: Class names (default: ["UP", "HOLD", "DOWN"])
            height: Chart height in pixels
            
        Returns:
            Plotly figure with confusion matrix
        """
        if labels is None:
            labels = ["UP", "HOLD", "DOWN"]
        
        n_classes = len(labels)
        
        # Compute confusion matrix
        cm = np.zeros((n_classes, n_classes), dtype=int)
        for true, pred in zip(y_true, y_pred):
            if 0 <= true < n_classes and 0 <= pred < n_classes:
                cm[true][pred] += 1
        
        # Compute percentages
        row_sums = cm.sum(axis=1, keepdims=True)
        cm_pct = np.divide(cm, row_sums, where=row_sums != 0) * 100
        
        # Create text annotations with count and percentage
        annotations = []
        text_matrix = []
        for i in range(n_classes):
            text_row = []
            for j in range(n_classes):
                count = cm[i][j]
                pct = cm_pct[i][j]
                text_row.append(f"{count}<br>({pct:.1f}%)")
            text_matrix.append(text_row)
        
        # Color scale - green for diagonal (correct), red for off-diagonal (errors)
        # Create custom colorscale
        fig = go.Figure()
        
        # Add heatmap
        fig.add_trace(go.Heatmap(
            z=cm,
            x=labels,
            y=labels,
            text=text_matrix,
            texttemplate="%{text}",
            textfont=dict(size=14, color="white", family="JetBrains Mono"),
            colorscale=[
                [0, "rgba(30, 41, 59, 0.9)"],
                [0.25, "rgba(59, 130, 246, 0.5)"],
                [0.5, "rgba(139, 92, 246, 0.7)"],
                [0.75, "rgba(16, 185, 129, 0.8)"],
                [1, "rgba(16, 185, 129, 1)"]
            ],
            showscale=True,
            colorbar=dict(
                title=dict(text="Count", font=dict(color=Theme.TEXT_SECONDARY, size=11)),
                tickfont=dict(color=Theme.TEXT_MUTED, size=10),
                bgcolor="rgba(0,0,0,0)"
            ),
            hovertemplate="True: %{y}<br>Predicted: %{x}<br>Count: %{z}<extra></extra>"
        ))
        
        # Calculate metrics
        total = cm.sum()
        correct = np.trace(cm)
        accuracy = correct / total * 100 if total > 0 else 0
        
        # Per-class metrics
        precisions = []
        recalls = []
        for i in range(n_classes):
            tp = cm[i][i]
            fp = cm[:, i].sum() - tp
            fn = cm[i, :].sum() - tp
            precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
            precisions.append(precision)
            recalls.append(recall)
        
        avg_precision = np.mean(precisions)
        avg_recall = np.mean(recalls)
        f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0
        
        # Add metrics annotation
        metrics_text = f"Accuracy: {accuracy:.1f}% | Precision: {avg_precision:.1f}% | Recall: {avg_recall:.1f}% | F1: {f1:.1f}%"
        fig.add_annotation(
            text=metrics_text,
            x=0.5, y=1.12,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=11, color=Theme.TEXT_SECONDARY, family="Inter"),
            bgcolor="rgba(20, 25, 35, 0.9)",
            bordercolor="rgba(139, 92, 246, 0.3)",
            borderwidth=1,
            borderpad=6
        )
        
        layout = Theme.get_base_layout("Prediction Confusion Matrix", height)
        layout["xaxis"]["title"] = dict(text="Predicted", font=dict(size=12, color=Theme.TEXT_SECONDARY))
        layout["yaxis"]["title"] = dict(text="Actual", font=dict(size=12, color=Theme.TEXT_SECONDARY))
        layout["xaxis"]["tickfont"] = dict(size=12, color=Theme.TEXT_PRIMARY)
        layout["yaxis"]["tickfont"] = dict(size=12, color=Theme.TEXT_PRIMARY)
        layout["yaxis"]["autorange"] = "reversed"
        
        fig.update_layout(**layout)
        return fig
    
    # =========================================================================
    # ROC CURVE CHART (Multi-class One-vs-Rest)
    # =========================================================================
    
    @staticmethod
    def create_roc_curve(
        y_true: List[int],
        y_probs: List[List[float]],
        labels: List[str] = None,
        height: int = 400
    ) -> go.Figure:
        """
        Create multi-class ROC curves (One-vs-Rest).
        
        Args:
            y_true: True labels (0=UP, 1=HOLD, 2=DOWN)
            y_probs: Predicted probabilities for each class [[p_up, p_hold, p_down], ...]
            labels: Class names (default: ["UP", "HOLD", "DOWN"])
            height: Chart height in pixels
            
        Returns:
            Plotly figure with ROC curves
        """
        if labels is None:
            labels = ["UP", "HOLD", "DOWN"]
        
        n_classes = len(labels)
        colors = ["#10b981", "#f59e0b", "#ef4444"]  # Green, Amber, Red for UP, HOLD, DOWN
        
        fig = go.Figure()
        
        # Convert to numpy arrays
        y_true = np.array(y_true)
        y_probs = np.array(y_probs)
        
        aucs = []
        
        # Calculate ROC curve for each class (One-vs-Rest)
        for i in range(n_classes):
            # Binary labels for this class
            y_binary = (y_true == i).astype(int)
            
            if len(y_probs.shape) == 2 and y_probs.shape[1] > i:
                y_score = y_probs[:, i]
            else:
                # Fallback if probs not available
                y_score = (y_true == i).astype(float)
            
            # Calculate ROC curve points
            thresholds = np.linspace(0, 1, 100)
            tpr_list = []
            fpr_list = []
            
            for thresh in thresholds:
                y_pred_binary = (y_score >= thresh).astype(int)
                
                tp = np.sum((y_pred_binary == 1) & (y_binary == 1))
                fp = np.sum((y_pred_binary == 1) & (y_binary == 0))
                tn = np.sum((y_pred_binary == 0) & (y_binary == 0))
                fn = np.sum((y_pred_binary == 0) & (y_binary == 1))
                
                tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
                fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
                
                tpr_list.append(tpr)
                fpr_list.append(fpr)
            
            # Sort by FPR for proper curve
            sorted_indices = np.argsort(fpr_list)
            fpr_sorted = np.array(fpr_list)[sorted_indices]
            tpr_sorted = np.array(tpr_list)[sorted_indices]
            
            # Calculate AUC using trapezoidal rule
            auc = np.trapezoid(tpr_sorted, fpr_sorted)
            auc = min(max(auc, 0), 1)  # Clamp between 0 and 1
            aucs.append(auc)
            
            # Add ROC curve
            fig.add_trace(go.Scatter(
                x=fpr_sorted,
                y=tpr_sorted,
                mode="lines",
                name=f"{labels[i]} (AUC={auc:.3f})",
                line=dict(color=colors[i], width=2.5),
                fill="tozeroy",
                fillcolor=f"rgba{tuple(list(int(colors[i].lstrip('#')[j:j+2], 16) for j in (0, 2, 4)) + [0.1])}",
                hovertemplate=f"<b>{labels[i]}</b><br>FPR: %{{x:.3f}}<br>TPR: %{{y:.3f}}<extra></extra>"
            ))
        
        # Add diagonal reference line (random classifier)
        fig.add_trace(go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            name="Random (AUC=0.500)",
            line=dict(color="#6b7280", width=1.5, dash="dash"),
            hoverinfo="skip"
        ))
        
        # Add macro-average AUC annotation
        macro_auc = np.mean(aucs)
        fig.add_annotation(
            text=f"Macro-Avg AUC: {macro_auc:.3f}",
            x=0.95, y=0.05,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=13, color="#a78bfa", family="JetBrains Mono"),
            bgcolor="rgba(20, 25, 35, 0.95)",
            bordercolor="rgba(139, 92, 246, 0.5)",
            borderwidth=1,
            borderpad=8
        )
        
        layout = Theme.get_base_layout("ROC Curves (One-vs-Rest)", height)
        layout["xaxis"]["title"] = dict(text="False Positive Rate", font=dict(size=11, color=Theme.TEXT_SECONDARY))
        layout["yaxis"]["title"] = dict(text="True Positive Rate", font=dict(size=11, color=Theme.TEXT_SECONDARY))
        layout["xaxis"]["range"] = [-0.02, 1.02]
        layout["yaxis"]["range"] = [-0.02, 1.02]
        layout["legend"] = dict(
            orientation="v",
            yanchor="bottom",
            y=0.02,
            xanchor="right",
            x=0.98,
            font=dict(color=Theme.TEXT_SECONDARY, size=10),
            bgcolor="rgba(20, 25, 35, 0.9)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1
        )
        
        fig.update_layout(**layout)
        return fig
