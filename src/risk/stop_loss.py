"""
Stop loss management and exit architecture.
"""

import numpy as np
import pandas as pd
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime

from ..common.types import Position, MarketData
from ..common.utils import compute_atr


class StopType(Enum):
    """Types of stop losses."""
    HARD = "hard"  # Static price level
    TRAILING = "trailing"  # Trailing stop
    ATR = "atr"  # ATR-based stop
    VOLATILITY = "volatility"  # Volatility-based stop
    TIME = "time"  # Time-based exit
    PROFIT_TARGET = "profit_target"  # Profit target


@dataclass
class StopLevel:
    """Stop level configuration."""
    stop_type: StopType
    price: float
    activation_price: Optional[float] = None  # For trailing stops
    atr_multiplier: Optional[float] = None
    time_limit: Optional[datetime] = None


class StopLossManager:
    """
    Manages stop losses and position exits.
    
    Supports:
    - Hard stops (static invalidation levels)
    - Trailing stops (ATR/chandelier/parabolic SAR)
    - Volatility stops
    - Time-based exits
    - Profit targets
    """
    
    def __init__(self):
        """Initialize stop loss manager."""
        self.stops: Dict[str, StopLevel] = {}
        self.position_highs: Dict[str, float] = {}
        self.position_lows: Dict[str, float] = {}
        self.entry_times: Dict[str, datetime] = {}
    
    def set_stop(self, position_id: str, stop_type: StopType,
                 price: float, **kwargs) -> None:
        """
        Set a stop for a position.
        
        Args:
            position_id: Position identifier
            stop_type: Type of stop
            price: Stop price level
            **kwargs: Additional parameters
        """
        self.stops[position_id] = StopLevel(
            stop_type=stop_type,
            price=price,
            activation_price=kwargs.get('activation_price'),
            atr_multiplier=kwargs.get('atr_multiplier'),
            time_limit=kwargs.get('time_limit')
        )
    
    def update_trailing_stop(self, position_id: str, 
                            current_price: float,
                            position_side: str,
                            atr_value: Optional[float] = None) -> Optional[float]:
        """
        Update trailing stop based on price movement.
        
        Args:
            position_id: Position identifier
            current_price: Current market price
            position_side: 'long' or 'short'
            atr_value: Current ATR value (for ATR-based trailing)
        
        Returns:
            Updated stop price or None
        """
        if position_id not in self.stops:
            return None
        
        stop = self.stops[position_id]
        
        # Update position extremes
        if position_id not in self.position_highs:
            self.position_highs[position_id] = current_price
            self.position_lows[position_id] = current_price
        
        self.position_highs[position_id] = max(
            self.position_highs[position_id], current_price
        )
        self.position_lows[position_id] = min(
            self.position_lows[position_id], current_price
        )
        
        # Update trailing stop
        if stop.stop_type == StopType.TRAILING:
            if position_side == 'long':
                # For longs, trail below highs
                new_stop = self.position_highs[position_id] - (
                    self.position_highs[position_id] - stop.activation_price
                ) if stop.activation_price else current_price * 0.95
                stop.price = max(stop.price, new_stop)
            else:
                # For shorts, trail above lows
                new_stop = self.position_lows[position_id] + (
                    stop.activation_price - self.position_lows[position_id]
                ) if stop.activation_price else current_price * 1.05
                stop.price = min(stop.price, new_stop)
        
        elif stop.stop_type == StopType.ATR and atr_value is not None:
            multiplier = stop.atr_multiplier or 2.0
            if position_side == 'long':
                new_stop = current_price - atr_value * multiplier
                stop.price = max(stop.price, new_stop)
            else:
                new_stop = current_price + atr_value * multiplier
                stop.price = min(stop.price, new_stop)
        
        return stop.price
    
    def check_stop(self, position_id: str, current_price: float,
                   position_side: str) -> Tuple[bool, str]:
        """
        Check if stop has been triggered.
        
        Args:
            position_id: Position identifier
            current_price: Current market price
            position_side: 'long' or 'short'
        
        Returns:
            Tuple of (triggered, reason)
        """
        if position_id not in self.stops:
            return False, "No stop set"
        
        stop = self.stops[position_id]
        
        # Check time-based exit
        if stop.time_limit and datetime.utcnow() >= stop.time_limit:
            return True, "Time limit reached"
        
        # Check price-based stops
        if position_side == 'long':
            if current_price <= stop.price:
                return True, f"Stop triggered at {stop.price}"
        else:  # short
            if current_price >= stop.price:
                return True, f"Stop triggered at {stop.price}"
        
        return False, "Stop not triggered"
    
    def check_volatility_stop(self, position_id: str,
                              realized_vol: float,
                              forecast_vol: float,
                              threshold: float = 1.5) -> bool:
        """
        Check if volatility stop should trigger.
        
        Args:
            position_id: Position identifier
            realized_vol: Realized volatility
            forecast_vol: Forecast volatility
            threshold: Volatility breach threshold
        
        Returns:
            True if volatility stop triggered
        """
        if forecast_vol <= 0:
            return False
        
        vol_ratio = realized_vol / forecast_vol
        
        if vol_ratio > threshold:
            return True
        
        return False
    
    def remove_stop(self, position_id: str) -> None:
        """
        Remove stop for a position.
        
        Args:
            position_id: Position identifier
        """
        if position_id in self.stops:
            del self.stops[position_id]
        if position_id in self.position_highs:
            del self.position_highs[position_id]
        if position_id in self.position_lows:
            del self.position_lows[position_id]
        if position_id in self.entry_times:
            del self.entry_times[position_id]
    
    def calculate_chandelier_exit(self, high: pd.Series, low: pd.Series,
                                  close: pd.Series, period: int = 22,
                                  atr_multiplier: float = 3.0,
                                  position_side: str = 'long') -> float:
        """
        Calculate Chandelier Exit stop.
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: Lookback period
            atr_multiplier: ATR multiplier
            position_side: 'long' or 'short'
        
        Returns:
            Chandelier exit price
        """
        atr = compute_atr(high, low, close, period)
        current_atr = atr.iloc[-1]
        
        if position_side == 'long':
            highest_high = high.tail(period).max()
            return highest_high - current_atr * atr_multiplier
        else:
            lowest_low = low.tail(period).min()
            return lowest_low + current_atr * atr_multiplier
    
    def calculate_parabolic_sar(self, high: pd.Series, low: pd.Series,
                                af_start: float = 0.02,
                                af_increment: float = 0.02,
                                af_max: float = 0.20) -> pd.Series:
        """
        Calculate Parabolic SAR.
        
        Args:
            high: High prices
            low: Low prices
            af_start: Starting acceleration factor
            af_increment: Acceleration factor increment
            af_max: Maximum acceleration factor
        
        Returns:
            Parabolic SAR series
        """
        n = len(high)
        sar = pd.Series(index=high.index, dtype=float)
        
        # Initialize
        trend = 1  # 1 for uptrend, -1 for downtrend
        af = af_start
        ep = high.iloc[0]  # Extreme point
        sar.iloc[0] = low.iloc[0]
        
        for i in range(1, n):
            # Update SAR
            sar.iloc[i] = sar.iloc[i-1] + af * (ep - sar.iloc[i-1])
            
            # Check for trend reversal
            if trend == 1:  # Uptrend
                if low.iloc[i] < sar.iloc[i]:  # Reverse to downtrend
                    trend = -1
                    sar.iloc[i] = ep
                    ep = low.iloc[i]
                    af = af_start
                else:  # Continue uptrend
                    if high.iloc[i] > ep:
                        ep = high.iloc[i]
                        af = min(af + af_increment, af_max)
                    sar.iloc[i] = min(sar.iloc[i], low.iloc[i-1], low.iloc[i-2] if i >= 2 else low.iloc[i-1])
            else:  # Downtrend
                if high.iloc[i] > sar.iloc[i]:  # Reverse to uptrend
                    trend = 1
                    sar.iloc[i] = ep
                    ep = high.iloc[i]
                    af = af_start
                else:  # Continue downtrend
                    if low.iloc[i] < ep:
                        ep = low.iloc[i]
                        af = min(af + af_increment, af_max)
                    sar.iloc[i] = max(sar.iloc[i], high.iloc[i-1], high.iloc[i-2] if i >= 2 else high.iloc[i-1])
        
        return sar
    
    def get_stop_summary(self, position_id: str) -> Dict:
        """
        Get summary of stop for a position.
        
        Args:
            position_id: Position identifier
        
        Returns:
            Stop summary dictionary
        """
        if position_id not in self.stops:
            return {'has_stop': False}
        
        stop = self.stops[position_id]
        
        return {
            'has_stop': True,
            'stop_type': stop.stop_type.value,
            'stop_price': stop.price,
            'activation_price': stop.activation_price,
            'atr_multiplier': stop.atr_multiplier,
            'time_limit': stop.time_limit,
            'position_high': self.position_highs.get(position_id),
            'position_low': self.position_lows.get(position_id)
        }
