"""
Position sizing algorithms for the AI Trading System.

Implements various position sizing frameworks including:
- Fixed Fractional sizing
- Kelly Criterion (constrained)
- Volatility Targeting
- CPPI (Constant Proportion Portfolio Insurance)
- ATR-based sizing
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from datetime import datetime

from ..common.types import Signal, Position, PortfolioState
from ..common.utils import compute_atr


@dataclass
class SizingResult:
    """Result of position sizing calculation."""
    quantity: float
    dollar_risk: float
    position_value: float
    leverage: float
    risk_fraction: float
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PositionSizer(ABC):
    """Abstract base class for position sizing algorithms."""
    
    def __init__(self, max_risk_per_trade: float = 0.02):
        """
        Initialize position sizer.
        
        Args:
            max_risk_per_trade: Maximum risk per trade as fraction of equity
        """
        self.max_risk_per_trade = max_risk_per_trade
    
    @abstractmethod
    def calculate_size(self, signal: Signal, portfolio: PortfolioState,
                       current_price: float, stop_price: float,
                       **kwargs) -> SizingResult:
        """
        Calculate position size.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            current_price: Current market price
            stop_price: Stop loss price
            **kwargs: Additional parameters
        
        Returns:
            SizingResult with position details
        """
        pass
    
    def _validate_inputs(self, portfolio: PortfolioState, 
                         current_price: float, stop_price: float) -> bool:
        """Validate sizing inputs."""
        if portfolio.equity <= 0:
            return False
        if current_price <= 0 or stop_price <= 0:
            return False
        if current_price == stop_price:
            return False
        return True


class FixedFractionalSizer(PositionSizer):
    """
    Fixed fractional position sizing.
    
    Risk = f * Equity where f is the risk fraction per trade.
    Position size = Risk / (Entry - Stop)
    """
    
    def __init__(self, risk_fraction: float = 0.01):
        """
        Initialize fixed fractional sizer.
        
        Args:
            risk_fraction: Risk fraction per trade (default 1%)
        """
        super().__init__(max_risk_per_trade=risk_fraction)
        self.risk_fraction = risk_fraction
    
    def calculate_size(self, signal: Signal, portfolio: PortfolioState,
                       current_price: float, stop_price: float,
                       **kwargs) -> SizingResult:
        """
        Calculate position size using fixed fractional method.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            current_price: Current market price
            stop_price: Stop loss price
        
        Returns:
            SizingResult
        """
        if not self._validate_inputs(portfolio, current_price, stop_price):
            return SizingResult(0, 0, 0, 0, 0)
        
        # Calculate risk amount
        dollar_risk = portfolio.equity * self.risk_fraction
        
        # Calculate risk per unit
        risk_per_unit = abs(current_price - stop_price)
        
        # Calculate position size
        if risk_per_unit > 0:
            quantity = dollar_risk / risk_per_unit
        else:
            quantity = 0
        
        position_value = quantity * current_price
        leverage = position_value / portfolio.equity if portfolio.equity > 0 else 0
        
        return SizingResult(
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
            leverage=leverage,
            risk_fraction=self.risk_fraction,
            metadata={
                'method': 'fixed_fractional',
                'risk_per_unit': risk_per_unit
            }
        )


class KellySizer(PositionSizer):
    """
    Kelly Criterion position sizing with constraints.
    
    f* = (p*b - q) / b
    where p = win probability, b = win/loss ratio, q = 1-p
    
    Uses Half-Kelly or Quarter-Kelly for safety.
    """
    
    def __init__(self, win_probability: float = 0.5,
                 win_loss_ratio: float = 2.0,
                 kelly_fraction: float = 0.25,  # Quarter-Kelly default
                 max_risk_per_trade: float = 0.02):
        """
        Initialize Kelly sizer.
        
        Args:
            win_probability: Estimated win probability
            win_loss_ratio: Average win / average loss ratio
            kelly_fraction: Fraction of Kelly to use (0.25 = Quarter-Kelly)
            max_risk_per_trade: Maximum risk cap
        """
        super().__init__(max_risk_per_trade)
        self.win_probability = win_probability
        self.win_loss_ratio = win_loss_ratio
        self.kelly_fraction = kelly_fraction
    
    def calculate_kelly_fraction(self) -> float:
        """
        Calculate Kelly fraction.
        
        Returns:
            Kelly fraction (constrained)
        """
        q = 1 - self.win_probability
        
        if self.win_loss_ratio <= 0:
            return 0.0
        
        # Full Kelly
        kelly = (self.win_probability * self.win_loss_ratio - q) / self.win_loss_ratio
        
        # Apply fraction (Half-Kelly, Quarter-Kelly, etc.)
        kelly = kelly * self.kelly_fraction
        
        # Ensure non-negative and cap at max risk
        kelly = max(0, min(kelly, self.max_risk_per_trade))
        
        return kelly
    
    def calculate_size(self, signal: Signal, portfolio: PortfolioState,
                       current_price: float, stop_price: float,
                       **kwargs) -> SizingResult:
        """
        Calculate position size using Kelly Criterion.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            current_price: Current market price
            stop_price: Stop loss price
        
        Returns:
            SizingResult
        """
        if not self._validate_inputs(portfolio, current_price, stop_price):
            return SizingResult(0, 0, 0, 0, 0)
        
        # Calculate Kelly fraction
        kelly_fraction = self.calculate_kelly_fraction()
        
        # Calculate risk amount
        dollar_risk = portfolio.equity * kelly_fraction
        
        # Calculate risk per unit
        risk_per_unit = abs(current_price - stop_price)
        
        # Calculate position size
        if risk_per_unit > 0:
            quantity = dollar_risk / risk_per_unit
        else:
            quantity = 0
        
        position_value = quantity * current_price
        leverage = position_value / portfolio.equity if portfolio.equity > 0 else 0
        
        return SizingResult(
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
            leverage=leverage,
            risk_fraction=kelly_fraction,
            metadata={
                'method': 'kelly_criterion',
                'full_kelly': kelly_fraction / self.kelly_fraction if self.kelly_fraction > 0 else 0,
                'kelly_fraction_used': self.kelly_fraction,
                'win_probability': self.win_probability,
                'win_loss_ratio': self.win_loss_ratio,
                'risk_per_unit': risk_per_unit
            }
        )
    
    def update_statistics(self, trades: List) -> None:
        """
        Update Kelly parameters from historical trades.
        
        Args:
            trades: List of completed trades
        """
        if len(trades) < 10:
            return
        
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return
        
        self.win_probability = len(wins) / len(trades)
        
        avg_win = np.mean([t.net_pnl for t in wins])
        avg_loss = abs(np.mean([t.net_pnl for t in losses]))
        
        if avg_loss > 0:
            self.win_loss_ratio = avg_win / avg_loss


class VolatilityTargetSizer(PositionSizer):
    """
    Volatility-targeted position sizing.
    
    Adjusts position size to target a specific portfolio volatility.
    w_t = w_base * (sigma_target / sigma_realized)
    """
    
    def __init__(self, target_volatility: float = 0.10,
                 lookback_periods: int = 60,
                 max_leverage: float = 2.0,
                 min_leverage: float = 0.1):
        """
        Initialize volatility target sizer.
        
        Args:
            target_volatility: Target annualized volatility (default 10%)
            lookback_periods: Periods for volatility calculation
            max_leverage: Maximum leverage cap
            min_leverage: Minimum leverage floor
        """
        super().__init__()
        self.target_volatility = target_volatility
        self.lookback_periods = lookback_periods
        self.max_leverage = max_leverage
        self.min_leverage = min_leverage
    
    def calculate_size(self, signal: Signal, portfolio: PortfolioState,
                       current_price: float, stop_price: float,
                       **kwargs) -> SizingResult:
        """
        Calculate position size based on volatility targeting.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            current_price: Current market price
            stop_price: Stop loss price
            **kwargs: Must include 'price_history' for volatility calculation
        
        Returns:
            SizingResult
        """
        if not self._validate_inputs(portfolio, current_price, stop_price):
            return SizingResult(0, 0, 0, 0, 0)
        
        price_history = kwargs.get('price_history')
        if price_history is None or len(price_history) < self.lookback_periods:
            # Fall back to fixed fractional if no history
            fallback = FixedFractionalSizer(0.01)
            return fallback.calculate_size(signal, portfolio, current_price, stop_price)
        
        # Calculate realized volatility
        returns = np.log(price_history / price_history.shift(1)).dropna()
        realized_vol = returns.std() * np.sqrt(252)  # Annualized
        
        if realized_vol <= 0:
            realized_vol = self.target_volatility
        
        # Calculate volatility adjustment
        vol_adjustment = self.target_volatility / realized_vol
        vol_adjustment = np.clip(vol_adjustment, self.min_leverage, self.max_leverage)
        
        # Calculate base position size (1% risk)
        base_risk = portfolio.equity * 0.01
        risk_per_unit = abs(current_price - stop_price)
        
        if risk_per_unit > 0:
            base_quantity = base_risk / risk_per_unit
            quantity = base_quantity * vol_adjustment
        else:
            quantity = 0
        
        position_value = quantity * current_price
        leverage = position_value / portfolio.equity if portfolio.equity > 0 else 0
        dollar_risk = quantity * risk_per_unit
        risk_fraction = dollar_risk / portfolio.equity if portfolio.equity > 0 else 0
        
        return SizingResult(
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
            leverage=leverage,
            risk_fraction=risk_fraction,
            metadata={
                'method': 'volatility_target',
                'realized_volatility': realized_vol,
                'target_volatility': self.target_volatility,
                'vol_adjustment': vol_adjustment,
                'risk_per_unit': risk_per_unit
            }
        )


class CPPISizer(PositionSizer):
    """
    Constant Proportion Portfolio Insurance position sizing.
    
    Risky Allocation = m * (V - F)
    where V = portfolio value, F = floor value, m = multiplier
    """
    
    def __init__(self, floor_fraction: float = 0.90,
                 multiplier: float = 3.0,
                 max_risk_per_trade: float = 0.02):
        """
        Initialize CPPI sizer.
        
        Args:
            floor_fraction: Floor as fraction of peak equity
            multiplier: CPPI multiplier
            max_risk_per_trade: Maximum risk per trade
        """
        super().__init__(max_risk_per_trade)
        self.floor_fraction = floor_fraction
        self.multiplier = multiplier
        self.peak_equity = 0.0
    
    def calculate_size(self, signal: Signal, portfolio: PortfolioState,
                       current_price: float, stop_price: float,
                       **kwargs) -> SizingResult:
        """
        Calculate position size using CPPI.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            current_price: Current market price
            stop_price: Stop loss price
        
        Returns:
            SizingResult
        """
        if not self._validate_inputs(portfolio, current_price, stop_price):
            return SizingResult(0, 0, 0, 0, 0)
        
        # Update peak equity
        self.peak_equity = max(self.peak_equity, portfolio.equity)
        
        # Calculate floor
        floor = self.peak_equity * self.floor_fraction
        
        # Calculate cushion
        cushion = portfolio.equity - floor
        
        if cushion <= 0:
            # Below floor, no new positions
            return SizingResult(0, 0, 0, 0, 0)
        
        # Calculate risky allocation
        risky_allocation = self.multiplier * cushion
        
        # Cap at max risk per trade
        max_risk = portfolio.equity * self.max_risk_per_trade
        dollar_risk = min(risky_allocation, max_risk)
        
        # Calculate risk per unit
        risk_per_unit = abs(current_price - stop_price)
        
        # Calculate position size
        if risk_per_unit > 0:
            quantity = dollar_risk / risk_per_unit
        else:
            quantity = 0
        
        position_value = quantity * current_price
        leverage = position_value / portfolio.equity if portfolio.equity > 0 else 0
        risk_fraction = dollar_risk / portfolio.equity if portfolio.equity > 0 else 0
        
        return SizingResult(
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
            leverage=leverage,
            risk_fraction=risk_fraction,
            metadata={
                'method': 'cppi',
                'peak_equity': self.peak_equity,
                'floor': floor,
                'cushion': cushion,
                'multiplier': self.multiplier,
                'risk_per_unit': risk_per_unit
            }
        )


class ATRSizer(PositionSizer):
    """
    ATR-based position sizing.
    
    Position Size = Risk Budget / (ATR * k)
    where k is a multiplier (typically 1-3)
    """
    
    def __init__(self, atr_multiplier: float = 2.0,
                 atr_period: int = 14,
                 risk_fraction: float = 0.01):
        """
        Initialize ATR sizer.
        
        Args:
            atr_multiplier: ATR multiplier for stop distance
            atr_period: Period for ATR calculation
            risk_fraction: Risk fraction per trade
        """
        super().__init__(risk_fraction)
        self.atr_multiplier = atr_multiplier
        self.atr_period = atr_period
        self.risk_fraction = risk_fraction
    
    def calculate_size(self, signal: Signal, portfolio: PortfolioState,
                       current_price: float, stop_price: float,
                       **kwargs) -> SizingResult:
        """
        Calculate position size using ATR.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            current_price: Current market price
            stop_price: Stop loss price
            **kwargs: Must include 'high', 'low', 'close' for ATR calculation
        
        Returns:
            SizingResult
        """
        if not self._validate_inputs(portfolio, current_price, stop_price):
            return SizingResult(0, 0, 0, 0, 0)
        
        high = kwargs.get('high')
        low = kwargs.get('low')
        close = kwargs.get('close')
        
        if high is not None and low is not None and close is not None:
            # Calculate ATR
            atr_series = compute_atr(high, low, close, self.atr_period)
            current_atr = atr_series.iloc[-1]
            
            # Override stop price with ATR-based stop if provided
            if signal.signal_type.value == 'buy':
                atr_stop = current_price - current_atr * self.atr_multiplier
            else:
                atr_stop = current_price + current_atr * self.atr_multiplier
            
            stop_price = atr_stop
        else:
            current_atr = abs(current_price - stop_price) / self.atr_multiplier
        
        # Calculate risk amount
        dollar_risk = portfolio.equity * self.risk_fraction
        
        # Calculate risk per unit
        risk_per_unit = abs(current_price - stop_price)
        
        # Calculate position size
        if risk_per_unit > 0:
            quantity = dollar_risk / risk_per_unit
        else:
            quantity = 0
        
        position_value = quantity * current_price
        leverage = position_value / portfolio.equity if portfolio.equity > 0 else 0
        
        return SizingResult(
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
            leverage=leverage,
            risk_fraction=self.risk_fraction,
            metadata={
                'method': 'atr_based',
                'atr': current_atr,
                'atr_multiplier': self.atr_multiplier,
                'effective_stop': stop_price,
                'risk_per_unit': risk_per_unit
            }
        )
