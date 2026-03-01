"""
Backtesting engine with realistic execution simulation.

Implements event-driven backtesting with slippage, commissions, and market impact.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Callable, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict

from ..common.types import (
    Signal, Position, Trade, Order, OrderType, OrderSide,
    PositionSide, PortfolioState, MarketData
)
from ..common.utils import max_drawdown, sharpe_ratio, sortino_ratio
from ..risk.position_sizing import PositionSizer, FixedFractionalSizer
from ..risk.risk_manager import RiskManager, RiskLimits
from .slippage import SlippageModel, MarketImpactModel
from .metrics import PerformanceMetrics


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    # Capital
    initial_capital: float = 100000.0
    
    # Costs
    commission_rate: float = 0.001  # 10 bps
    slippage_model: str = "fixed"
    slippage_bps: float = 1.0  # 1 bp
    
    # Market impact
    impact_model: str = "square_root"
    impact_coefficient: float = 1.0
    
    # Execution
    fill_probability: float = 0.99
    partial_fill_probability: float = 0.05
    
    # Risk
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    
    # Data
    point_in_time: bool = True  # Enforce point-in-time data


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    Simulates realistic trading with slippage, commissions, and market impact.
    """
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize backtest engine.
        
        Args:
            config: Backtest configuration
        """
        self.config = config
        self.risk_manager = RiskManager(config.risk_limits)
        self.slippage_model = SlippageModel(
            model_type=config.slippage_model,
            fixed_bps=config.slippage_bps
        )
        self.impact_model = MarketImpactModel(
            model_type=config.impact_model,
            coefficient=config.impact_coefficient
        )
        
        # State
        self.portfolio: Optional[PortfolioState] = None
        self.trades: List[Trade] = []
        self.orders: List[Order] = []
        self.signals: List[Signal] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        
        # Tracking
        self.positions: Dict[str, Position] = {}
        self.cash: float = 0.0
        self.peak_equity: float = 0.0
        
    def run(
        self,
        data: Dict[str, pd.DataFrame],
        signal_generator: Callable,
        position_sizer: Optional[PositionSizer] = None
    ) -> PerformanceMetrics:
        """
        Run backtest.
        
        Args:
            data: Dictionary of symbol -> OHLCV DataFrame
            signal_generator: Function that generates signals from data
            position_sizer: Position sizing algorithm
        
        Returns:
            PerformanceMetrics
        """
        # Initialize portfolio
        self.cash = self.config.initial_capital
        self.peak_equity = self.config.initial_capital
        self.equity_curve = [(data[list(data.keys())[0]].index[0], self.config.initial_capital)]
        
        if position_sizer is None:
            position_sizer = FixedFractionalSizer(0.01)
        
        # Get all timestamps
        all_timestamps = sorted(set(
            ts for df in data.values() for ts in df.index
        ))
        
        print(f"Running backtest: {len(all_timestamps)} bars, {len(data)} symbols")
        
        # Event loop
        for i, timestamp in enumerate(all_timestamps):
            if i % 100 == 0:
                print(f"Processing bar {i}/{len(all_timestamps)}: {timestamp}")
            
            # Get current market data for all symbols
            market_data = self._get_market_data_at_time(data, timestamp)
            
            # Update positions with current prices
            self._update_positions(market_data, timestamp)
            
            # Check stops and generate exit signals
            self._check_stops(market_data, timestamp)
            
            # Generate signals
            signals = signal_generator(data, timestamp)
            self.signals.extend(signals)
            
            # Process signals
            for signal in signals:
                self._process_signal(
                    signal, market_data, position_sizer, timestamp
                )
            
            # Record equity
            equity = self._calculate_equity(market_data)
            self.equity_curve.append((timestamp, equity))
            
            # Update peak and drawdown
            self.peak_equity = max(self.peak_equity, equity)
        
        # Close all positions at end
        self._close_all_positions(market_data, timestamp)
        
        # Calculate metrics
        return self._calculate_metrics()
    
    def _get_market_data_at_time(
        self,
        data: Dict[str, pd.DataFrame],
        timestamp: datetime
    ) -> Dict[str, MarketData]:
        """
        Get market data for all symbols at specific time.
        
        Args:
            data: Price data dictionary
            timestamp: Timestamp
        
        Returns:
            Dictionary of symbol -> MarketData
        """
        market_data = {}
        for symbol, df in data.items():
            if timestamp in df.index:
                row = df.loc[timestamp]
                market_data[symbol] = MarketData(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row.get('volume', 0),
                    bid=row.get('bid'),
                    ask=row.get('ask')
                )
        return market_data
    
    def _update_positions(
        self,
        market_data: Dict[str, MarketData],
        timestamp: datetime
    ) -> None:
        """
        Update position P&L with current prices.
        
        Args:
            market_data: Current market data
            timestamp: Current timestamp
        """
        for symbol, position in self.positions.items():
            if symbol in market_data:
                current_price = market_data[symbol].close
                position.update_unrealized(current_price)
    
    def _check_stops(
        self,
        market_data: Dict[str, MarketData],
        timestamp: datetime
    ) -> None:
        """
        Check and execute stop losses.
        
        Args:
            market_data: Current market data
            timestamp: Current timestamp
        """
        for symbol, position in list(self.positions.items()):
            if not position.is_active:
                continue
            
            if symbol not in market_data:
                continue
            
            current_price = market_data[symbol].close
            
            # Check stop
            if position.stop_price:
                if position.side == PositionSide.LONG and current_price <= position.stop_price:
                    self._exit_position(position, current_price, timestamp, "stop_loss")
                elif position.side == PositionSide.SHORT and current_price >= position.stop_price:
                    self._exit_position(position, current_price, timestamp, "stop_loss")
            
            # Check target
            if position.target_price:
                if position.side == PositionSide.LONG and current_price >= position.target_price:
                    self._exit_position(position, current_price, timestamp, "profit_target")
                elif position.side == PositionSide.SHORT and current_price <= position.target_price:
                    self._exit_position(position, current_price, timestamp, "profit_target")
    
    def _process_signal(
        self,
        signal: Signal,
        market_data: Dict[str, MarketData],
        position_sizer: PositionSizer,
        timestamp: datetime
    ) -> None:
        """
        Process trading signal.
        
        Args:
            signal: Trading signal
            market_data: Current market data
            position_sizer: Position sizer
            timestamp: Current timestamp
        """
        symbol = signal.symbol
        
        if symbol not in market_data:
            return
        
        current_price = market_data[symbol].close
        
        # Handle exit signal
        if signal.signal_type.value == 'exit':
            if symbol in self.positions and self.positions[symbol].is_active:
                self._exit_position(self.positions[symbol], current_price, timestamp, "signal_exit")
            return
        
        # Check for existing position
        if symbol in self.positions and self.positions[symbol].is_active:
            # Could add logic to add to position or reverse
            return
        
        # Calculate position size
        stop_price = signal.suggested_stop or (current_price * 0.98 if signal.signal_type.value == 'buy' else current_price * 1.02)
        
        portfolio = self._get_portfolio_state(timestamp)
        sizing_result = position_sizer.calculate_size(
            signal, portfolio, current_price, stop_price
        )
        
        if sizing_result.quantity <= 0:
            return
        
        # Create position
        side = PositionSide.LONG if signal.signal_type.value == 'buy' else PositionSide.SHORT
        
        position = Position(
            symbol=symbol,
            side=side,
            quantity=sizing_result.quantity,
            entry_price=current_price,
            entry_time=timestamp,
            strategy_id=signal.strategy_id,
            stop_price=stop_price,
            target_price=signal.suggested_target,
            max_risk_pct=sizing_result.risk_fraction
        )
        
        # Check risk limits
        approved, reason = self.risk_manager.check_signal(
            signal, portfolio, position
        )
        
        if not approved:
            return
        
        # Execute entry
        self._enter_position(position, current_price, timestamp)
    
    def _enter_position(
        self,
        position: Position,
        price: float,
        timestamp: datetime
    ) -> None:
        """
        Execute position entry.
        
        Args:
            position: Position to enter
            price: Entry price
            timestamp: Entry timestamp
        """
        # Calculate costs
        position_value = position.quantity * price
        commission = position_value * self.config.commission_rate
        
        # Apply slippage
        slippage = self.slippage_model.calculate_slippage(
            position.quantity, price, 'entry'
        )
        
        # Update cash
        total_cost = position_value + commission + slippage
        self.cash -= total_cost
        
        # Store position
        self.positions[position.symbol] = position
        
        # Record order
        order = Order(
            order_id=f"entry_{position.symbol}_{timestamp.strftime('%Y%m%d%H%M%S')}",
            symbol=position.symbol,
            side=OrderSide.BUY if position.side == PositionSide.LONG else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            timestamp=timestamp,
            filled_quantity=position.quantity,
            avg_fill_price=price,
            fill_timestamp=timestamp,
            commission=commission,
            slippage=slippage,
            status="filled"
        )
        self.orders.append(order)
    
    def _exit_position(
        self,
        position: Position,
        price: float,
        timestamp: datetime,
        reason: str
    ) -> None:
        """
        Execute position exit.
        
        Args:
            position: Position to exit
            price: Exit price
            timestamp: Exit timestamp
            reason: Exit reason
        """
        # Calculate costs
        position_value = position.quantity * price
        commission = position_value * self.config.commission_rate
        
        # Apply slippage
        slippage = self.slippage_model.calculate_slippage(
            position.quantity, price, 'exit'
        )
        
        # Calculate P&L
        if position.side == PositionSide.LONG:
            gross_pnl = (price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - price) * position.quantity
        
        net_pnl = gross_pnl - commission - slippage
        
        # Update cash
        if position.side == PositionSide.LONG:
            self.cash += position_value - commission - slippage
        else:
            self.cash += position.entry_price * position.quantity + gross_pnl - commission - slippage
        
        # Create trade record
        trade = Trade(
            trade_id=f"trade_{position.symbol}_{timestamp.strftime('%Y%m%d%H%M%S')}",
            symbol=position.symbol,
            entry_time=position.entry_time,
            exit_time=timestamp,
            entry_price=position.entry_price,
            exit_price=price,
            quantity=position.quantity,
            side=position.side,
            gross_pnl=gross_pnl,
            commission=commission,
            slippage=slippage,
            max_adverse_excursion=0.0,  # Would track during position
            max_favorable_excursion=0.0,
            entry_signal=None,
            exit_reason=reason
        )
        self.trades.append(trade)
        
        # Remove position
        position.side = PositionSide.FLAT
        position.quantity = 0
        
        # Record order
        order = Order(
            order_id=f"exit_{position.symbol}_{timestamp.strftime('%Y%m%d%H%M%S')}",
            symbol=position.symbol,
            side=OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            timestamp=timestamp,
            filled_quantity=position.quantity,
            avg_fill_price=price,
            fill_timestamp=timestamp,
            commission=commission,
            slippage=slippage,
            status="filled"
        )
        self.orders.append(order)
    
    def _close_all_positions(
        self,
        market_data: Dict[str, MarketData],
        timestamp: datetime
    ) -> None:
        """
        Close all open positions at end of backtest.
        
        Args:
            market_data: Current market data
            timestamp: Current timestamp
        """
        for symbol, position in list(self.positions.items()):
            if position.is_active and symbol in market_data:
                self._exit_position(
                    position, market_data[symbol].close, timestamp, "end_of_backtest"
                )
    
    def _get_portfolio_state(self, timestamp: datetime) -> PortfolioState:
        """
        Get current portfolio state.
        
        Args:
            timestamp: Current timestamp
        
        Returns:
            PortfolioState
        """
        equity = self._calculate_equity({})
        
        return PortfolioState(
            timestamp=timestamp,
            equity=equity,
            cash=self.cash,
            positions=self.positions,
            trades=self.trades
        )
    
    def _calculate_equity(self, market_data: Dict[str, MarketData]) -> float:
        """
        Calculate total equity.
        
        Args:
            market_data: Current market data
        
        Returns:
            Total equity
        """
        position_value = sum(
            pos.unrealized_pnl for pos in self.positions.values()
        )
        return self.cash + position_value
    
    def _calculate_metrics(self) -> PerformanceMetrics:
        """
        Calculate performance metrics.
        
        Returns:
            PerformanceMetrics
        """
        equity_series = pd.Series(
            {ts: eq for ts, eq in self.equity_curve}
        )
        
        returns = equity_series.pct_change().dropna()
        
        return PerformanceMetrics(
            equity_curve=equity_series,
            returns=returns,
            trades=self.trades,
            orders=self.orders,
            signals=self.signals,
            initial_capital=self.config.initial_capital,
            final_equity=equity_series.iloc[-1],
            total_return=equity_series.iloc[-1] / self.config.initial_capital - 1,
            sharpe_ratio=sharpe_ratio(returns),
            sortino_ratio=sortino_ratio(returns),
            max_drawdown=max_drawdown(equity_series)[0],
            num_trades=len(self.trades),
            winning_trades=len([t for t in self.trades if t.net_pnl > 0]),
            losing_trades=len([t for t in self.trades if t.net_pnl <= 0]),
            avg_trade_pnl=np.mean([t.net_pnl for t in self.trades]) if self.trades else 0,
            avg_win=np.mean([t.net_pnl for t in self.trades if t.net_pnl > 0]) if any(t.net_pnl > 0 for t in self.trades) else 0,
            avg_loss=np.mean([t.net_pnl for t in self.trades if t.net_pnl <= 0]) if any(t.net_pnl <= 0 for t in self.trades) else 0,
            profit_factor=abs(sum(t.net_pnl for t in self.trades if t.net_pnl > 0)) / abs(sum(t.net_pnl for t in self.trades if t.net_pnl < 0)) if any(t.net_pnl < 0 for t in self.trades) else float('inf'),
            commission_total=sum(t.commission for t in self.trades),
            slippage_total=sum(t.slippage for t in self.trades)
        )
