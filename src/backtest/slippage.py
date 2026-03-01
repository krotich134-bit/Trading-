"""
Slippage and market impact models for realistic backtesting.
"""

import numpy as np
from typing import Optional


class SlippageModel:
    """
    Slippage model for simulating execution costs.
    
    Supports multiple slippage models:
    - Fixed: Fixed basis points per trade
    - Volatility: Proportional to volatility
    - Volume: Inverse to volume
    """
    
    def __init__(self, model_type: str = "fixed", fixed_bps: float = 1.0):
        """
        Initialize slippage model.
        
        Args:
            model_type: Type of slippage model
            fixed_bps: Fixed slippage in basis points
        """
        self.model_type = model_type
        self.fixed_bps = fixed_bps
    
    def calculate_slippage(
        self,
        quantity: float,
        price: float,
        side: str,
        volatility: Optional[float] = None,
        volume: Optional[float] = None,
        avg_volume: Optional[float] = None
    ) -> float:
        """
        Calculate slippage cost.
        
        Args:
            quantity: Order quantity
            price: Order price
            side: 'entry' or 'exit'
            volatility: Annualized volatility (for vol-based model)
            volume: Current volume (for volume-based model)
            avg_volume: Average volume (for volume-based model)
        
        Returns:
            Slippage cost in currency
        """
        position_value = quantity * price
        
        if self.model_type == "fixed":
            slippage_bps = self.fixed_bps
        
        elif self.model_type == "volatility" and volatility is not None:
            # Slippage proportional to volatility
            slippage_bps = self.fixed_bps * (volatility / 0.20)  # Normalize to 20% vol
        
        elif self.model_type == "volume" and volume is not None and avg_volume is not None:
            # Slippage inverse to relative volume
            if avg_volume > 0:
                volume_ratio = volume / avg_volume
                slippage_bps = self.fixed_bps / max(volume_ratio, 0.1)
            else:
                slippage_bps = self.fixed_bps
        
        else:
            slippage_bps = self.fixed_bps
        
        return position_value * slippage_bps / 10000


class MarketImpactModel:
    """
    Market impact model for large orders.
    
    Implements square-root impact model:
    I = eta * sigma * (Q / ADV)^delta
    
    where:
    - eta: Impact coefficient
    - sigma: Daily volatility
    - Q: Order quantity
    - ADV: Average daily volume
    - delta: Impact exponent (typically 0.5-0.6)
    """
    
    def __init__(self, model_type: str = "square_root", coefficient: float = 1.0):
        """
        Initialize market impact model.
        
        Args:
            model_type: Type of impact model
            coefficient: Impact coefficient (eta)
        """
        self.model_type = model_type
        self.coefficient = coefficient
    
    def calculate_impact(
        self,
        quantity: float,
        price: float,
        adv: float,
        volatility: float,
        participation_rate: Optional[float] = None
    ) -> float:
        """
        Calculate market impact.
        
        Args:
            quantity: Order quantity
            price: Current price
            adv: Average daily volume (in shares)
            volatility: Annualized volatility
            participation_rate: Target participation rate
        
        Returns:
            Market impact as fraction of price
        """
        if adv <= 0:
            return 0.0
        
        # Daily volatility
        daily_vol = volatility / np.sqrt(252)
        
        if self.model_type == "square_root":
            # Square-root impact model
            order_fraction = quantity / adv
            impact = self.coefficient * daily_vol * np.sqrt(order_fraction)
        
        elif self.model_type == "linear":
            # Linear impact model
            order_fraction = quantity / adv
            impact = self.coefficient * daily_vol * order_fraction
        
        elif self.model_type == "participation" and participation_rate is not None:
            # Participation rate model
            impact = self.coefficient * daily_vol * np.sqrt(participation_rate)
        
        else:
            impact = 0.0
        
        return impact
    
    def calculate_temporary_impact(
        self,
        quantity: float,
        price: float,
        adv: float,
        volatility: float,
        execution_time_hours: float = 1.0
    ) -> float:
        """
        Calculate temporary (immediate) market impact.
        
        Args:
            quantity: Order quantity
            price: Current price
            adv: Average daily volume
            volatility: Annualized volatility
            execution_time_hours: Expected execution time
        
        Returns:
            Temporary impact as fraction of price
        """
        # Temporary impact is typically higher than permanent
        permanent_impact = self.calculate_impact(quantity, price, adv, volatility)
        
        # Temporary impact decays with time
        decay_factor = 1.0 / np.sqrt(max(execution_time_hours, 0.1))
        
        return permanent_impact * (1 + decay_factor)
    
    def estimate_execution_cost(
        self,
        quantity: float,
        price: float,
        adv: float,
        volatility: float,
        spread_bps: float = 1.0
    ) -> dict:
        """
        Estimate total execution cost.
        
        Args:
            quantity: Order quantity
            price: Current price
            adv: Average daily volume
            volatility: Annualized volatility
            spread_bps: Bid-ask spread in basis points
        
        Returns:
            Dictionary with cost breakdown
        """
        # Spread cost (half-spread)
        spread_cost = spread_bps / 2 / 10000
        
        # Market impact
        impact = self.calculate_impact(quantity, price, adv, volatility)
        
        # Total cost
        total_cost = spread_cost + impact
        
        return {
            'spread_cost': spread_cost,
            'market_impact': impact,
            'total_cost': total_cost,
            'total_cost_bps': total_cost * 10000,
            'position_value': quantity * price,
            'dollar_cost': quantity * price * total_cost
        }
