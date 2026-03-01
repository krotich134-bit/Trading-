"""
Signal generation module for the AI Trading System.
"""

from .features import FeatureEngineer
from .strategies import (
    MomentumStrategy,
    MeanReversionStrategy,
    StatisticalArbitrageStrategy,
    VolatilityStrategy,
    RegimeDetectionStrategy
)
from .ensemble import SignalEnsemble, EnsembleMethod

__all__ = [
    'FeatureEngineer',
    'MomentumStrategy',
    'MeanReversionStrategy',
    'StatisticalArbitrageStrategy',
    'VolatilityStrategy',
    'RegimeDetectionStrategy',
    'SignalEnsemble',
    'EnsembleMethod'
]
