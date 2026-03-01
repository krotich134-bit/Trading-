"""
Portfolio risk management and exposure controls.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict

from ..common.types import Position, PortfolioState, RiskMetrics, Signal
from ..common.utils import compute_correlation_matrix, max_drawdown


@dataclass
class RiskLimits:
    """Risk limit configuration."""
    # Per-trade limits
    max_risk_per_trade: float = 0.02  # 2% max
    default_risk_per_trade: float = 0.005  # 0.5% default
    
    # Position limits
    max_single_position: float = 0.10  # 10% of portfolio
    max_sector_exposure: float = 0.25  # 25% per sector
    max_total_positions: int = 20
    
    # Portfolio heat
    max_portfolio_heat: float = 0.15  # 15% portfolio heat
    
    # Drawdown controls
    daily_loss_limit: float = 0.05  # 5% daily loss
    monthly_loss_limit: float = 0.20  # 20% monthly loss
    quarterly_loss_limit: float = 0.30  # 30% quarterly loss
    
    # Exposure throttling
    drawdown_5pct_action: str = "cut_50"  # Cut size 50%
    drawdown_10pct_action: str = "cut_75"  # Cut size 75%
    drawdown_15pct_action: str = "halt"  # Halt new risk
    
    # Correlation trigger
    correlation_threshold: float = 0.70
    correlation_action: str = "reduce_exposure"
    
    # Volatility trigger
    vol_stress_multiplier: float = 1.5
    vol_stress_action: str = "reduce_exposure"


class RiskManager:
    """
    Portfolio-level risk manager.
    
    Implements:
    - Position-level risk checks
    - Portfolio heat calculation
    - Drawdown-based throttling
    - Correlation stress detection
    - Circuit breakers
    """
    
    def __init__(self, limits: RiskLimits):
        """
        Initialize risk manager.
        
        Args:
            limits: RiskLimits configuration
        """
        self.limits = limits
        self.daily_pnl = 0.0
        self.monthly_pnl = 0.0
        self.quarterly_pnl = 0.0
        self.peak_equity = 0.0
        self.current_drawdown = 0.0
        
        # Tracking
        self.daily_trades = []
        self.monthly_trades = []
        self.quarterly_trades = []
        
        # Circuit breaker state
        self.trading_halted = False
        self.halt_reason = None
        self.halt_time = None
        
        # Throttling state
        self.size_reduction_factor = 1.0
        
    def check_signal(self, signal: Signal, portfolio: PortfolioState,
                     proposed_position: Position) -> Tuple[bool, str]:
        """
        Check if signal passes all risk checks.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            proposed_position: Proposed position
        
        Returns:
            Tuple of (approved, reason)
        """
        # Check circuit breakers
        if self.trading_halted:
            return False, f"Trading halted: {self.halt_reason}"
        
        # Check position count
        if portfolio.open_positions_count >= self.limits.max_total_positions:
            return False, "Maximum position count reached"
        
        # Check single position limit
        position_value = abs(proposed_position.quantity * proposed_position.entry_price)
        position_pct = position_value / portfolio.equity if portfolio.equity > 0 else 0
        
        if position_pct > self.limits.max_single_position:
            return False, f"Position size {position_pct:.2%} exceeds limit {self.limits.max_single_position:.2%}"
        
        # Check per-trade risk
        trade_risk = proposed_position.current_risk / portfolio.equity if portfolio.equity > 0 else 0
        if trade_risk > self.limits.max_risk_per_trade:
            return False, f"Trade risk {trade_risk:.2%} exceeds limit {self.limits.max_risk_per_trade:.2%}"
        
        # Check portfolio heat
        heat = self.calculate_portfolio_heat(portfolio)
        if heat > self.limits.max_portfolio_heat:
            return False, f"Portfolio heat {heat:.2%} exceeds limit {self.limits.max_portfolio_heat:.2%}"
        
        return True, "Approved"
    
    def calculate_portfolio_heat(self, portfolio: PortfolioState) -> float:
        """
        Calculate portfolio heat: sqrt(r^T * Sigma * r)
        
        Args:
            portfolio: Current portfolio state
        
        Returns:
            Portfolio heat
        """
        if not portfolio.positions:
            return 0.0
        
        # Get active positions
        active_positions = {k: v for k, v in portfolio.positions.items() if v.is_active}
        
        if not active_positions:
            return 0.0
        
        # Build risk vector and correlation matrix
        symbols = list(active_positions.keys())
        risk_vector = np.array([
            pos.current_risk / portfolio.equity 
            for pos in active_positions.values()
        ])
        
        # Simplified correlation (would use historical returns in production)
        n = len(symbols)
        if n == 1:
            return risk_vector[0]
        
        # Assume 0.5 correlation for simplicity (would be calculated from data)
        corr_matrix = np.eye(n) * 0.5 + 0.5
        
        # Calculate portfolio heat
        heat = np.sqrt(risk_vector.T @ corr_matrix @ risk_vector)
        
        return heat
    
    def update_drawdown(self, portfolio: PortfolioState) -> None:
        """
        Update drawdown tracking and apply throttling.
        
        Args:
            portfolio: Current portfolio state
        """
        # Update peak equity
        self.peak_equity = max(self.peak_equity, portfolio.equity)
        
        # Calculate current drawdown
        if self.peak_equity > 0:
            self.current_drawdown = (self.peak_equity - portfolio.equity) / self.peak_equity
        
        # Apply throttling based on drawdown
        if self.current_drawdown >= 0.20:  # 20% drawdown
            self._apply_throttle("halt", "20% drawdown reached")
        elif self.current_drawdown >= 0.15:  # 15% drawdown
            self._apply_throttle("halt", "15% drawdown reached")
        elif self.current_drawdown >= 0.10:  # 10% drawdown
            self.size_reduction_factor = 0.25
        elif self.current_drawdown >= 0.05:  # 5% drawdown
            self.size_reduction_factor = 0.50
        else:
            self.size_reduction_factor = 1.0
    
    def _apply_throttle(self, action: str, reason: str) -> None:
        """
        Apply throttling action.
        
        Args:
            action: Throttling action
            reason: Reason for throttling
        """
        if action == "halt":
            self.trading_halted = True
            self.halt_reason = reason
            self.halt_time = datetime.utcnow()
        elif action == "cut_50":
            self.size_reduction_factor = 0.5
        elif action == "cut_75":
            self.size_reduction_factor = 0.25
    
    def check_correlation_stress(self, returns_dict: Dict[str, pd.Series]) -> bool:
        """
        Check if correlation stress condition is met.
        
        Args:
            returns_dict: Dictionary of symbol -> returns series
        
        Returns:
            True if correlation stress detected
        """
        if len(returns_dict) < 2:
            return False
        
        corr_matrix = compute_correlation_matrix(returns_dict)
        
        # Get upper triangle (excluding diagonal)
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        correlations = corr_matrix.values[mask]
        
        avg_correlation = np.mean(correlations)
        
        return avg_correlation > self.limits.correlation_threshold
    
    def check_volatility_stress(self, realized_vol: float, 
                                target_vol: float) -> bool:
        """
        Check if volatility stress condition is met.
        
        Args:
            realized_vol: Realized volatility
            target_vol: Target volatility
        
        Returns:
            True if volatility stress detected
        """
        return realized_vol > target_vol * self.limits.vol_stress_multiplier
    
    def record_trade_pnl(self, pnl: float, timestamp: datetime) -> None:
        """
        Record trade P&L for limit tracking.
        
        Args:
            pnl: Trade P&L
            timestamp: Trade timestamp
        """
        self.daily_pnl += pnl
        self.monthly_pnl += pnl
        self.quarterly_pnl += pnl
        
        # Check limits
        if self.daily_pnl < -self.limits.daily_loss_limit:
            self._apply_throttle("halt", f"Daily loss limit exceeded: {self.daily_pnl:.2%}")
        
        if self.monthly_pnl < -self.limits.monthly_loss_limit:
            self._apply_throttle("halt", f"Monthly loss limit exceeded: {self.monthly_pnl:.2%}")
        
        if self.quarterly_pnl < -self.limits.quarterly_loss_limit:
            self._apply_throttle("halt", f"Quarterly loss limit exceeded: {self.quarterly_pnl:.2%}")
    
    def reset_daily(self) -> None:
        """Reset daily tracking."""
        self.daily_pnl = 0.0
        self.daily_trades = []
    
    def reset_monthly(self) -> None:
        """Reset monthly tracking."""
        self.monthly_pnl = 0.0
        self.monthly_trades = []
    
    def reset_quarterly(self) -> None:
        """Reset quarterly tracking."""
        self.quarterly_pnl = 0.0
        self.quarterly_trades = []
    
    def get_risk_metrics(self, portfolio: PortfolioState) -> RiskMetrics:
        """
        Generate comprehensive risk metrics.
        
        Args:
            portfolio: Current portfolio state
        
        Returns:
            RiskMetrics object
        """
        # Calculate exposures
        long_exposure = sum(
            pos.quantity * pos.entry_price 
            for pos in portfolio.positions.values() 
            if pos.side.value == 'long'
        )
        short_exposure = sum(
            abs(pos.quantity) * pos.entry_price 
            for pos in portfolio.positions.values() 
            if pos.side.value == 'short'
        )
        gross_exposure = long_exposure + short_exposure
        net_exposure = long_exposure - short_exposure
        cash_ratio = portfolio.cash / portfolio.equity if portfolio.equity > 0 else 0
        
        # Calculate heat
        portfolio_heat = self.calculate_portfolio_heat(portfolio)
        
        # Calculate VaR (simplified)
        var_95 = portfolio_heat * 1.645  # 95% confidence
        var_99 = portfolio_heat * 2.326  # 99% confidence
        expected_shortfall = portfolio_heat * 2.0  # Simplified ES
        
        # Concentration
        max_position = 0.0
        for pos in portfolio.positions.values():
            pos_value = abs(pos.quantity * pos.entry_price)
            pos_pct = pos_value / portfolio.equity if portfolio.equity > 0 else 0
            max_position = max(max_position, pos_pct)
        
        return RiskMetrics(
            timestamp=datetime.utcnow(),
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            cash_ratio=cash_ratio,
            portfolio_heat=portfolio_heat,
            var_95=var_95,
            var_99=var_99,
            expected_shortfall=expected_shortfall,
            max_single_position=max_position,
            max_sector_exposure=0.0,  # Would need sector mapping
            current_drawdown=self.current_drawdown,
            max_drawdown=self.current_drawdown,  # Would track historical max
            avg_correlation=0.5,  # Would calculate from data
            correlation_stress=False  # Would check actual correlation
        )
    
    def get_status(self) -> Dict:
        """
        Get current risk manager status.
        
        Returns:
            Status dictionary
        """
        return {
            'trading_halted': self.trading_halted,
            'halt_reason': self.halt_reason,
            'halt_time': self.halt_time,
            'current_drawdown': self.current_drawdown,
            'peak_equity': self.peak_equity,
            'size_reduction_factor': self.size_reduction_factor,
            'daily_pnl': self.daily_pnl,
            'monthly_pnl': self.monthly_pnl,
            'quarterly_pnl': self.quarterly_pnl
        }
