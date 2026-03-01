def test_ensemble_backtest_two_symbols():
    import numpy as np
    import pandas as pd
    from datetime import datetime, timedelta
    from backtest.engine import BacktestEngine, BacktestConfig
    from risk.position_sizing import FixedFractionalSizer
    from backtest import cli as backtest_cli
    n = 240
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    base = 100 + np.linspace(0, 5, n)
    noise1 = np.random.normal(0, 0.3, n).cumsum() * 0.02
    noise2 = np.random.normal(0, 0.3, n).cumsum() * 0.02
    close_a = pd.Series(base + noise1, index=idx, name="close")
    close_b = pd.Series(base * 1.01 + noise2, index=idx, name="close")
    def make_df(close):
        return pd.DataFrame(
            {
                "open": close.shift(1).fillna(close.iloc[0]),
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000,
            },
            index=close.index,
        )
    data = {"AAA": make_df(close_a), "BBB": make_df(close_b)}
    gen = backtest_cli._ensemble_signal_generator_factory(
        {"momentum": True, "mean_reversion": True, "stat_arb": False},
        "CONFIDENCE_WEIGHTED",
        statarb_pairs=None
    )
    engine = BacktestEngine(BacktestConfig(initial_capital=100000.0))
    metrics = engine.run(data, gen, FixedFractionalSizer(0.01))
    assert metrics.initial_capital == 100000.0
    assert metrics.final_equity > 0
    assert len(metrics.signals) >= 0
    assert metrics.num_trades >= 0

