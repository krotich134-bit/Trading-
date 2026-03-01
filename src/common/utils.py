"""
Utility functions for the AI Trading System.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import re


def timestamp_utc() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


def validate_symbol(symbol: str) -> bool:
    """Validate symbol format."""
    if not symbol or not isinstance(symbol, str):
        return False
    # Allow alphanumeric, dots, hyphens
    pattern = r'^[A-Z0-9.-]+$'
    return bool(re.match(pattern, symbol.upper()))


def compute_returns(prices: pd.Series, method: str = "log") -> pd.Series:
    """
    Compute returns from price series.
    
    Args:
        prices: Price series
        method: "log" or "simple"
    
    Returns:
        Returns series
    """
    if method == "log":
        return np.log(prices / prices.shift(1)).dropna()
    else:
        return prices.pct_change().dropna()


def annualize_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Annualize volatility from returns.
    
    Args:
        returns: Return series
        periods_per_year: Trading periods per year
    
    Returns:
        Annualized volatility
    """
    return returns.std() * np.sqrt(periods_per_year)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, 
                 periods_per_year: int = 252) -> float:
    """
    Compute Sharpe ratio.
    
    Args:
        returns: Return series
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading periods per year
    
    Returns:
        Sharpe ratio
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    if excess_returns.std() == 0:
        return 0.0
    return excess_returns.mean() / excess_returns.std() * np.sqrt(periods_per_year)


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0,
                  periods_per_year: int = 252) -> float:
    """
    Compute Sortino ratio (downside deviation only).
    
    Args:
        returns: Return series
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading periods per year
    
    Returns:
        Sortino ratio
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    downside_returns = excess_returns[excess_returns < 0]
    
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return 0.0
    
    downside_std = downside_returns.std() * np.sqrt(periods_per_year)
    return excess_returns.mean() * periods_per_year / downside_std


def max_drawdown(equity_curve: pd.Series) -> Tuple[float, datetime, datetime]:
    """
    Compute maximum drawdown with timing.
    
    Args:
        equity_curve: Equity curve series
    
    Returns:
        Tuple of (max_drawdown, peak_date, trough_date)
    """
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    
    max_dd = drawdown.min()
    trough_idx = drawdown.idxmin()
    peak_idx = equity_curve.loc[:trough_idx].idxmax()
    
    return max_dd, peak_idx, trough_idx


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Compute Calmar ratio (return / max drawdown).
    
    Args:
        returns: Return series
        periods_per_year: Trading periods per year
    
    Returns:
        Calmar ratio
    """
    equity_curve = (1 + returns).cumprod()
    max_dd, _, _ = max_drawdown(equity_curve)
    
    if max_dd == 0:
        return 0.0
    
    annual_return = returns.mean() * periods_per_year
    return annual_return / abs(max_dd)


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, 
                period: int = 14) -> pd.Series:
    """
    Compute Average True Range.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ATR period
    
    Returns:
        ATR series
    """
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    
    return atr


def rolling_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """
    Compute rolling z-score.
    
    Args:
        series: Input series
        window: Rolling window
    
    Returns:
        Z-score series
    """
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    return (series - rolling_mean) / rolling_std


def robust_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """
    Compute robust z-score using median and MAD.
    
    Args:
        series: Input series
        window: Rolling window
    
    Returns:
        Robust z-score series
    """
    rolling_median = series.rolling(window=window).median()
    rolling_mad = series.rolling(window=window).apply(
        lambda x: np.median(np.abs(x - np.median(x)))
    )
    # MAD to std conversion: 1.4826
    return (series - rolling_median) / (rolling_mad * 1.4826 + 1e-10)


def cointegration_test(x: pd.Series, y: pd.Series) -> Tuple[float, float]:
    """
    Simple Engle-Granger cointegration test.
    
    Args:
        x: First price series
        y: Second price series
    
    Returns:
        Tuple of (test_statistic, p_value)
    """
    from statsmodels.tsa.stattools import coint
    
    score, p_value, _ = coint(x, y)
    return score, p_value


def hurst_exponent(prices: pd.Series, max_lag: int = 100) -> float:
    """
    Compute Hurst exponent to test for mean reversion/trend.
    
    H < 0.5: mean reverting
    H = 0.5: random walk
    H > 0.5: trending
    
    Args:
        prices: Price series
        max_lag: Maximum lag for computation
    
    Returns:
        Hurst exponent
    """
    lags = range(2, min(max_lag, len(prices) // 4))
    tau = [np.std(np.subtract(prices[lag:], prices[:-lag])) for lag in lags]
    
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return poly[0]


def compute_correlation_matrix(returns_dict: dict) -> pd.DataFrame:
    """
    Compute correlation matrix from returns dictionary.
    
    Args:
        returns_dict: Dictionary of symbol -> returns series
    
    Returns:
        Correlation matrix DataFrame
    """
    df = pd.DataFrame(returns_dict)
    return df.corr()


def portfolio_volatility(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """
    Compute portfolio volatility.
    
    Args:
        weights: Portfolio weights
        cov_matrix: Covariance matrix
    
    Returns:
        Portfolio volatility
    """
    return np.sqrt(weights.T @ cov_matrix @ weights)


def effective_number_of_bets(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """
    Compute effective number of bets (diversification measure).
    
    Args:
        weights: Portfolio weights
        cov_matrix: Covariance matrix
    
    Returns:
        Effective number of bets
    """
    # Compute portfolio variance
    port_var = weights.T @ cov_matrix @ weights
    
    # Compute marginal contributions
    marginal_contrib = cov_matrix @ weights
    
    # Compute percentage risk contributions
    risk_contrib = weights * marginal_contrib / port_var
    
    # Effective number of bets
    return 1.0 / np.sum(risk_contrib ** 2)


def winsorize(series: pd.Series, limits: Tuple[float, float] = (0.05, 0.05)) -> pd.Series:
    """
    Winsorize series at given percentiles.
    
    Args:
        series: Input series
        limits: Lower and upper percentile limits
    
    Returns:
        Winsorized series
    """
    lower = series.quantile(limits[0])
    upper = series.quantile(1 - limits[1])
    return series.clip(lower, upper)
