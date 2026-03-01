# Signal Engine API Specification

## Overview

The Signal Engine API provides endpoints for generating trading signals, managing strategies, and retrieving signal history.

**Base URL:** `https://api.ai-trading.system/v1`

**Authentication:** Bearer token (JWT)

---

## Endpoints

### Health Check

```http
GET /health
```

Returns the health status of the signal engine.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-02T10:30:00Z",
  "version": "1.2.3",
  "uptime_seconds": 86400
}
```

---

### Generate Signal

```http
POST /signals/generate
```

Generate a trading signal for a specific symbol.

**Request Body:**
```json
{
  "symbol": "AAPL",
  "strategy_id": "momentum",
  "parameters": {
    "lookback": 20,
    "confidence_threshold": 0.6
  }
}
```

**Response:**
```json
{
  "signal_id": "sig_1234567890",
  "symbol": "AAPL",
  "timestamp": "2026-03-02T10:30:00Z",
  "signal_type": "buy",
  "confidence": 0.75,
  "expected_return": 2.5,
  "half_life_seconds": 3600,
  "strategy_id": "momentum",
  "suggested_stop": 170.0,
  "suggested_target": 180.0,
  "metadata": {
    "momentum_score": 0.85,
    "trend_strength": 28.5
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Symbol not found
- `429 Too Many Requests`: Rate limit exceeded

---

### Get Signal by ID

```http
GET /signals/{signal_id}
```

Retrieve a specific signal by its ID.

**Response:**
```json
{
  "signal_id": "sig_1234567890",
  "symbol": "AAPL",
  "timestamp": "2026-03-02T10:30:00Z",
  "signal_type": "buy",
  "confidence": 0.75,
  "expected_return": 2.5,
  "half_life_seconds": 3600,
  "strategy_id": "momentum",
  "status": "active",
  "decay_weight": 0.85
}
```

---

### List Signals

```http
GET /signals
```

List signals with optional filters.

**Query Parameters:**
- `symbol` (string): Filter by symbol
- `strategy_id` (string): Filter by strategy
- `signal_type` (string): Filter by type (buy/sell/hold)
- `from` (datetime): Start timestamp
- `to` (datetime): End timestamp
- `limit` (integer): Max results (default: 100, max: 1000)
- `offset` (integer): Pagination offset

**Response:**
```json
{
  "signals": [
    {
      "signal_id": "sig_1234567890",
      "symbol": "AAPL",
      "timestamp": "2026-03-02T10:30:00Z",
      "signal_type": "buy",
      "confidence": 0.75,
      "strategy_id": "momentum"
    }
  ],
  "total": 150,
  "limit": 100,
  "offset": 0
}
```

---

### Get Strategy Status

```http
GET /strategies/{strategy_id}/status
```

Get the current status of a strategy.

**Response:**
```json
{
  "strategy_id": "momentum",
  "name": "Momentum Strategy",
  "status": "active",
  "is_active": true,
  "confidence_threshold": 0.6,
  "parameters": {
    "lookback_periods": [20, 60, 120],
    "adx_threshold": 25
  },
  "performance": {
    "total_signals": 1500,
    "avg_confidence": 0.68,
    "win_rate": 0.52
  },
  "last_signal_time": "2026-03-02T10:30:00Z"
}
```

---

### List Strategies

```http
GET /strategies
```

List all available strategies.

**Response:**
```json
{
  "strategies": [
    {
      "strategy_id": "momentum",
      "name": "Momentum Strategy",
      "status": "active",
      "description": "Time-series and cross-sectional momentum"
    },
    {
      "strategy_id": "mean_reversion",
      "name": "Mean Reversion",
      "status": "active",
      "description": "Bollinger band mean reversion"
    },
    {
      "strategy_id": "stat_arb",
      "name": "Statistical Arbitrage",
      "status": "inactive",
      "description": "Cointegrated pairs trading"
    }
  ]
}
```

---

### Update Strategy

```http
PUT /strategies/{strategy_id}
```

Update strategy parameters.

**Request Body:**
```json
{
  "is_active": true,
  "confidence_threshold": 0.7,
  "parameters": {
    "lookback_periods": [20, 60],
    "adx_threshold": 30
  }
}
```

**Response:**
```json
{
  "strategy_id": "momentum",
  "status": "updated",
  "message": "Strategy parameters updated successfully"
}
```

---

### Get Ensemble Signal

```http
POST /signals/ensemble
```

Generate an ensemble signal combining multiple strategies.

**Request Body:**
```json
{
  "symbol": "AAPL",
  "ensemble_method": "confidence_weighted",
  "strategy_ids": ["momentum", "mean_reversion", "volatility"]
}
```

**Response:**
```json
{
  "signal_id": "ens_1234567890",
  "symbol": "AAPL",
  "timestamp": "2026-03-02T10:30:00Z",
  "signal_type": "buy",
  "confidence": 0.72,
  "expected_return": 2.2,
  "ensemble_method": "confidence_weighted",
  "component_signals": {
    "momentum": {
      "signal_type": "buy",
      "confidence": 0.75,
      "weight": 0.4
    },
    "mean_reversion": {
      "signal_type": "hold",
      "confidence": 0.3,
      "weight": 0.3
    },
    "volatility": {
      "signal_type": "buy",
      "confidence": 0.8,
      "weight": 0.3
    }
  }
}
```

---

## WebSocket API

### Real-time Signals

Connect to WebSocket for real-time signal updates.

```
wss://ws.ai-trading.system/v1/signals
```

**Authentication:** Bearer token in query parameter

**Subscribe Message:**
```json
{
  "action": "subscribe",
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "strategies": ["momentum", "mean_reversion"]
}
```

**Signal Update:**
```json
{
  "type": "signal",
  "data": {
    "signal_id": "sig_1234567890",
    "symbol": "AAPL",
    "timestamp": "2026-03-02T10:30:00Z",
    "signal_type": "buy",
    "confidence": 0.75
  }
}
```

---

## Rate Limits

- **REST API:** 1000 requests per minute
- **WebSocket:** 100 messages per second
- **Signal Generation:** 100 signals per minute per symbol

---

## Error Codes

| Code | Description |
|------|-------------|
| `INVALID_SYMBOL` | Symbol not recognized |
| `INVALID_STRATEGY` | Strategy ID not found |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `INSUFFICIENT_DATA` | Not enough historical data |
| `STRATEGY_INACTIVE` | Strategy is not active |

---

## Data Models

### Signal

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | string | Unique signal identifier |
| `symbol` | string | Trading symbol |
| `timestamp` | datetime | Signal generation time |
| `signal_type` | enum | buy, sell, hold, exit |
| `confidence` | float | 0.0 to 1.0 |
| `expected_return` | float | Expected return in R multiples |
| `half_life_seconds` | float | Signal decay half-life |
| `strategy_id` | string | Source strategy |
| `suggested_stop` | float | Recommended stop price |
| `suggested_target` | float | Recommended target price |
| `metadata` | object | Strategy-specific data |

### Strategy

| Field | Type | Description |
|-------|------|-------------|
| `strategy_id` | string | Unique strategy identifier |
| `name` | string | Human-readable name |
| `status` | enum | active, inactive, paused |
| `confidence_threshold` | float | Minimum confidence for signals |
| `parameters` | object | Strategy-specific parameters |
| `performance` | object | Historical performance metrics |
