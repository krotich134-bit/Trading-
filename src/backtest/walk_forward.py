"""
Walk-forward optimization framework.

Implements rolling and expanding window cross-validation for time series.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Callable, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from tqdm import tqdm

from .engine import BacktestEngine, BacktestConfig
from .metrics import PerformanceMetrics


@dataclass
class WalkForwardConfig:
    """Walk-forward optimization configuration."""
    train_size: int  # Number of bars in training window
    test_size: int   # Number of bars in test window
    step_size: int   # Step size between windows
    window_type: str = "rolling"  # 'rolling' or 'expanding'
    min_train_size: int = 252  # Minimum training size for expanding window


class WalkForwardOptimizer:
    """
    Walk-forward optimization for trading strategies.
    
    Prevents lookahead bias by using only past data for parameter optimization.
    """
    
    def __init__(self, config: WalkForwardConfig):
        """
        Initialize walk-forward optimizer.
        
        Args:
            config: WalkForwardConfig
        """
        self.config = config
        self.results = []
        self.optimal_params = []
    
    def run(
        self,
        data: Dict[str, pd.DataFrame],
        strategy_class: type,
        param_grid: Dict[str, List],
        backtest_config: BacktestConfig,
        optimization_metric: str = "sharpe_ratio"
    ) -> pd.DataFrame:
        """
        Run walk-forward optimization.
        
        Args:
            data: Price data dictionary
            strategy_class: Strategy class to optimize
            param_grid: Parameter grid to search
            backtest_config: Backtest configuration
            optimization_metric: Metric to optimize
        
        Returns:
            DataFrame with results for each window
        """
        # Get all timestamps
        all_timestamps = sorted(set(
            ts for df in data.values() for ts in df.index
        ))
        
        n_bars = len(all_timestamps)
        
        # Generate windows
        windows = self._generate_windows(n_bars)
        
        print(f"Running walk-forward optimization: {len(windows)} windows")
        
        results = []
        
        for i, (train_start, train_end, test_start, test_end) in enumerate(tqdm(windows)):
            print(f"\nWindow {i+1}/{len(windows)}")
            print(f"  Train: {all_timestamps[train_start]} to {all_timestamps[train_end]}")
            print(f"  Test:  {all_timestamps[test_start]} to {all_timestamps[test_end]}")
            
            # Split data
            train_timestamps = all_timestamps[train_start:train_end]
            test_timestamps = all_timestamps[test_start:test_end]
            
            train_data = self._slice_data(data, train_timestamps[0], train_timestamps[-1])
            test_data = self._slice_data(data, test_timestamps[0], test_timestamps[-1])
            
            # Optimize parameters on training data
            best_params = self._optimize_params(
                train_data, strategy_class, param_grid,
                backtest_config, optimization_metric
            )
            
            print(f"  Best params: {best_params}")
            
            # Test on out-of-sample data
            test_metrics = self._test_params(
                test_data, strategy_class, best_params, backtest_config
            )
            
            # Store results
            result = {
                'window': i,
                'train_start': all_timestamps[train_start],
                'train_end': all_timestamps[train_end],
                'test_start': all_timestamps[test_start],
                'test_end': all_timestamps[test_end],
                'best_params': best_params,
                'test_sharpe': test_metrics.sharpe_ratio,
                'test_return': test_metrics.total_return,
                'test_drawdown': test_metrics.max_drawdown,
                'test_trades': test_metrics.num_trades,
                'test_win_rate': test_metrics.winning_trades / test_metrics.num_trades if test_metrics.num_trades > 0 else 0
            }
            
            results.append(result)
            self.optimal_params.append(best_params)
        
        self.results = pd.DataFrame(results)
        return self.results
    
    def _generate_windows(self, n_bars: int) -> List[Tuple[int, int, int, int]]:
        """
        Generate train/test window indices.
        
        Args:
            n_bars: Total number of bars
        
        Returns:
            List of (train_start, train_end, test_start, test_end) tuples
        """
        windows = []
        
        if self.config.window_type == "rolling":
            # Rolling window
            start = 0
            while start + self.config.train_size + self.config.test_size <= n_bars:
                train_start = start
                train_end = start + self.config.train_size
                test_start = train_end
                test_end = test_start + self.config.test_size
                
                windows.append((train_start, train_end, test_start, test_end))
                start += self.config.step_size
        
        else:  # expanding
            # Expanding window
            train_end = self.config.min_train_size
            while train_end + self.config.test_size <= n_bars:
                train_start = 0
                test_start = train_end
                test_end = test_start + self.config.test_size
                
                windows.append((train_start, train_end, test_start, test_end))
                train_end += self.config.step_size
        
        return windows
    
    def _slice_data(
        self,
        data: Dict[str, pd.DataFrame],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, pd.DataFrame]:
        """
        Slice data by time range.
        
        Args:
            data: Price data dictionary
            start_time: Start time
            end_time: End time
        
        Returns:
            Sliced data dictionary
        """
        sliced = {}
        for symbol, df in data.items():
            mask = (df.index >= start_time) & (df.index <= end_time)
            sliced[symbol] = df.loc[mask].copy()
        return sliced
    
    def _optimize_params(
        self,
        train_data: Dict[str, pd.DataFrame],
        strategy_class: type,
        param_grid: Dict[str, List],
        backtest_config: BacktestConfig,
        metric: str
    ) -> Dict[str, Any]:
        """
        Optimize parameters on training data.
        
        Args:
            train_data: Training data
            strategy_class: Strategy class
            param_grid: Parameter grid
            backtest_config: Backtest configuration
            metric: Optimization metric
        
        Returns:
            Best parameters
        """
        from itertools import product
        
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        param_combinations = list(product(*param_values))
        
        best_metric = -np.inf
        best_params = {}
        
        for param_combo in param_combinations:
            params = dict(zip(param_names, param_combo))
            
            try:
                # Create strategy with these parameters
                strategy = strategy_class(**params)
                
                # Run backtest
                engine = BacktestEngine(backtest_config)
                
                def signal_generator(data, timestamp):
                    signals = []
                    for symbol, df in data.items():
                        if timestamp in df.index:
                            idx = df.index.get_loc(timestamp)
                            if idx >= 50:  # Minimum data needed
                                signal = strategy.generate_signal(
                                    df.iloc[:idx+1], symbol
                                )
                                if signal:
                                    signals.append(signal)
                    return signals
                
                metrics = engine.run(train_data, signal_generator)
                
                # Get metric value
                metric_value = getattr(metrics, metric, 0)
                
                if metric_value > best_metric:
                    best_metric = metric_value
                    best_params = params
            
            except Exception as e:
                print(f"Error with params {params}: {e}")
                continue
        
        return best_params
    
    def _test_params(
        self,
        test_data: Dict[str, pd.DataFrame],
        strategy_class: type,
        params: Dict[str, Any],
        backtest_config: BacktestConfig
    ) -> PerformanceMetrics:
        """
        Test parameters on out-of-sample data.
        
        Args:
            test_data: Test data
            strategy_class: Strategy class
            params: Parameters to test
            backtest_config: Backtest configuration
        
        Returns:
            PerformanceMetrics
        """
        strategy = strategy_class(**params)
        
        engine = BacktestEngine(backtest_config)
        
        def signal_generator(data, timestamp):
            signals = []
            for symbol, df in data.items():
                if timestamp in df.index:
                    idx = df.index.get_loc(timestamp)
                    if idx >= 50:
                        signal = strategy.generate_signal(
                            df.iloc[:idx+1], symbol
                        )
                        if signal:
                            signals.append(signal)
            return signals
        
        return engine.run(test_data, signal_generator)
    
    def get_consolidated_results(self) -> Dict[str, float]:
        """
        Get consolidated results across all windows.
        
        Returns:
            Dictionary with aggregated metrics
        """
        if self.results is None or len(self.results) == 0:
            return {}
        
        return {
            'avg_sharpe': self.results['test_sharpe'].mean(),
            'std_sharpe': self.results['test_sharpe'].std(),
            'avg_return': self.results['test_return'].mean(),
            'std_return': self.results['test_return'].std(),
            'avg_drawdown': self.results['test_drawdown'].mean(),
            'avg_trades': self.results['test_trades'].mean(),
            'avg_win_rate': self.results['test_win_rate'].mean(),
            'param_stability': self._calculate_param_stability()
        }
    
    def _calculate_param_stability(self) -> float:
        """
        Calculate parameter stability across windows.
        
        Returns:
            Stability score (0-1, higher is more stable)
        """
        if len(self.optimal_params) < 2:
            return 1.0
        
        # Count how often each parameter value is chosen
        param_counts = {}
        for params in self.optimal_params:
            for key, value in params.items():
                if key not in param_counts:
                    param_counts[key] = {}
                if value not in param_counts[key]:
                    param_counts[key][value] = 0
                param_counts[key][value] += 1
        
        # Calculate stability as average of max frequency
        stabilities = []
        for key, counts in param_counts.items():
            max_freq = max(counts.values())
            stability = max_freq / len(self.optimal_params)
            stabilities.append(stability)
        
        return np.mean(stabilities)
    
    def plot_results(self, save_path: Optional[str] = None):
        """
        Plot walk-forward results.
        
        Args:
            save_path: Path to save plot
        """
        try:
            import matplotlib.pyplot as plt
            
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            
            # Sharpe ratio by window
            axes[0, 0].plot(self.results['window'], self.results['test_sharpe'], marker='o')
            axes[0, 0].axhline(y=self.results['test_sharpe'].mean(), color='r', linestyle='--')
            axes[0, 0].set_title('Sharpe Ratio by Window')
            axes[0, 0].set_xlabel('Window')
            axes[0, 0].set_ylabel('Sharpe Ratio')
            axes[0, 0].grid(True)
            
            # Return by window
            axes[0, 1].plot(self.results['window'], self.results['test_return'], marker='o')
            axes[0, 1].axhline(y=self.results['test_return'].mean(), color='r', linestyle='--')
            axes[0, 1].set_title('Return by Window')
            axes[0, 1].set_xlabel('Window')
            axes[0, 1].set_ylabel('Return')
            axes[0, 1].grid(True)
            
            # Drawdown by window
            axes[1, 0].plot(self.results['window'], self.results['test_drawdown'], marker='o')
            axes[1, 0].axhline(y=self.results['test_drawdown'].mean(), color='r', linestyle='--')
            axes[1, 0].set_title('Max Drawdown by Window')
            axes[1, 0].set_xlabel('Window')
            axes[1, 0].set_ylabel('Drawdown')
            axes[1, 0].grid(True)
            
            # Win rate by window
            axes[1, 1].plot(self.results['window'], self.results['test_win_rate'], marker='o')
            axes[1, 1].axhline(y=self.results['test_win_rate'].mean(), color='r', linestyle='--')
            axes[1, 1].set_title('Win Rate by Window')
            axes[1, 1].set_xlabel('Window')
            axes[1, 1].set_ylabel('Win Rate')
            axes[1, 1].grid(True)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=150, bbox_inches='tight')
            else:
                plt.show()
        
        except ImportError:
            print("matplotlib not available for plotting")
