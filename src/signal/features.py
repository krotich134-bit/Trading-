"""
Feature engineering for trading signals.

Implements technical, statistical, and alternative data features
with strict point-in-time discipline.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from scipy import stats
from sklearn.preprocessing import StandardScaler


class FeatureEngineer:
    """
    Feature engineering with point-in-time discipline.
    
    All features are computed using only past data to prevent lookahead bias.
    """
    
    def __init__(self):
        """Initialize feature engineer."""
        self.feature_scaler = StandardScaler()
        self.feature_names = []
    
    def compute_technical_features(
        self,
        df: pd.DataFrame,
        windows: List[int] = [5, 10, 20, 50]
    ) -> pd.DataFrame:
        """
        Compute technical analysis features.
        
        Args:
            df: DataFrame with OHLCV data
            windows: List of lookback windows
        
        Returns:
            DataFrame with technical features
        """
        features = pd.DataFrame(index=df.index)
        
        # Price-based features
        for window in windows:
            # Moving averages
            features[f'sma_{window}'] = df['close'].rolling(window=window).mean()
            features[f'ema_{window}'] = df['close'].ewm(span=window, adjust=False).mean()
            
            # Distance from moving average
            features[f'dist_sma_{window}'] = (
                df['close'] - features[f'sma_{window}']
            ) / features[f'sma_{window}']
            
            # Volatility
            features[f'volatility_{window}'] = (
                df['close'].rolling(window=window).std() / df['close']
            )
            
            # Returns
            features[f'return_{window}'] = (
                df['close'] / df['close'].shift(window) - 1
            )
        
        # RSI
        for window in [14, 21]:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            features[f'rsi_{window}'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        features['macd'] = ema_12 - ema_26
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()
        features['macd_histogram'] = features['macd'] - features['macd_signal']
        
        # Bollinger Bands
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        features['bb_upper'] = sma_20 + 2 * std_20
        features['bb_lower'] = sma_20 - 2 * std_20
        features['bb_position'] = (df['close'] - features['bb_lower']) / (
            features['bb_upper'] - features['bb_lower']
        )
        features['bb_width'] = (features['bb_upper'] - features['bb_lower']) / sma_20
        
        # Volume features
        if 'volume' in df.columns:
            features['volume_sma_20'] = df['volume'].rolling(window=20).mean()
            features['volume_ratio'] = df['volume'] / features['volume_sma_20']
            
            # On-balance volume
            obv = [0]
            for i in range(1, len(df)):
                if df['close'].iloc[i] > df['close'].iloc[i-1]:
                    obv.append(obv[-1] + df['volume'].iloc[i])
                elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                    obv.append(obv[-1] - df['volume'].iloc[i])
                else:
                    obv.append(obv[-1])
            features['obv'] = obv
        
        # High-low range
        features['hl_range'] = (df['high'] - df['low']) / df['close']
        features['body_size'] = abs(df['close'] - df['open']) / df['close']
        
        return features
    
    def compute_statistical_features(
        self,
        df: pd.DataFrame,
        windows: List[int] = [20, 60]
    ) -> pd.DataFrame:
        """
        Compute statistical features.
        
        Args:
            df: DataFrame with price data
            windows: List of lookback windows
        
        Returns:
            DataFrame with statistical features
        """
        features = pd.DataFrame(index=df.index)
        returns = np.log(df['close'] / df['close'].shift(1))
        
        for window in windows:
            # Skewness and kurtosis
            features[f'skew_{window}'] = returns.rolling(window=window).skew()
            features[f'kurt_{window}'] = returns.rolling(window=window).kurt()
            
            # Autocorrelation
            features[f'autocorr_{window}'] = returns.rolling(window=window).apply(
                lambda x: x.autocorr(lag=1) if len(x) > 1 else 0
            )
            
            # Z-score
            features[f'zscore_{window}'] = (
                (df['close'] - df['close'].rolling(window=window).mean()) /
                df['close'].rolling(window=window).std()
            )
            
            # Min/max position
            features[f'min_pos_{window}'] = (
                (df['close'] - df['close'].rolling(window=window).min()) /
                (df['close'].rolling(window=window).max() - 
                 df['close'].rolling(window=window).min())
            )
        
        return features
    
    def compute_microstructure_features(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute market microstructure features.
        
        Args:
            df: DataFrame with L1/L2 data
        
        Returns:
            DataFrame with microstructure features
        """
        features = pd.DataFrame(index=df.index)
        
        if 'bid' in df.columns and 'ask' in df.columns:
            # Spread
            features['spread'] = df['ask'] - df['bid']
            features['spread_pct'] = features['spread'] / df['close']
            
            # Mid-price
            features['mid'] = (df['ask'] + df['bid']) / 2
            
            # Order book imbalance
            if 'bid_size' in df.columns and 'ask_size' in df.columns:
                features['ob_imbalance'] = (
                    df['bid_size'] - df['ask_size']
                ) / (df['bid_size'] + df['ask_size'])
            
            # Price relative to spread
            features['price_loc'] = (
                df['close'] - df['bid']
            ) / features['spread']
        
        return features
    
    def compute_cross_sectional_features(
        self,
        returns_dict: Dict[str, pd.Series],
        window: int = 20
    ) -> Dict[str, pd.DataFrame]:
        """
        Compute cross-sectional features across multiple assets.
        
        Args:
            returns_dict: Dictionary of symbol -> returns series
            window: Lookback window
        
        Returns:
            Dictionary of symbol -> features DataFrame
        """
        # Align returns
        returns_df = pd.DataFrame(returns_dict).dropna()
        
        results = {}
        for symbol in returns_dict.keys():
            features = pd.DataFrame(index=returns_df.index)
            
            # Cross-sectional rank
            features['cs_rank'] = returns_df[symbol].rolling(window=window).apply(
                lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
            )
            
            # Relative strength
            market_mean = returns_df.mean(axis=1)
            features['rel_strength'] = (
                returns_df[symbol].rolling(window=window).mean() - 
                market_mean.rolling(window=window).mean()
            )
            
            # Beta to market
            features['beta'] = returns_df[symbol].rolling(window=window).cov(
                market_mean
            ) / market_mean.rolling(window=window).var()
            
            results[symbol] = features
        
        return results
    
    def compute_regime_features(
        self,
        df: pd.DataFrame,
        vol_window: int = 20,
        trend_window: int = 50
    ) -> pd.DataFrame:
        """
        Compute regime detection features.
        
        Args:
            df: DataFrame with price data
            vol_window: Volatility lookback
            trend_window: Trend lookback
        
        Returns:
            DataFrame with regime features
        """
        features = pd.DataFrame(index=df.index)
        returns = np.log(df['close'] / df['close'].shift(1))
        
        # Volatility regime
        features['vol_current'] = returns.rolling(window=vol_window).std() * np.sqrt(252)
        features['vol_long'] = returns.rolling(window=252).std() * np.sqrt(252)
        features['vol_ratio'] = features['vol_current'] / features['vol_long']
        features['vol_regime'] = np.where(features['vol_ratio'] > 1.5, 'high',
                                         np.where(features['vol_ratio'] < 0.7, 'low', 'normal'))
        
        # Trend regime
        sma_short = df['close'].rolling(window=20).mean()
        sma_long = df['close'].rolling(window=trend_window).mean()
        features['trend_regime'] = np.where(sma_short > sma_long, 'uptrend', 'downtrend')
        
        # ADX for trend strength
        features['adx'] = self._compute_adx(df, period=14)
        
        return features
    
    def _compute_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Compute Average Directional Index (ADX).
        
        Args:
            df: DataFrame with OHLC data
            period: ADX period
        
        Returns:
            ADX series
        """
        # True range
        tr1 = df['high'] - df['low']
        tr2 = abs(df['high'] - df['close'].shift(1))
        tr3 = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # +DM and -DM
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        plus_dm = pd.Series(plus_dm, index=df.index)
        minus_dm = pd.Series(minus_dm, index=df.index)
        
        # Smooth TR, +DM, -DM
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr
        
        # DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_dm + 1e-10)
        adx = dx.ewm(span=period, adjust=False).mean()
        
        return adx
    
    def prepare_ml_features(
        self,
        df: pd.DataFrame,
        target_horizon: int = 5,
        feature_windows: List[int] = [5, 10, 20, 50]
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare features for machine learning.
        
        Args:
            df: DataFrame with OHLCV data
            target_horizon: Forward return horizon
            feature_windows: Feature lookback windows
        
        Returns:
            Tuple of (features DataFrame, target Series)
        """
        # Compute all feature sets
        tech_features = self.compute_technical_features(df, feature_windows)
        stat_features = self.compute_statistical_features(df, feature_windows)
        micro_features = self.compute_microstructure_features(df)
        regime_features = self.compute_regime_features(df)
        
        # Combine features
        all_features = pd.concat([
            tech_features,
            stat_features,
            micro_features,
            regime_features.select_dtypes(include=[np.number])
        ], axis=1)
        
        # Create target (forward return)
        target = np.log(
            df['close'].shift(-target_horizon) / df['close']
        )
        
        # Drop rows with NaN
        valid_idx = all_features.dropna().index
        all_features = all_features.loc[valid_idx]
        target = target.loc[valid_idx]
        
        self.feature_names = all_features.columns.tolist()
        
        return all_features, target
