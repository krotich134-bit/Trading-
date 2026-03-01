from typing import Dict
import pandas as pd

CANON = {
    "open": ["open", "o", "price_open"],
    "high": ["high", "h", "price_high"],
    "low": ["low", "l", "price_low"],
    "close": ["close", "c", "price_close", "adj_close", "adjusted_close"],
    "volume": ["volume", "vol", "turnover"],
}

TIME_FIELDS = ["timestamp", "date", "datetime", "time", "trade_date"]

def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    cols = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.copy()
    df.columns = cols
    mapped: Dict[str, str] = {}
    for k, variants in CANON.items():
        for v in variants:
            if v in df.columns:
                mapped[k] = v
                break
    if "close" not in mapped and "adj_close" in df.columns:
        mapped["close"] = "adj_close"
    rename_map = {}
    for k, v in mapped.items():
        if v != k:
            rename_map[v] = k
    if rename_map:
        df = df.rename(columns=rename_map)
    tf = None
    for t in TIME_FIELDS:
        if t in df.columns:
            tf = t
            break
    if tf:
        df[tf] = pd.to_datetime(df[tf])
        df = df.set_index(df[tf])
        df = df.drop(columns=[tf])
    for req in ["open", "high", "low", "close"]:
        if req not in df.columns:
            raise ValueError("missing column: " + req)
    if "volume" not in df.columns:
        df["volume"] = 0
    return df

