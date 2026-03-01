def test_cli_entry_points_importable():
    import importlib
    backtest_cli = importlib.import_module("backtest.cli")
    signal_cli = importlib.import_module("signal.cli")
    risk_cli = importlib.import_module("risk.cli")
    exec_cli = importlib.import_module("execution.cli")
    assert callable(getattr(backtest_cli, "main"))
    assert callable(getattr(signal_cli, "main"))
    assert callable(getattr(risk_cli, "main"))
    assert callable(getattr(exec_cli, "main"))
