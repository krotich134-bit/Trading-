# Data Formats

This guide shows how to provide OHLCV data for the backtest CLI.

## CSV Example

Required columns: open, high, low, close. Optional: volume. Timestamp column can be timestamp or date.

```csv
timestamp,open,high,low,close,volume
2024-01-02,100.0,101.0,99.5,100.5,1200000
2024-01-03,100.5,101.2,99.8,100.9,1300000
```

## Parquet Example

Parquet files may have vendor-specific column names. The loader normalizes common variants like Open, High, Low, Close, Adj Close, Date, Timestamp.

## Multi-File Usage

```
ai-trading-backtest --files "C:\data\aapl.parquet,C:\data\msft.csv" --symbols AAPL,MSFT
```

## Stat-Arb Pairs

```
ai-trading-backtest --enable-statarb --pairs "AAPL:MSFT;MSFT:AAPL"
```

or JSON:

```json
{
  "AAPL": "MSFT",
  "MSFT": "AAPL"
}
```

