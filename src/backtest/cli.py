import argparse
import json
from datetime import datetime
from ..common.schema import normalize_ohlcv


def _make_synthetic_data(rows=300):
    import numpy as np
    import pandas as pd
    idx = pd.date_range("2023-01-01", periods=rows, freq="D")
    trend = np.linspace(0, 5, rows)
    noise = np.random.normal(0, 0.5, rows).cumsum() * 0.05
    base = 100 + trend + noise
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
    return {"TEST": df}


def _standardize_columns(df):
    return normalize_ohlcv(df)

def _load_csv(path, symbol="SYMBOL"):
    import pandas as pd
    df = pd.read_csv(path)
    df = _standardize_columns(df)
    return {symbol: df}

def _load_parquet(path, symbol="SYMBOL"):
    import pandas as pd
    df = pd.read_parquet(path)
    df = _standardize_columns(df)
    return {symbol: df}

def _load_files(paths, symbols=None):
    import os
    data = {}
    for i, p in enumerate(paths):
        sym = symbols[i] if symbols and i < len(symbols) else f"SYM{i+1}"
        ext = os.path.splitext(p)[1].lower()
        if ext in [".parquet", ".pq", ".pqt"]:
            d = _load_parquet(p, sym)
        else:
            d = _load_csv(p, sym)
        data.update(d)
    return data


def _ensemble_signal_generator_factory(enabled_strats, ensemble_method, statarb_pairs=None):
    from ..signal.strategies import MomentumStrategy, MeanReversionStrategy, StatisticalArbitrageStrategy
    from ..signal.ensemble import SignalEnsemble, EnsembleMethod

    ensemble = SignalEnsemble(method=EnsembleMethod[ensemble_method])
    momentum = MomentumStrategy() if enabled_strats.get("momentum", True) else None
    meanrev = MeanReversionStrategy() if enabled_strats.get("mean_reversion", True) else None
    statarb = StatisticalArbitrageStrategy() if enabled_strats.get("stat_arb", False) else None

    def generator(data_dict, ts):
        import pandas as pd
        out = []
        symbols = list(data_dict.keys())
        for sym, df in data_dict.items():
            if ts not in df.index:
                continue
            idx = df.index.get_loc(ts)
            if idx < 60:
                continue
            sub = df.iloc[: idx + 1]
            candidates = []
            if momentum is not None:
                s = momentum.generate_signal(sub, sym)
                if s:
                    candidates.append(s)
            if meanrev is not None:
                s = meanrev.generate_signal(sub, sym)
                if s:
                    candidates.append(s)
            if statarb is not None and statarb_pairs and sym in statarb_pairs:
                pair_sym = statarb_pairs[sym]
                if pair_sym in data_dict and ts in data_dict[pair_sym].index:
                    pidx = data_dict[pair_sym].index.get_loc(ts)
                    if pidx >= 60:
                        pair_sub = data_dict[pair_sym].iloc[: pidx + 1]
                        s = statarb.generate_signal(sub, sym, pair_data=pair_sub, pair_symbol=pair_sym)
                        if s:
                            candidates.append(s)
            ens = ensemble.combine_signals(candidates, current_time=ts)
            if ens:
                out.append(ens)
        return out

    return generator


def main():
    parser = argparse.ArgumentParser(prog="ai-trading-backtest")
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--files", type=str, default=None)
    parser.add_argument("--symbols", type=str, default=None)
    parser.add_argument("--capital", type=float, default=100000.0)
    parser.add_argument("--risk", type=float, default=0.01)
    parser.add_argument("--ensemble", type=str, default="CONFIDENCE_WEIGHTED", choices=["EQUAL_WEIGHT","CONFIDENCE_WEIGHTED","MAJORITY_VOTE","PERFORMANCE_WEIGHTED","BAYESIAN_AVERAGING"])
    parser.add_argument("--enable-momentum", action="store_true", default=True)
    parser.add_argument("--enable-meanreversion", action="store_true", default=True)
    parser.add_argument("--enable-statarb", action="store_true", default=False)
    parser.add_argument("--pairs", type=str, default=None)
    parser.add_argument("--pairs-file", type=str, default=None)
    args = parser.parse_args()
    if args.files:
        paths = [p.strip() for p in args.files.split(",") if p.strip()]
        syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
        data = _load_files(paths, syms)
    elif args.csv:
        paths = [p.strip() for p in args.csv.split(",") if p.strip()]
        syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
        data = _load_files(paths, syms)
    else:
        data = _make_synthetic_data()
    from .engine import BacktestEngine, BacktestConfig
    from ..risk.position_sizing import FixedFractionalSizer
    cfg = BacktestConfig(initial_capital=args.capital)
    engine = BacktestEngine(cfg)
    enabled = {
        "momentum": args.enable_momentum,
        "mean_reversion": args.enable_meanreversion,
        "stat_arb": args.enable_statarb,
    }
    pairs = None
    if args.enable_statarb:
        if args.pairs_file:
            import json as _json
            with open(args.pairs_file, "r", encoding="utf-8") as fh:
                pairs = _json.load(fh)
        elif args.pairs:
            pairs = {}
            for item in [x for x in args.pairs.split(";") if x.strip()]:
                a, b = [t.strip() for t in item.split(":")]
                pairs[a] = b
        elif len(data.keys()) >= 2:
            symlist = list(data.keys())
            pairs = {}
            for i, s in enumerate(symlist):
                pairs[s] = symlist[(i + 1) % len(symlist)]
        if pairs:
            valid_syms = set(data.keys())
            filtered = {}
            for k, v in pairs.items():
                if k in valid_syms and v in valid_syms:
                    filtered[k] = v
                else:
                    try:
                        print(f"Skipping pair {k}:{v} not in dataset")
                    except Exception:
                        pass
            pairs = filtered if filtered else None
    generator = _ensemble_signal_generator_factory(enabled, args.ensemble, statarb_pairs=pairs if pairs else None)
    metrics = engine.run(data, generator, FixedFractionalSizer(args.risk))
    print(metrics.summary())
    out = {
        "initial_capital": metrics.initial_capital,
        "final_equity": metrics.final_equity,
        "total_return": metrics.total_return,
        "sharpe_ratio": metrics.sharpe_ratio,
        "max_drawdown": metrics.max_drawdown,
        "num_trades": metrics.num_trades,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
