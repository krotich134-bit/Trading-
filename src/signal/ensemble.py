"""
Signal ensemble and combination methods.

Implements multiple ensemble techniques for combining signals from different strategies.
"""

import numpy as np
import pandas as pd
from enum import Enum
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ..common.types import Signal, SignalType


class EnsembleMethod(Enum):
    """Ensemble combination methods."""
    EQUAL_WEIGHT = "equal_weight"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    PERFORMANCE_WEIGHTED = "performance_weighted"
    BAYESIAN_AVERAGING = "bayesian_averaging"
    STACKING = "stacking"
    MAJORITY_VOTE = "majority_vote"


class SignalEnsemble:
    """
    Signal ensemble for combining multiple strategy signals.
    
    Supports various ensemble methods with confidence scoring and decay weighting.
    """
    
    def __init__(self, method: EnsembleMethod = EnsembleMethod.CONFIDENCE_WEIGHTED):
        """
        Initialize signal ensemble.
        
        Args:
            method: Ensemble combination method
        """
        self.method = method
        self.strategy_performance = {}
        self.strategy_weights = {}
    
    def combine_signals(
        self,
        signals: List[Signal],
        current_time: Optional[datetime] = None
    ) -> Optional[Signal]:
        """
        Combine multiple signals into ensemble signal.
        
        Args:
            signals: List of signals from different strategies
            current_time: Current time for decay calculation
        
        Returns:
            Ensemble signal or None
        """
        if not signals:
            return None
        
        if current_time is None:
            current_time = datetime.utcnow()
        
        # Filter expired signals
        active_signals = [
            s for s in signals 
            if s.decay_weight(current_time) > 0.1
        ]
        
        if not active_signals:
            return None
        
        # Apply ensemble method
        if self.method == EnsembleMethod.EQUAL_WEIGHT:
            return self._equal_weight(active_signals, current_time)
        elif self.method == EnsembleMethod.CONFIDENCE_WEIGHTED:
            return self._confidence_weighted(active_signals, current_time)
        elif self.method == EnsembleMethod.PERFORMANCE_WEIGHTED:
            return self._performance_weighted(active_signals, current_time)
        elif self.method == EnsembleMethod.BAYESIAN_AVERAGING:
            return self._bayesian_averaging(active_signals, current_time)
        elif self.method == EnsembleMethod.MAJORITY_VOTE:
            return self._majority_vote(active_signals, current_time)
        else:
            return self._equal_weight(active_signals, current_time)
    
    def _equal_weight(
        self,
        signals: List[Signal],
        current_time: datetime
    ) -> Optional[Signal]:
        """Equal weight ensemble."""
        return self._weighted_average(signals, current_time, equal_weights=True)
    
    def _confidence_weighted(
        self,
        signals: List[Signal],
        current_time: datetime
    ) -> Optional[Signal]:
        """Confidence-weighted ensemble."""
        weights = [s.confidence * s.decay_weight(current_time) for s in signals]
        return self._weighted_average(signals, current_time, weights=weights)
    
    def _performance_weighted(
        self,
        signals: List[Signal],
        current_time: datetime
    ) -> Optional[Signal]:
        """Performance-weighted ensemble using historical strategy performance."""
        weights = []
        for signal in signals:
            perf = self.strategy_performance.get(signal.strategy_id, 0.5)
            decay = signal.decay_weight(current_time)
            weights.append(perf * signal.confidence * decay)
        
        return self._weighted_average(signals, current_time, weights=weights)
    
    def _bayesian_averaging(
        self,
        signals: List[Signal],
        current_time: datetime
    ) -> Optional[Signal]:
        """
        Bayesian model averaging.
        
        Weights signals by posterior probability based on historical accuracy.
        """
        # Get posterior probabilities (simplified)
        posteriors = []
        for signal in signals:
            prior = signal.confidence
            likelihood = self.strategy_performance.get(signal.strategy_id, 0.5)
            posterior = prior * likelihood
            decay = signal.decay_weight(current_time)
            posteriors.append(posterior * decay)
        
        # Normalize
        total = sum(posteriors)
        if total > 0:
            weights = [p / total for p in posteriors]
        else:
            weights = None
        
        return self._weighted_average(signals, current_time, weights=weights)
    
    def _majority_vote(
        self,
        signals: List[Signal],
        current_time: datetime
    ) -> Optional[Signal]:
        """Majority vote ensemble."""
        # Count votes by signal type
        votes = {SignalType.BUY: 0, SignalType.SELL: 0, SignalType.HOLD: 0}
        
        for signal in signals:
            decay = signal.decay_weight(current_time)
            votes[signal.signal_type] += signal.confidence * decay
        
        # Determine winner
        winner = max(votes, key=votes.get)
        total_votes = sum(votes.values())
        
        if total_votes == 0 or votes[winner] / total_votes < 0.5:
            return None
        
        # Calculate ensemble confidence
        confidence = votes[winner] / total_votes
        
        # Aggregate metadata
        all_metadata = {}
        expected_returns = []
        for signal in signals:
            if signal.signal_type == winner:
                all_metadata[signal.strategy_id] = signal.metadata
                expected_returns.append(signal.expected_return)
        
        # Use median expected return
        expected_return = np.median(expected_returns) if expected_returns else 0
        
        # Use shortest half-life
        half_life = min(s.half_life_seconds for s in signals if s.signal_type == winner)
        
        return Signal(
            symbol=signals[0].symbol,
            timestamp=current_time,
            signal_type=winner,
            confidence=confidence,
            expected_return=expected_return,
            half_life_seconds=half_life,
            strategy_id="ensemble_majority_vote",
            metadata={
                'votes': votes,
                'component_signals': all_metadata,
                'ensemble_method': 'majority_vote'
            }
        )
    
    def _weighted_average(
        self,
        signals: List[Signal],
        current_time: datetime,
        weights: Optional[List[float]] = None,
        equal_weights: bool = False
    ) -> Optional[Signal]:
        """
        Compute weighted average of signals.
        
        Args:
            signals: List of signals
            current_time: Current time
            weights: Optional weights
            equal_weights: Use equal weights
        
        Returns:
            Ensemble signal
        """
        if equal_weights:
            weights = [1.0] * len(signals)
        elif weights is None:
            weights = [s.confidence for s in signals]
        
        # Apply decay
        decayed_weights = [
            w * s.decay_weight(current_time) 
            for w, s in zip(weights, signals)
        ]
        
        # Normalize weights
        total_weight = sum(decayed_weights)
        if total_weight == 0:
            return None
        
        normalized_weights = [w / total_weight for w in decayed_weights]
        
        # Separate by signal type
        buy_signals = [(s, w) for s, w in zip(signals, normalized_weights) if s.signal_type == SignalType.BUY]
        sell_signals = [(s, w) for s, w in zip(signals, normalized_weights) if s.signal_type == SignalType.SELL]
        
        # Calculate weighted scores
        buy_score = sum(w for _, w in buy_signals)
        sell_score = sum(w for _, w in sell_signals)
        
        # Determine signal type
        if buy_score > sell_score and buy_score > 0.3:
            signal_type = SignalType.BUY
            confidence = buy_score
            selected_signals = buy_signals
        elif sell_score > buy_score and sell_score > 0.3:
            signal_type = SignalType.SELL
            confidence = sell_score
            selected_signals = sell_signals
        else:
            return None
        
        # Aggregate expected return
        if selected_signals:
            expected_returns = [s.expected_return * w for s, w in selected_signals]
            expected_return = sum(expected_returns) / sum(w for _, w in selected_signals)
        else:
            expected_return = 0
        
        # Use shortest half-life
        half_life = min(s.half_life_seconds for s, _ in selected_signals)
        
        # Aggregate metadata
        all_metadata = {s.strategy_id: s.metadata for s, _ in selected_signals}
        
        # Aggregate stops (use most conservative)
        stops = [s.suggested_stop for s, _ in selected_signals if s.suggested_stop is not None]
        targets = [s.suggested_target for s, _ in selected_signals if s.suggested_target is not None]
        
        suggested_stop = min(stops) if stops and signal_type == SignalType.BUY else (max(stops) if stops else None)
        suggested_target = max(targets) if targets and signal_type == SignalType.BUY else (min(targets) if targets else None)
        
        return Signal(
            symbol=signals[0].symbol,
            timestamp=current_time,
            signal_type=signal_type,
            confidence=confidence,
            expected_return=expected_return,
            half_life_seconds=half_life,
            strategy_id=f"ensemble_{self.method.value}",
            metadata={
                'buy_score': buy_score,
                'sell_score': sell_score,
                'component_signals': all_metadata,
                'ensemble_method': self.method.value,
                'weights': {s.strategy_id: w for s, w in zip(signals, normalized_weights)}
            },
            suggested_stop=suggested_stop,
            suggested_target=suggested_target
        )
    
    def update_strategy_performance(
        self,
        strategy_id: str,
        performance: float
    ) -> None:
        """
        Update strategy performance for weighting.
        
        Args:
            strategy_id: Strategy identifier
            performance: Performance metric (e.g., Sharpe ratio, win rate)
        """
        # Exponential moving average of performance
        alpha = 0.3  # Smoothing factor
        current = self.strategy_performance.get(strategy_id, performance)
        self.strategy_performance[strategy_id] = alpha * performance + (1 - alpha) * current
    
    def get_ensemble_weights(self) -> Dict[str, float]:
        """
        Get current ensemble weights.
        
        Returns:
            Dictionary of strategy_id -> weight
        """
        return self.strategy_weights.copy()
