import argparse
import json


def main():
    parser = argparse.ArgumentParser(prog="ai-trading-risk")
    parser.add_argument("--simulate-fixed", action="store_true")
    parser.add_argument("--n-trades", type=int, default=500)
    parser.add_argument("--n-sims", type=int, default=1000)
    parser.add_argument("--win-prob", type=float, default=0.5)
    parser.add_argument("--win-loss", type=float, default=1.5)
    parser.add_argument("--risk", type=float, default=0.01)
    parser.add_argument("--equity", type=float, default=100000.0)
    parser.add_argument("--ruin", type=float, default=0.2)
    args = parser.parse_args()
    if args.simulate_fixed:
        from .monte_carlo import MonteCarloSimulator
        sim = MonteCarloSimulator(seed=42)
        res = sim.simulate_fixed_parameters(
            n_trades=args.n_trades,
            n_sims=args.n_sims,
            win_probability=args.win_prob,
            win_loss_ratio=args.win_loss,
            risk_per_trade=args.risk,
            starting_equity=args.equity,
            ruin_threshold=args.ruin,
        )
        print(res.summary())
        out = {
            "ruin_probability": res.ruin_probability,
            "terminal_wealth_mean": res.terminal_wealth_mean,
            "terminal_wealth_median": res.terminal_wealth_median,
            "max_drawdown_mean": res.max_drawdown_mean,
            "probability_profit": res.probability_profit,
            "probability_double": res.probability_double,
            "expected_return": res.expected_return,
        }
        print(json.dumps(out))
    else:
        print(json.dumps({"status": "ok"}))


if __name__ == "__main__":
    main()

