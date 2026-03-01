import argparse
import json
from datetime import datetime


def _load_csv(path, symbol="SYMBOL"):
    import pandas as pd
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    else:
        df.index = pd.date_range("2000-01-01", periods=len(df), freq="D")
    must = ["open", "high", "low", "close"]
    for c in must:
        if c not in df.columns:
            raise SystemExit(f"missing column: {c}")
    if "volume" not in df.columns:
        df["volume"] = 0
    return df, symbol


def _generate_signals(df, symbol, window=20, threshold=0.5, limit=10):
    import pandas as pd
    import numpy as np
    from ..common.types import Signal, SignalType
    signals = []
    z = (df["close"] - df["close"].rolling(window).mean()) / df["close"].rolling(window).std()
    z = z.dropna()
    for ts, val in z.tail(limit).items():
        if val > threshold:
            s = Signal(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                signal_type=SignalType.BUY,
                confidence=min(1.0, float(abs(val) / 2)),
                expected_return=1.0,
                half_life_seconds=86400,
                strategy_id="cli_signal",
                suggested_stop=float(df.loc[ts, "close"] * 0.98),
                suggested_target=float(df.loc[ts, "close"] * 1.03),
            )
            signals.append(s)
        elif val < -threshold:
            s = Signal(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                signal_type=SignalType.SELL,
                confidence=min(1.0, float(abs(val) / 2)),
                expected_return=1.0,
                half_life_seconds=86400,
                strategy_id="cli_signal",
                suggested_stop=float(df.loc[ts, "close"] * 1.02),
                suggested_target=float(df.loc[ts, "close"] * 0.97),
            )
            signals.append(s)
    return signals


def main():
    parser = argparse.ArgumentParser(prog="ai-trading-signal")
    parser.add_argument("--csv", type=str, required=True)
    parser.add_argument("--symbol", type=str, default="SYMBOL")
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    df, symbol = _load_csv(args.csv, args.symbol)
    signals = _generate_signals(df, symbol, args.window, args.threshold, args.limit)
    payload = [
        {
            "symbol": s.symbol,
            "timestamp": s.timestamp.isoformat(),
            "type": s.signal_type.value,
            "confidence": s.confidence,
            "stop": s.suggested_stop,
            "target": s.suggested_target,
        }
        for s in signals
    ]
    print(json.dumps(payload, default=str))


if __name__ == "__main__":
    main()

