import argparse
import json
import sys
from datetime import datetime
import math
import time


def _parse_orders_from_stdin():
    raw = sys.stdin.read()
    if not raw.strip():
        return []
    obj = json.loads(raw)
    if isinstance(obj, dict):
        return [obj]
    return obj


def _compute_fill_price(order, spread_bps, slippage_bps):
    side = order.get("side", "buy").lower()
    base_price = float(order.get("price", 100.0))
    if "bid" in order and "ask" in order:
        if side == "buy":
            base_price = float(order["ask"])
        else:
            base_price = float(order["bid"])
        half_spread = 0.0
    else:
        half_spread = spread_bps / 2.0 / 10000.0
    slip = slippage_bps / 10000.0
    if side == "buy":
        return base_price * (1 + half_spread + slip)
    else:
        return base_price * (1 - half_spread - slip)


def main():
    parser = argparse.ArgumentParser(prog="ai-trading-exec")
    parser.add_argument("--spread-bps", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--participation", type=float, default=0.1)
    parser.add_argument("--vol", type=float, default=0.2)
    parser.add_argument("--adv", type=float, default=1000000.0)
    parser.add_argument("--latency-ms", type=int, default=0)
    parser.add_argument("--adv-file", type=str, default=None)
    parser.add_argument("--latency-dist", type=str, default="constant", choices=["constant","normal","lognormal","uniform"])
    parser.add_argument("--latency-mean-ms", type=float, default=0.0)
    parser.add_argument("--latency-std-ms", type=float, default=0.0)
    parser.add_argument("--latency-min-ms", type=float, default=0.0)
    parser.add_argument("--latency-max-ms", type=float, default=0.0)
    parser.add_argument("--venue-latency-file", type=str, default=None)
    args = parser.parse_args()
    from .executor import ExecutionEngine
    from ..common.types import Order, OrderType, OrderSide
    from ..backtest.slippage import MarketImpactModel
    engine = ExecutionEngine()
    adv_cache = {}
    if args.adv_file:
        try:
            with open(args.adv_file, "r", encoding="utf-8") as fh:
                adv_cache = json.load(fh)
        except Exception:
            adv_cache = {}
    venue_lat = {}
    if args.venue_latency_file:
        try:
            with open(args.venue_latency_file, "r", encoding="utf-8") as fh:
                venue_lat = json.load(fh)
        except Exception:
            venue_lat = {}
    orders_in = _parse_orders_from_stdin()
    results = []
    latencies = []
    for o in orders_in:
        order = Order(
            order_id=str(o.get("order_id", f"order_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}")),
            symbol=str(o["symbol"]),
            side=OrderSide.BUY if str(o.get("side","buy")).lower()=="buy" else OrderSide.SELL,
            order_type=OrderType.MARKET if str(o.get("order_type","market")).lower()=="market" else OrderType.LIMIT,
            quantity=float(o["quantity"]),
            timestamp=datetime.utcnow(),
            limit_price=float(o.get("limit_price")) if o.get("limit_price") is not None else None,
        )
        fills = []
        if order.order_type == OrderType.MARKET:
            adv = float(o.get("adv", adv_cache.get(order.symbol, args.adv)))
            vol = float(o.get("volatility", args.vol))
            participation = float(o.get("participation", args.participation))
            max_chunk = max(1.0, adv * participation)
            chunks = int(math.ceil(order.quantity / max_chunk))
            remain = order.quantity
            impact_model = MarketImpactModel(model_type="square_root", coefficient=1.0)
            base_price = float(o.get("price", 100.0))
            total_qty = 0.0
            total_px_qty = 0.0
            now_ts = datetime.utcnow()
            for i in range(chunks):
                q = min(remain, max_chunk)
                remain -= q
                impact_frac = impact_model.calculate_impact(q, base_price, adv, vol)
                slp_bps = float(o.get("slippage_bps", args.slippage_bps))
                spr_bps = float(o.get("spread_bps", args.spread_bps))
                px = _compute_fill_price(o, spr_bps, slp_bps)
                if order.side == OrderSide.BUY:
                    px = px * (1 + impact_frac)
                else:
                    px = px * (1 - impact_frac)
                fill_entry = {
                    "qty": q,
                    "price": px,
                    "time": now_ts.isoformat(),
                    "chunk_index": i,
                }
                venue = o.get("venue")
                dist_cfg = None
                if venue and venue in venue_lat:
                    dist_cfg = venue_lat[venue]
                if dist_cfg:
                    d = str(dist_cfg.get("dist", args.latency_dist)).lower()
                    if d == "normal":
                        mu = float(dist_cfg.get("mean_ms", args.latency_mean_ms))
                        sd = float(dist_cfg.get("std_ms", args.latency_std_ms))
                        lm = max(0.0, abs(mu + sd))
                        lat_ms = max(0.0, abs(__import__("random").gauss(mu, sd)))
                    elif d == "lognormal":
                        mu = float(dist_cfg.get("mean_ms", args.latency_mean_ms))
                        sd = float(dist_cfg.get("std_ms", args.latency_std_ms))
                        lat_ms = max(0.0, __import__("random").lognormvariate(mu, sd))
                    elif d == "uniform":
                        a = float(dist_cfg.get("min_ms", args.latency_min_ms))
                        b = float(dist_cfg.get("max_ms", args.latency_max_ms))
                        lat_ms = max(0.0, __import__("random").uniform(a, b))
                    else:
                        lat_ms = float(dist_cfg.get("ms", args.latency_ms))
                else:
                    d = args.latency_dist
                    if d == "normal":
                        lat_ms = max(0.0, __import__("random").gauss(args.latency_mean_ms, args.latency_std_ms))
                    elif d == "lognormal":
                        lat_ms = max(0.0, __import__("random").lognormvariate(args.latency_mean_ms, args.latency_std_ms))
                    elif d == "uniform":
                        lat_ms = max(0.0, __import__("random").uniform(args.latency_min_ms, args.latency_max_ms))
                    else:
                        lat_ms = float(args.latency_ms)
                fill_entry["latency_ms"] = lat_ms
                fill_entry["venue"] = venue if venue else None
                fills.append(fill_entry)
                total_qty += q
                total_px_qty += px * q
                if lat_ms > 0:
                    time.sleep(lat_ms / 1000.0)
                now_ts = datetime.utcnow()
                latencies.append(lat_ms)
            vwap = total_px_qty / total_qty if total_qty > 0 else 0.0
            order.avg_fill_price = vwap
            order.filled_quantity = order.quantity
        oid = engine.submit_order(order)
        status = engine.get_order_status(oid)
        if order.order_type == OrderType.MARKET:
            status["fills"] = fills
            status["vwap"] = order.avg_fill_price
            status["dollar_cost"] = order.avg_fill_price * order.filled_quantity
        results.append(status)
    summary = {}
    if results:
        tq = sum([r.get("filled_quantity", 0) or 0 for r in results if r])
        cost = sum([r.get("dollar_cost", 0) or 0 for r in results if r])
        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
        summary = {
            "total_orders": len(results),
            "total_quantity": tq,
            "avg_latency_ms": avg_lat,
            "total_dollar_cost": cost,
        }
    print(json.dumps({"results": results, "summary": summary}))


if __name__ == "__main__":
    main()
