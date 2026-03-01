"""
Trading strategy implementations.

Includes momentum, mean reversion, statistical arbitrage, volatility, and regime detection strategies.
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from scipy import stats

from ..common.types import Signal, SignalType, MarketData
from ..common.utils import hurst_exponent, cointegration_test


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""
    
    def __init__(self, strategy_id: str, confidence_threshold: float = 0.6):
        """
        Initialize strategy.
        
        Args:
            strategy_id: Unique strategy identifier
            confidence_threshold: Minimum confidence for signal generation
        """
        self.strategy_id = strategy_id
        self.confidence_threshold = confidence_threshold
        self.is_active = True
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, symbol: str,
                        **kwargs) -> Optional[Signal]:
        """
        Generate trading signal.
        
        Args:
            data: Price data DataFrame
            symbol: Trading symbol
            **kwargs: Additional parameters
        
        Returns:
            Signal or None
        """
        pass
    
    def calculate_confidence(self, indicator_value: float,
                            threshold_long: float,
                            threshold_short: float) -> Tuple[SignalType, float]:
        """
        Calculate signal confidence from indicator value.
        
        Args:
            indicator_value: Indicator value
            threshold_long: Long threshold
            threshold_short: Short threshold
        
        Returns:
            Tuple of (signal_type, confidence)
        """
        if indicator_value > threshold_long:
            confidence = min(1.0, (indicator_value - threshold_long) / abs(threshold_long) + 0.5)
            return SignalType.BUY, confidence
        elif indicator_value < threshold_short:
            confidence = min(1.0, (threshold_short - indicator_value) / abs(threshold_short) + 0.5)
            return SignalType.SELL, confidence
        else:
            return SignalType.HOLD, 0.0


class MomentumStrategy(BaseStrategy):
    """
    Time-series and cross-sectional momentum strategy.
    
    Combines multiple momentum signals with trend strength filtering.
    """
    
    def __init__(self, lookback_periods: List[int] = [20, 60, 120],
                 adx_threshold: float = 25,
                 **kwargs):
        """
        Initialize momentum strategy.
        
        Args:
            lookback_periods: List of lookback periods for momentum
            adx_threshold: ADX threshold for trend strength
        """
        super().__init__("momentum", **kwargs)
        self.lookback_periods = lookback_periods
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, data: pd.DataFrame, symbol: str,
                        **kwargs) -> Optional[Signal]:
        """
        Generate momentum signal.
        
        Args:
            data: Price data DataFrame
            symbol: Trading symbol
        
        Returns:
            Signal or None
        """
        if len(data) < max(self.lookback_periods) + 20:
            return None
        
        # Calculate momentum scores for each period
        momentum_scores = []
        for period in self.lookback_periods:
            ret = data['close'].iloc[-1] / data['close'].iloc[-period] - 1
            # Normalize by volatility
            vol = data['close'].iloc[-period:].pct_change().std() * np.sqrt(period)
            if vol > 0:
                momentum_scores.append(ret / vol)
            else:
                momentum_scores.append(0)
        
        # Combine momentum scores (weighted average)
        weights = np.array([0.5, 0.3, 0.2])  # More weight to shorter-term
        combined_momentum = np.average(momentum_scores, weights=weights)
        
        # Check trend strength (ADX)
        adx = self._calculate_adx(data)
        trend_strength = adx.iloc[-1] if not adx.empty else 0
        
        if trend_strength < self.adx_threshold:
            return None  # No strong trend
        
        # Generate signal
        if combined_momentum > 0.5:
            signal_type = SignalType.BUY
            confidence = min(1.0, abs(combined_momentum) / 2)
        elif combined_momentum < -0.5:
            signal_type = SignalType.SELL
            confidence = min(1.0, abs(combined_momentum) / 2)
        else:
            return None
        
        if confidence < self.confidence_threshold:
            return None
        
        # Calculate suggested stop
        atr = self._calculate_atr(data).iloc[-1]
        if signal_type == SignalType.BUY:
            stop = data['close'].iloc[-1] - 2 * atr
            target = data['close'].iloc[-1] + 3 * atr
        else:
            stop = data['close'].iloc[-1] + 2 * atr
            target = data['close'].iloc[-1] - 3 * atr
        
        return Signal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            signal_type=signal_type,
            confidence=confidence,
            expected_return=3.0,  # 3:1 reward/risk
            half_life_seconds=86400,  # 1 day
            strategy_id=self.strategy_id,
            metadata={
                'momentum_scores': momentum_scores,
                'trend_strength': trend_strength,
                'lookback': self.lookback_periods
            },
            suggested_stop=stop,
            suggested_target=target
        )
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ADX."""
        tr1 = df['high'] - df['low']
        tr2 = abs(df['high'] - df['close'].shift(1))
        tr3 = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(span=period, adjust=False).mean() / atr
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(span=period, adjust=False).mean() / atr
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.ewm(span=period, adjust=False).mean()
        
        return adx
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR."""
        tr1 = df['high'] - df['low']
        tr2 = abs(df['high'] - df['close'].shift(1))
        tr3 = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy using Bollinger Bands and z-scores.
    
    Only trades when Hurst exponent indicates mean-reverting behavior.
    """
    
    def __init__(self, lookback: int = 20,
                 entry_zscore: float = 2.0,
                 exit_zscore: float = 0.5,
                 hurst_threshold: float = 0.4,
                 **kwargs):
        """
        Initialize mean reversion strategy.
        
        Args:
            lookback: Lookback period for mean/variance
            entry_zscore: Z-score entry threshold
            exit_zscore: Z-score exit threshold
            hurst_threshold: Hurst exponent threshold for mean reversion
        """
        super().__init__("mean_reversion", **kwargs)
        self.lookback = lookback
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.hurst_threshold = hurst_threshold
    
    def generate_signal(self, data: pd.DataFrame, symbol: str,
                        **kwargs) -> Optional[Signal]:
        """
        Generate mean reversion signal.
        
        Args:
            data: Price data DataFrame
            symbol: Trading symbol
        
        Returns:
            Signal or None
        """
        if len(data) < self.lookback * 2:
            return None
        
        # Check Hurst exponent
        hurst = hurst_exponent(data['close'].iloc[-self.lookback*4:])
        if hurst > self.hurst_threshold:
            return None  # Not mean-reverting
        
        # Calculate z-score
        sma = data['close'].rolling(window=self.lookback).mean()
        std = data['close'].rolling(window=self.lookback).std()
        zscore = (data['close'].iloc[-1] - sma.iloc[-1]) / std.iloc[-1]
        
        # Check for existing position
        has_position = kwargs.get('has_position', False)
        position_side = kwargs.get('position_side', None)
        
        if has_position:
            # Check exit
            if position_side == 'long' and zscore >= -self.exit_zscore:
                return Signal(
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    signal_type=SignalType.EXIT,
                    confidence=1.0,
                    expected_return=0,
                    half_life_seconds=3600,
                    strategy_id=self.strategy_id,
                    metadata={'exit_reason': 'zscore_exit', 'zscore': zscore}
                )
            elif position_side == 'short' and zscore <= self.exit_zscore:
                return Signal(
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    signal_type=SignalType.EXIT,
                    confidence=1.0,
                    expected_return=0,
                    half_life_seconds=3600,
                    strategy_id=self.strategy_id,
                    metadata={'exit_reason': 'zscore_exit', 'zscore': zscore}
                )
            return None
        
        # Entry signals
        if zscore < -self.entry_zscore:
            signal_type = SignalType.BUY
            confidence = min(1.0, abs(zscore) / 3)
        elif zscore > self.entry_zscore:
            signal_type = SignalType.SELL
            confidence = min(1.0, abs(zscore) / 3)
        else:
            return None
        
        if confidence < self.confidence_threshold:
            return None
        
        # Calculate stops
        atr = self._calculate_atr(data).iloc[-1]
        if signal_type == SignalType.BUY:
            stop = data['close'].iloc[-1] - 1.5 * atr
            target = sma.iloc[-1]  # Target the mean
        else:
            stop = data['close'].iloc[-1] + 1.5 * atr
            target = sma.iloc[-1]
        
        return Signal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            signal_type=signal_type,
            confidence=confidence,
            expected_return=2.0,
            half_life_seconds=43200,  # 12 hours
            strategy_id=self.strategy_id,
            metadata={
                'zscore': zscore,
                'hurst': hurst,
                'mean': sma.iloc[-1]
            },
            suggested_stop=stop,
            suggested_target=target
        )
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR."""
        tr1 = df['high'] - df['low']
        tr2 = abs(df['high'] - df['close'].shift(1))
        tr3 = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()


class StatisticalArbitrageStrategy(BaseStrategy):
    """
    Statistical arbitrage using cointegrated pairs.
    
    Trades mean reversion of cointegrated spreads.
    """
    
    def __init__(self, lookback: int = 60,
                 entry_zscore: float = 2.0,
                 coint_pvalue: float = 0.05,
                 **kwargs):
        """
        Initialize stat arb strategy.
        
        Args:
            lookback: Lookback for cointegration test
            entry_zscore: Spread z-score entry threshold
            coint_pvalue: Cointegration test p-value threshold
        """
        super().__init__("stat_arb", **kwargs)
        self.lookback = lookback
        self.entry_zscore = entry_zscore
        self.coint_pvalue = coint_pvalue
        self.hedge_ratios = {}
    
    def generate_signal(self, data: pd.DataFrame, symbol: str,
                        **kwargs) -> Optional[Signal]:
        """
        Generate statistical arbitrage signal.
        
        Args:
            data: Price data DataFrame (for primary symbol)
            symbol: Primary symbol
            **kwargs: Must include 'pair_data' for the paired symbol
        
        Returns:
            Signal or None
        """
        pair_data = kwargs.get('pair_data')
        pair_symbol = kwargs.get('pair_symbol')
        
        if pair_data is None or pair_symbol is None:
            return None
        
        if len(data) < self.lookback or len(pair_data) < self.lookback:
            return None
        
        # Get aligned data
        aligned_data = pd.concat([
            data['close'].rename(symbol),
            pair_data['close'].rename(pair_symbol)
        ], axis=1).dropna().tail(self.lookback)
        
        if len(aligned_data) < self.lookback:
            return None
        
        # Test cointegration
        try:
            score, pvalue = cointegration_test(
                aligned_data[symbol],
                aligned_data[pair_symbol]
            )
        except:
            return None
        
        if pvalue > self.coint_pvalue:
            return None  # Not cointegrated
        
        # Calculate hedge ratio (OLS)
        X = aligned_data[pair_symbol]
        y = aligned_data[symbol]
        hedge_ratio = np.cov(y, X)[0, 1] / np.var(X)
        
        # Calculate spread
        spread = y - hedge_ratio * X
        
        # Z-score of spread
        spread_mean = spread.mean()
        spread_std = spread.std()
        zscore = (spread.iloc[-1] - spread_mean) / spread_std
        
        # Generate signal
        if abs(zscore) < self.entry_zscore:
            return None
        
        if zscore < -self.entry_zscore:
            signal_type = SignalType.BUY
            confidence = min(1.0, abs(zscore) / 3)
        else:
            signal_type = SignalType.SELL
            confidence = min(1.0, abs(zscore) / 3)
        
        if confidence < self.confidence_threshold:
            return None
        
        return Signal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            signal_type=signal_type,
            confidence=confidence,
            expected_return=1.5,
            half_life_seconds=86400,
            strategy_id=self.strategy_id,
            metadata={
                'pair_symbol': pair_symbol,
                'hedge_ratio': hedge_ratio,
                'spread_zscore': zscore,
                'coint_pvalue': pvalue
            }
        )


class VolatilityStrategy(BaseStrategy):
    """
    Volatility trading strategy.
    
    Trades volatility mean reversion and volatility regime changes.
    """
    
    def __init__(self, vol_lookback: int = 20,
                 vol_percentile_threshold: float = 80,
                 **kwargs):
        """
        Initialize volatility strategy.
        
        Args:
            vol_lookback: Volatility lookback period
            vol_percentile_threshold: Volatility percentile threshold
        """
        super().__init__("volatility", **kwargs)
        self.vol_lookback = vol_lookback
        self.vol_percentile_threshold = vol_percentile_threshold
    
    def generate_signal(self, data: pd.DataFrame, symbol: str,
                        **kwargs) -> Optional[Signal]:
        """
        Generate volatility signal.
        
        Args:
            data: Price data DataFrame
            symbol: Trading symbol
        
        Returns:
            Signal or None
        """
        if len(data) < self.vol_lookback * 3:
            return None
        
        # Calculate realized volatility
        returns = data['close'].pct_change().dropna()
        current_vol = returns.tail(self.vol_lookback).std() * np.sqrt(252)
        
        # Calculate historical volatility percentiles
        rolling_vol = returns.rolling(window=self.vol_lookback).std() * np.sqrt(252)
        vol_percentile = stats.percentileofscore(
            rolling_vol.dropna().values,
            current_vol
        )
        
        # Volatility regime detection
        if vol_percentile > self.vol_percentile_threshold:
            # High volatility - expect mean reversion
            signal_type = SignalType.SELL  # Sell straddle or reduce exposure
            confidence = (vol_percentile - self.vol_percentile_threshold) / 20
            expected_return = 1.0
        elif vol_percentile < 20:
            # Low volatility - expect expansion
            signal_type = SignalType.BUY  # Buy options or increase exposure
            confidence = (20 - vol_percentile) / 20
            expected_return = 1.0
        else:
            return None
        
        if confidence < self.confidence_threshold:
            return None
        
        return Signal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            signal_type=signal_type,
            confidence=confidence,
            expected_return=expected_return,
            half_life_seconds=604800,  # 1 week
            strategy_id=self.strategy_id,
            metadata={
                'current_vol': current_vol,
                'vol_percentile': vol_percentile,
                'regime': 'high' if vol_percentile > 50 else 'low'
            }
        )


class RegimeDetectionStrategy(BaseStrategy):
    """
    Regime detection strategy using volatility and correlation regimes.
    
    Adjusts exposure based on detected market regime.
    """
    
    def __init__(self, vol_window: int = 20,
                 correlation_window: int = 60,
                 **kwargs):
        """
        Initialize regime detection strategy.
        
        Args:
            vol_window: Volatility calculation window
            correlation_window: Correlation calculation window
        """
        super().__init__("regime_detection", **kwargs)
        self.vol_window = vol_window
        self.correlation_window = correlation_window
        self.current_regime = 'normal'
    
    def generate_signal(self, data: pd.DataFrame, symbol: str,
                        **kwargs) -> Optional[Signal]:
        """
        Generate regime-based signal.
        
        Args:
            data: Price data DataFrame
            symbol: Trading symbol
            **kwargs: May include 'market_data' for correlation calculation
        
        Returns:
            Signal or None
        """
        if len(data) < self.correlation_window:
            return None
        
        # Calculate volatility regime
        returns = data['close'].pct_change().dropna()
        current_vol = returns.tail(self.vol_window).std() * np.sqrt(252)
        historical_vol = returns.tail(252).std() * np.sqrt(252) if len(returns) >= 252 else returns.std() * np.sqrt(252)
        
        vol_ratio = current_vol / historical_vol if historical_vol > 0 else 1.0
        
        # Determine regime
        if vol_ratio > 1.5:
            regime = 'crisis'
            confidence = min(1.0, (vol_ratio - 1.5) / 1.0 + 0.7)
            signal_type = SignalType.SELL  # Reduce exposure
            expected_return = 0.5
        elif vol_ratio > 1.2:
            regime = 'stressed'
            confidence = min(1.0, (vol_ratio - 1.2) / 0.3 + 0.5)
            signal_type = SignalType.SELL
            expected_return = 0.8
        elif vol_ratio < 0.7:
            regime = 'low_vol'
            confidence = min(1.0, (0.7 - vol_ratio) / 0.3 + 0.5)
            signal_type = SignalType.BUY  # Increase exposure
            expected_return = 1.2
        else:
            regime = 'normal'
            confidence = 0.0
            signal_type = SignalType.HOLD
            expected_return = 0
        
        if confidence < self.confidence_threshold:
            return None
        
        self.current_regime = regime
        
        return Signal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            signal_type=signal_type,
            confidence=confidence,
            expected_return=expected_return,
            half_life_seconds=172800,  # 2 days
            strategy_id=self.strategy_id,
            metadata={
                'regime': regime,
                'vol_ratio': vol_ratio,
                'current_vol': current_vol,
                'historical_vol': historical_vol
            }
        )
