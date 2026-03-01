"""
Monte Carlo simulation engine for risk analysis.

Implements:
- Risk of ruin estimation
- Equity curve simulation
- Drawdown distribution analysis
- Tail risk assessment
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from scipy import stats


@dataclass
class MonteCarloResults:
    """Results from Monte Carlo simulation."""
    # Ruin statistics
    ruin_probability: float
    ruin_threshold: float
    
    # Terminal wealth statistics
    terminal_wealth_mean: float
    terminal_wealth_median: float
    terminal_wealth_std: float
    terminal_wealth_percentiles: Dict[int, float]
    
    # Drawdown statistics
    max_drawdown_mean: float
    max_drawdown_median: float
    max_drawdown_percentiles: Dict[int, float]
    
    # Path statistics
    equity_curves: List[np.ndarray]
    drawdown_curves: List[np.ndarray]
    
    # Additional metrics
    probability_profit: float
    probability_double: float
    expected_return: float
    
    def summary(self) -> str:
        """Generate text summary of results."""
        lines = [
            "=" * 60,
            "MONTE CARLO SIMULATION RESULTS",
            "=" * 60,
            f"",
            f"Ruin Probability (>{self.ruin_threshold:.0%} loss): {self.ruin_probability:.2%}",
            f"",
            f"Terminal Wealth Statistics:",
            f"  Mean:   {self.terminal_wealth_mean:,.0f}",
            f"  Median: {self.terminal_wealth_median:,.0f}",
            f"  Std:    {self.terminal_wealth_std:,.0f}",
            f"  5th %ile: {self.terminal_wealth_percentiles[5]:,.0f}",
            f"  95th %ile: {self.terminal_wealth_percentiles[95]:,.0f}",
            f"",
            f"Max Drawdown Statistics:",
            f"  Mean:   {self.max_drawdown_mean:.2%}",
            f"  Median: {self.max_drawdown_median:.2%}",
            f"  95th %ile: {self.max_drawdown_percentiles[95]:.2%}",
            f"",
            f"Outcome Probabilities:",
            f"  Probability of Profit: {self.probability_profit:.2%}",
            f"  Probability of Doubling: {self.probability_double:.2%}",
            f"  Expected Return: {self.expected_return:.2%}",
            "=" * 60
        ]
        return "\n".join(lines)


class MonteCarloSimulator:
    """
    Monte Carlo simulation engine for trading strategy risk analysis.
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize Monte Carlo simulator.
        
        Args:
            seed: Random seed for reproducibility
        """
        self.rng = np.random.RandomState(seed)
    
    def simulate_fixed_parameters(
        self,
        n_trades: int,
        n_sims: int,
        win_probability: float,
        win_loss_ratio: float,
        risk_per_trade: float,
        starting_equity: float = 100000,
        ruin_threshold: float = 0.20
    ) -> MonteCarloResults:
        """
        Run Monte Carlo simulation with fixed parameters.
        
        Args:
            n_trades: Number of trades per simulation
            n_sims: Number of simulations
            win_probability: Probability of winning trade
            win_loss_ratio: Average win / average loss ratio
            risk_per_trade: Risk per trade as fraction of equity
            starting_equity: Starting equity
            ruin_threshold: Ruin threshold (fraction of starting equity)
        
        Returns:
            MonteCarloResults
        """
        equity_curves = []
        drawdown_curves = []
        terminal_wealths = []
        max_drawdowns = []
        ruin_count = 0
        
        for _ in range(n_sims):
            equity = starting_equity
            peak = starting_equity
            equity_curve = [equity]
            drawdown_curve = [0.0]
            ruined = False
            
            for _ in range(n_trades):
                # Determine trade outcome
                is_win = self.rng.random() < win_probability
                
                # Calculate return multiple
                if is_win:
                    r_multiple = win_loss_ratio
                else:
                    r_multiple = -1.0
                
                # Update equity
                equity *= (1 + risk_per_trade * r_multiple)
                equity_curve.append(equity)
                
                # Update peak and drawdown
                if equity > peak:
                    peak = equity
                drawdown = (peak - equity) / peak
                drawdown_curve.append(drawdown)
                
                # Check ruin
                if equity < starting_equity * (1 - ruin_threshold):
                    ruined = True
                    break
            
            equity_curves.append(np.array(equity_curve))
            drawdown_curves.append(np.array(drawdown_curve))
            terminal_wealths.append(equity)
            max_drawdowns.append(max(drawdown_curve))
            
            if ruined:
                ruin_count += 1
        
        return self._compile_results(
            equity_curves, drawdown_curves, terminal_wealths,
            max_drawdowns, ruin_count, n_sims, starting_equity, ruin_threshold
        )
    
    def simulate_from_trades(
        self,
        trades: List[float],
        n_sims: int,
        risk_per_trade: float,
        starting_equity: float = 100000,
        ruin_threshold: float = 0.20,
        block_bootstrap: bool = True,
        block_size: int = 10
    ) -> MonteCarloResults:
        """
        Run Monte Carlo simulation using historical trade distribution.
        
        Args:
            trades: List of historical trade returns (in R multiples)
            n_sims: Number of simulations
            risk_per_trade: Risk per trade as fraction of equity
            starting_equity: Starting equity
            ruin_threshold: Ruin threshold
            block_bootstrap: Use block bootstrap for serial correlation
            block_size: Block size for bootstrap
        
        Returns:
            MonteCarloResults
        """
        n_trades = len(trades)
        equity_curves = []
        drawdown_curves = []
        terminal_wealths = []
        max_drawdowns = []
        ruin_count = 0
        
        for _ in range(n_sims):
            equity = starting_equity
            peak = starting_equity
            equity_curve = [equity]
            drawdown_curve = [0.0]
            ruined = False
            
            if block_bootstrap:
                # Block bootstrap to preserve serial correlation
                n_blocks = (n_trades + block_size - 1) // block_size
                sampled_returns = []
                
                for _ in range(n_blocks):
                    start_idx = self.rng.randint(0, n_trades - block_size + 1)
                    block = trades[start_idx:start_idx + block_size]
                    sampled_returns.extend(block)
                
                sampled_returns = sampled_returns[:n_trades]
            else:
                # Simple bootstrap
                sampled_returns = self.rng.choice(trades, size=n_trades, replace=True)
            
            for r_multiple in sampled_returns:
                # Update equity
                equity *= (1 + risk_per_trade * r_multiple)
                equity_curve.append(equity)
                
                # Update peak and drawdown
                if equity > peak:
                    peak = equity
                drawdown = (peak - equity) / peak
                drawdown_curve.append(drawdown)
                
                # Check ruin
                if equity < starting_equity * (1 - ruin_threshold):
                    ruined = True
                    break
            
            equity_curves.append(np.array(equity_curve))
            drawdown_curves.append(np.array(drawdown_curve))
            terminal_wealths.append(equity)
            max_drawdowns.append(max(drawdown_curve))
            
            if ruined:
                ruin_count += 1
        
        return self._compile_results(
            equity_curves, drawdown_curves, terminal_wealths,
            max_drawdowns, ruin_count, n_sims, starting_equity, ruin_threshold
        )
    
    def simulate_regime_switching(
        self,
        n_trades: int,
        n_sims: int,
        regimes: List[Dict],
        transition_matrix: np.ndarray,
        risk_per_trade: float,
        starting_equity: float = 100000,
        ruin_threshold: float = 0.20
    ) -> MonteCarloResults:
        """
        Run Monte Carlo with regime switching.
        
        Args:
            n_trades: Number of trades per simulation
            n_sims: Number of simulations
            regimes: List of regime dictionaries with 'win_prob', 'win_loss_ratio'
            transition_matrix: Markov transition matrix between regimes
            risk_per_trade: Risk per trade
            starting_equity: Starting equity
            ruin_threshold: Ruin threshold
        
        Returns:
            MonteCarloResults
        """
        n_regimes = len(regimes)
        equity_curves = []
        drawdown_curves = []
        terminal_wealths = []
        max_drawdowns = []
        ruin_count = 0
        
        for _ in range(n_sims):
            equity = starting_equity
            peak = starting_equity
            equity_curve = [equity]
            drawdown_curve = [0.0]
            ruined = False
            
            # Start in random regime
            current_regime = self.rng.randint(0, n_regimes)
            
            for _ in range(n_trades):
                # Get current regime parameters
                regime = regimes[current_regime]
                win_prob = regime['win_prob']
                win_loss_ratio = regime['win_loss_ratio']
                
                # Determine trade outcome
                is_win = self.rng.random() < win_prob
                
                if is_win:
                    r_multiple = win_loss_ratio
                else:
                    r_multiple = -1.0
                
                # Update equity
                equity *= (1 + risk_per_trade * r_multiple)
                equity_curve.append(equity)
                
                # Update peak and drawdown
                if equity > peak:
                    peak = equity
                drawdown = (peak - equity) / peak
                drawdown_curve.append(drawdown)
                
                # Check ruin
                if equity < starting_equity * (1 - ruin_threshold):
                    ruined = True
                    break
                
                # Regime transition
                current_regime = self.rng.choice(
                    n_regimes, p=transition_matrix[current_regime]
                )
            
            equity_curves.append(np.array(equity_curve))
            drawdown_curves.append(np.array(drawdown_curve))
            terminal_wealths.append(equity)
            max_drawdowns.append(max(drawdown_curve))
            
            if ruined:
                ruin_count += 1
        
        return self._compile_results(
            equity_curves, drawdown_curves, terminal_wealths,
            max_drawdowns, ruin_count, n_sims, starting_equity, ruin_threshold
        )
    
    def simulate_stress_scenario(
        self,
        n_trades: int,
        n_sims: int,
        base_win_prob: float,
        base_win_loss_ratio: float,
        stress_periods: List[Tuple[int, int, Dict]],
        risk_per_trade: float,
        starting_equity: float = 100000,
        ruin_threshold: float = 0.20
    ) -> MonteCarloResults:
        """
        Run Monte Carlo with stress periods.
        
        Args:
            n_trades: Number of trades
            n_sims: Number of simulations
            base_win_prob: Base win probability
            base_win_loss_ratio: Base win/loss ratio
            stress_periods: List of (start, end, params) for stress periods
            risk_per_trade: Risk per trade
            starting_equity: Starting equity
            ruin_threshold: Ruin threshold
        
        Returns:
            MonteCarloResults
        """
        equity_curves = []
        drawdown_curves = []
        terminal_wealths = []
        max_drawdowns = []
        ruin_count = 0
        
        for _ in range(n_sims):
            equity = starting_equity
            peak = starting_equity
            equity_curve = [equity]
            drawdown_curve = [0.0]
            ruined = False
            
            for trade_idx in range(n_trades):
                # Determine if in stress period
                win_prob = base_win_prob
                win_loss_ratio = base_win_loss_ratio
                
                for start, end, params in stress_periods:
                    if start <= trade_idx < end:
                        win_prob = params.get('win_prob', win_prob)
                        win_loss_ratio = params.get('win_loss_ratio', win_loss_ratio)
                        break
                
                # Determine trade outcome
                is_win = self.rng.random() < win_prob
                
                if is_win:
                    r_multiple = win_loss_ratio
                else:
                    r_multiple = -1.0
                
                # Update equity
                equity *= (1 + risk_per_trade * r_multiple)
                equity_curve.append(equity)
                
                # Update peak and drawdown
                if equity > peak:
                    peak = equity
                drawdown = (peak - equity) / peak
                drawdown_curve.append(drawdown)
                
                # Check ruin
                if equity < starting_equity * (1 - ruin_threshold):
                    ruined = True
                    break
            
            equity_curves.append(np.array(equity_curve))
            drawdown_curves.append(np.array(drawdown_curve))
            terminal_wealths.append(equity)
            max_drawdowns.append(max(drawdown_curve))
            
            if ruined:
                ruin_count += 1
        
        return self._compile_results(
            equity_curves, drawdown_curves, terminal_wealths,
            max_drawdowns, ruin_count, n_sims, starting_equity, ruin_threshold
        )
    
    def _compile_results(
        self,
        equity_curves: List[np.ndarray],
        drawdown_curves: List[np.ndarray],
        terminal_wealths: List[float],
        max_drawdowns: List[float],
        ruin_count: int,
        n_sims: int,
        starting_equity: float,
        ruin_threshold: float
    ) -> MonteCarloResults:
        """
        Compile simulation results.
        
        Args:
            equity_curves: List of equity curves
            drawdown_curves: List of drawdown curves
            terminal_wealths: List of terminal wealth values
            max_drawdowns: List of max drawdowns
            ruin_count: Number of ruin events
            n_sims: Total number of simulations
            starting_equity: Starting equity
            ruin_threshold: Ruin threshold
        
        Returns:
            MonteCarloResults
        """
        terminal_wealths = np.array(terminal_wealths)
        max_drawdowns = np.array(max_drawdowns)
        
        # Calculate percentiles
        wealth_percentiles = {
            5: np.percentile(terminal_wealths, 5),
            10: np.percentile(terminal_wealths, 10),
            25: np.percentile(terminal_wealths, 25),
            50: np.percentile(terminal_wealths, 50),
            75: np.percentile(terminal_wealths, 75),
            90: np.percentile(terminal_wealths, 90),
            95: np.percentile(terminal_wealths, 95)
        }
        
        drawdown_percentiles = {
            5: np.percentile(max_drawdowns, 5),
            10: np.percentile(max_drawdowns, 10),
            25: np.percentile(max_drawdowns, 25),
            50: np.percentile(max_drawdowns, 50),
            75: np.percentile(max_drawdowns, 75),
            90: np.percentile(max_drawdowns, 90),
            95: np.percentile(max_drawdowns, 95)
        }
        
        # Calculate probabilities
        probability_profit = np.mean(terminal_wealths > starting_equity)
        probability_double = np.mean(terminal_wealths > 2 * starting_equity)
        expected_return = np.mean(terminal_wealths) / starting_equity - 1
        
        return MonteCarloResults(
            ruin_probability=ruin_count / n_sims,
            ruin_threshold=ruin_threshold,
            terminal_wealth_mean=np.mean(terminal_wealths),
            terminal_wealth_median=np.median(terminal_wealths),
            terminal_wealth_std=np.std(terminal_wealths),
            terminal_wealth_percentiles=wealth_percentiles,
            max_drawdown_mean=np.mean(max_drawdowns),
            max_drawdown_median=np.median(max_drawdowns),
            max_drawdown_percentiles=drawdown_percentiles,
            equity_curves=equity_curves,
            drawdown_curves=drawdown_curves,
            probability_profit=probability_profit,
            probability_double=probability_double,
            expected_return=expected_return
        )
    
    def kelly_analysis(
        self,
        win_probability: float,
        win_loss_ratio: float,
        risk_fractions: np.ndarray = None
    ) -> pd.DataFrame:
        """
        Analyze growth rate vs Kelly fraction.
        
        Args:
            win_probability: Win probability
            win_loss_ratio: Win/loss ratio
            risk_fractions: Array of risk fractions to test
        
        Returns:
            DataFrame with analysis results
        """
        if risk_fractions is None:
            risk_fractions = np.linspace(0, 0.5, 51)
        
        q = 1 - win_probability
        
        # Full Kelly
        kelly_full = (win_probability * win_loss_ratio - q) / win_loss_ratio
        
        results = []
        for f in risk_fractions:
            # Geometric growth rate
            g = win_probability * np.log(1 + f * win_loss_ratio) + \
                q * np.log(1 - f)
            
            results.append({
                'risk_fraction': f,
                'kelly_fraction': f / kelly_full if kelly_full > 0 else 0,
                'geometric_growth_rate': g,
                'is_full_kelly': abs(f - kelly_full) < 0.001,
                'is_half_kelly': abs(f - kelly_full / 2) < 0.001,
                'is_quarter_kelly': abs(f - kelly_full / 4) < 0.001
            })
        
        return pd.DataFrame(results)
