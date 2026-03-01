"""
Performance metrics calculation for backtesting.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from scipy import stats

from ..common.types import Trade, Order, Signal


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    
    # Equity
    equity_curve: pd.Series
    returns: pd.Series
    
    # Trade data
    trades: List[Trade]
    orders: List[Order]
    signals: List[Signal]
    
    # Capital
    initial_capital: float
    final_equity: float
    total_return: float
    
    # Risk-adjusted returns
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    
    # Trade statistics
    num_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    
    # Costs
    commission_total: float
    slippage_total: float
    
    def summary(self) -> str:
        """Generate text summary."""
        win_rate = self.winning_trades / self.num_trades if self.num_trades > 0 else 0
        
        lines = [
            "=" * 60,
            "BACKTEST PERFORMANCE SUMMARY",
            "=" * 60,
            f"",
            f"Capital:",
            f"  Initial:     ${self.initial_capital:,.2f}",
            f"  Final:       ${self.final_equity:,.2f}",
            f"  Total Return: {self.total_return:.2%}",
            f"",
            f"Risk-Adjusted Returns:",
            f"  Sharpe Ratio:  {self.sharpe_ratio:.2f}",
            f"  Sortino Ratio: {self.sortino_ratio:.2f}",
            f"  Max Drawdown:  {self.max_drawdown:.2%}",
            f"",
            f"Trade Statistics:",
            f"  Total Trades:  {self.num_trades}",
            f"  Win Rate:      {win_rate:.2%}",
            f"  Profit Factor: {self.profit_factor:.2f}",
            f"  Avg Trade:     ${self.avg_trade_pnl:,.2f}",
            f"  Avg Win:       ${self.avg_win:,.2f}",
            f"  Avg Loss:      ${self.avg_loss:,.2f}",
            f"",
            f"Costs:",
            f"  Commission:    ${self.commission_total:,.2f}",
            f"  Slippage:      ${self.slippage_total:,.2f}",
            f"  Total Costs:   ${self.commission_total + self.slippage_total:,.2f}",
            "=" * 60
        ]
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        win_rate = self.winning_trades / self.num_trades if self.num_trades > 0 else 0
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': self.final_equity,
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'max_drawdown': self.max_drawdown,
            'num_trades': self.num_trades,
            'win_rate': win_rate,
            'profit_factor': self.profit_factor,
            'avg_trade_pnl': self.avg_trade_pnl,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'commission_total': self.commission_total,
            'slippage_total': self.slippage_total
        }
    
    def calculate_calmar_ratio(self, periods_per_year: int = 252) -> float:
        """
        Calculate Calmar ratio.
        
        Args:
            periods_per_year: Trading periods per year
        
        Returns:
            Calmar ratio
        """
        annual_return = self.returns.mean() * periods_per_year
        if self.max_drawdown == 0:
            return 0.0
        return annual_return / abs(self.max_drawdown)
    
    def calculate_omega_ratio(self, threshold: float = 0.0) -> float:
        """
        Calculate Omega ratio.
        
        Args:
            threshold: Return threshold
        
        Returns:
            Omega ratio
        """
        excess_returns = self.returns - threshold
        gains = excess_returns[excess_returns > 0].sum()
        losses = abs(excess_returns[excess_returns < 0].sum())
        
        if losses == 0:
            return float('inf')
        return gains / losses
    
    def calculate_tail_ratio(self, percentile: float = 5.0) -> float:
        """
        Calculate tail ratio (95th percentile gain / 5th percentile loss).
        
        Args:
            percentile: Tail percentile
        
        Returns:
            Tail ratio
        """
        upper_tail = np.percentile(self.returns, 100 - percentile)
        lower_tail = abs(np.percentile(self.returns, percentile))
        
        if lower_tail == 0:
            return float('inf')
        return upper_tail / lower_tail
    
    def calculate_common_sense_ratio(self) -> float:
        """
        Calculate Common Sense Ratio (Tail Ratio * Gain/Pain Ratio).
        
        Returns:
            Common Sense Ratio
        """
        tail_ratio = self.calculate_tail_ratio()
        
        gains = self.returns[self.returns > 0].sum()
        pains = abs(self.returns[self.returns < 0].sum())
        
        if pains == 0:
            gain_pain = float('inf')
        else:
            gain_pain = gains / pains
        
        return tail_ratio * gain_pain
    
    def calculate_skewness(self) -> float:
        """Calculate return skewness."""
        return self.returns.skew()
    
    def calculate_kurtosis(self) -> float:
        """Calculate return kurtosis."""
        return self.returns.kurtosis()
    
    def calculate_var(self, confidence: float = 0.95) -> float:
        """
        Calculate Value at Risk.
        
        Args:
            confidence: Confidence level
        
        Returns:
            VaR as negative return
        """
        return np.percentile(self.returns, (1 - confidence) * 100)
    
    def calculate_cvar(self, confidence: float = 0.95) -> float:
        """
        Calculate Conditional Value at Risk (Expected Shortfall).
        
        Args:
            confidence: Confidence level
        
        Returns:
            CVaR as negative return
        """
        var = self.calculate_var(confidence)
        return self.returns[self.returns <= var].mean()
    
    def calculate_trade_expectancy(self) -> float:
        """
        Calculate trade expectancy in R multiples.
        
        Returns:
            Expectancy per trade
        """
        if not self.trades:
            return 0.0
        
        wins = [t for t in self.trades if t.net_pnl > 0]
        losses = [t for t in self.trades if t.net_pnl <= 0]
        
        win_rate = len(wins) / len(self.trades)
        loss_rate = 1 - win_rate
        
        avg_win_r = np.mean([t.return_multiple for t in wins]) if wins else 0
        avg_loss_r = np.mean([t.return_multiple for t in losses]) if losses else 0
        
        return win_rate * avg_win_r - loss_rate * abs(avg_loss_r)
    
    def get_monthly_returns(self) -> pd.Series:
        """Get monthly returns series."""
        return self.returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
    
    def get_annual_returns(self) -> pd.Series:
        """Get annual returns series."""
        return self.returns.resample('Y').apply(lambda x: (1 + x).prod() - 1)
    
    def get_drawdown_series(self) -> pd.Series:
        """Get drawdown series."""
        rolling_max = self.equity_curve.cummax()
        return (self.equity_curve - rolling_max) / rolling_max
    
    def get_trade_analysis(self) -> Dict:
        """Get detailed trade analysis."""
        if not self.trades:
            return {}
        
        trades_df = pd.DataFrame([
            {
                'symbol': t.symbol,
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'duration': (t.exit_time - t.entry_time).total_seconds() / 3600,  # hours
                'net_pnl': t.net_pnl,
                'return_multiple': t.return_multiple,
                'exit_reason': t.exit_reason
            }
            for t in self.trades
        ])
        
        return {
            'avg_duration_hours': trades_df['duration'].mean(),
            'median_duration_hours': trades_df['duration'].median(),
            'exit_reason_counts': trades_df['exit_reason'].value_counts().to_dict(),
            'best_trade': trades_df['net_pnl'].max(),
            'worst_trade': trades_df['net_pnl'].min(),
            'consecutive_wins': self._calculate_consecutive(trades_df['net_pnl'] > 0),
            'consecutive_losses': self._calculate_consecutive(trades_df['net_pnl'] <= 0)
        }
    
    def _calculate_consecutive(self, series: pd.Series) -> Dict:
        """Calculate consecutive streaks."""
        streaks = []
        current_streak = 0
        
        for value in series:
            if value:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        
        if current_streak > 0:
            streaks.append(current_streak)
        
        return {
            'max': max(streaks) if streaks else 0,
            'avg': np.mean(streaks) if streaks else 0
        }
    
    def plot_equity_curve(self, save_path: Optional[str] = None):
        """
        Plot equity curve.
        
        Args:
            save_path: Path to save plot
        """
        try:
            import matplotlib.pyplot as plt
            
            fig, axes = plt.subplots(3, 1, figsize=(12, 10))
            
            # Equity curve
            axes[0].plot(self.equity_curve.index, self.equity_curve.values)
            axes[0].set_title('Equity Curve')
            axes[0].set_ylabel('Equity ($)')
            axes[0].grid(True)
            
            # Drawdown
            drawdown = self.get_drawdown_series()
            axes[1].fill_between(drawdown.index, drawdown.values, 0, color='red', alpha=0.3)
            axes[1].set_title('Drawdown')
            axes[1].set_ylabel('Drawdown (%)')
            axes[1].grid(True)
            
            # Returns distribution
            axes[2].hist(self.returns.dropna(), bins=50, alpha=0.7, edgecolor='black')
            axes[2].set_title('Returns Distribution')
            axes[2].set_xlabel('Return')
            axes[2].set_ylabel('Frequency')
            axes[2].grid(True)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=150, bbox_inches='tight')
            else:
                plt.show()
        except ImportError:
            print("matplotlib not available for plotting")
