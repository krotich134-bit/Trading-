def test_backtest_engine_smoke():
    import numpy as np
    import pandas as pd
    from backtest.engine import BacktestEngine, BacktestConfig
    from risk.position_sizing import FixedFractionalSizer
    from common.types import Signal, SignalType
    from datetime import datetime
    idx = pd.date_range("2023-01-01", periods=120, freq="D")
    base = 100 + np.linspace(0, 2, len(idx))
    close = pd.Series(base, index=idx, name="close")
    df = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000,
        },
        index=idx,
    )
    data = {"TEST": df}
    def gen(data_dict, ts):
        signals = []
        if ts not in df.index:
            return signals
        i = df.index.get_loc(ts)
        if i < 20:
            return signals
        sub = df.iloc[: i + 1]
        sma = sub["close"].rolling(window=20).mean().iloc[-1]
        if sub["close"].iloc[-1] > sma:
            s = Signal(
                symbol="TEST",
                timestamp=datetime.utcnow(),
                signal_type=SignalType.BUY,
                confidence=0.8,
                expected_return=1.0,
                half_life_seconds=86400,
                strategy_id="test",
                suggested_stop=float(sub["close"].iloc[-1] * 0.98),
                suggested_target=float(sub["close"].iloc[-1] * 1.03),
            )
            signals.append(s)
        return signals
    engine = BacktestEngine(BacktestConfig(initial_capital=100000.0))
    metrics = engine.run(data, gen, FixedFractionalSizer(0.01))
    assert metrics.initial_capital == 100000.0
    assert metrics.final_equity > 0
    assert metrics.num_trades >= 0

