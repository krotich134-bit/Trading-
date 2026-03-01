"""
Backtesting framework for the AI Trading System.
"""

from .engine import BacktestEngine
from .walk_forward import WalkForwardOptimizer
from .metrics import PerformanceMetrics
from .slippage import SlippageModel, MarketImpactModel

__all__ = [
    'BacktestEngine',
    'WalkForwardOptimizer',
    'PerformanceMetrics',
    'SlippageModel',
    'MarketImpactModel'
]
