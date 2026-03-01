"""
Core data types and structures for the AI Trading System.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable, Any, Tuple
from enum import Enum
from datetime import datetime
import numpy as np
import pandas as pd


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class MarketData:
    """Standardized market data tick."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    vwap: Optional[float] = None
    
    @property
    def mid(self) -> float:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.close
    
    @property
    def spread(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None


@dataclass
class Signal:
    """Trading signal with confidence and metadata."""
    symbol: str
    timestamp: datetime
    signal_type: SignalType
    confidence: float  # 0.0 to 1.0
    expected_return: float  # Expected return in R multiples
    half_life_seconds: float  # Signal decay half-life
    strategy_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Risk parameters
    suggested_stop: Optional[float] = None
    suggested_target: Optional[float] = None
    max_position_size: Optional[float] = None
    
    def decay_weight(self, current_time: datetime) -> float:
        """Compute exponential decay weight based on elapsed time."""
        elapsed = (current_time - self.timestamp).total_seconds()
        lambda_decay = np.log(2) / self.half_life_seconds
        return np.exp(-lambda_decay * elapsed)


@dataclass
class Position:
    """Current position state."""
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    entry_time: datetime
    strategy_id: str
    
    # Risk management
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    max_risk_pct: float = 0.01  # 1% default
    
    # Tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None
    
    def update_unrealized(self, current_price: float) -> float:
        """Update and return unrealized P&L."""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
        
        # Update trailing extremes
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
        if self.lowest_price is None or current_price < self.lowest_price:
            self.lowest_price = current_price
            
        return self.unrealized_pnl
    
    @property
    def current_risk(self) -> float:
        """Current risk in currency terms."""
        if self.stop_price is None:
            return abs(self.unrealized_pnl)
        
        if self.side == PositionSide.LONG:
            risk_per_unit = self.entry_price - self.stop_price
        else:
            risk_per_unit = self.stop_price - self.entry_price
            
        return abs(risk_per_unit * self.quantity)
    
    @property
    is_active(self) -> bool:
        return self.side != PositionSide.FLAT and self.quantity != 0


@dataclass
class Order:
    """Order request/execution record."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    timestamp: datetime
    
    # Price levels
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    # Execution
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    commission: float = 0.0
    slippage: float = 0.0
    
    # Status
    status: str = "pending"  # pending, filled, partial, cancelled, rejected
    
    @property
    def is_filled(self) -> bool:
        return self.status == "filled" and self.filled_quantity == self.quantity
    
    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity


@dataclass
class Trade:
    """Completed trade record."""
    trade_id: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    side: PositionSide
    
    # P&L
    gross_pnl: float
    commission: float
    slippage: float
    
    # Risk metrics
    max_adverse_excursion: float
    max_favorable_excursion: float
    
    # Context
    entry_signal: Optional[Signal] = None
    exit_reason: str = "unknown"
    
    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commission - self.slippage
    
    @property
    def return_multiple(self) -> float:
        """Return in R multiples."""
        if self.entry_signal and self.entry_signal.suggested_stop:
            risk = abs(self.entry_price - self.entry_signal.suggested_stop)
            if risk > 0:
                return self.net_pnl / (risk * self.quantity)
        return 0.0


@dataclass
class RiskMetrics:
    """Portfolio risk metrics snapshot."""
    timestamp: datetime
    
    # Exposure
    gross_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float
    cash_ratio: float
    
    # Risk measures
    portfolio_heat: float  # sqrt(r^T * Sigma * r)
    var_95: float  # 95% VaR
    var_99: float  # 99% VaR
    expected_shortfall: float
    
    # Concentration
    max_single_position: float
    max_sector_exposure: float
    
    # Drawdown
    current_drawdown: float
    max_drawdown: float
    
    # Correlation
    avg_correlation: float
    correlation_stress: bool  # True if avg correlation > 0.7


@dataclass
class PortfolioState:
    """Complete portfolio state."""
    timestamp: datetime
    equity: float
    cash: float
    positions: Dict[str, Position]
    trades: List[Trade]
    
    # History
    equity_curve: pd.Series = field(default_factory=pd.Series)
    
    @property
    def total_value(self) -> float:
        position_value = sum(
            pos.unrealized_pnl for pos in self.positions.values()
        )
        return self.equity + position_value
    
    @property
    def open_positions_count(self) -> int:
        return sum(1 for pos in self.positions.values() if pos.is_active)


TimeSeries = pd.Series
