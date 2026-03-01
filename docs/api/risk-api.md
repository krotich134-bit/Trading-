# Risk Engine API Specification

## Overview

The Risk Engine API provides endpoints for position sizing, risk calculations, portfolio monitoring, and circuit breaker management.

**Base URL:** `https://api.ai-trading.system/v1/risk`

**Authentication:** Bearer token (JWT)

---

## Endpoints

### Health Check

```http
GET /health
```

Returns the health status of the risk engine.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-02T10:30:00Z",
  "version": "1.2.3",
  "circuit_breakers": {
    "trading_halted": false,
    "current_drawdown": 0.03
  }
}
```

---

### Calculate Position Size

```http
POST /position-size
```

Calculate position size for a signal.

**Request Body:**
```json
{
  "signal_id": "sig_1234567890",
  "symbol": "AAPL",
  "current_price": 175.5,
  "stop_price": 170.0,
  "portfolio_equity": 100000,
  "sizing_method": "kelly",
  "risk_fraction": 0.01
}
```

**Response:**
```json
{
  "sizing_id": "size_1234567890",
  "signal_id": "sig_1234567890",
  "symbol": "AAPL",
  "quantity": 181,
  "dollar_risk": 995.5,
  "position_value": 31765.5,
  "leverage": 0.318,
  "risk_fraction": 0.00996,
  "sizing_method": "kelly",
  "metadata": {
    "kelly_fraction": 0.25,
    "win_probability": 0.52,
    "win_loss_ratio": 2.1
  },
  "approved": true,
  "approval_reason": "Within risk limits"
}
```

---

### Check Signal Risk

```http
POST /check-signal
```

Check if a signal passes all risk checks.

**Request Body:**
```json
{
  "signal_id": "sig_1234567890",
  "symbol": "AAPL",
  "position_size": 181,
  "entry_price": 175.5,
  "stop_price": 170.0
}
```

**Response:**
```json
{
  "approved": true,
  "reason": "Approved",
  "checks": {
    "position_count": {
      "passed": true,
      "current": 5,
      "limit": 20
    },
    "single_position": {
      "passed": true,
      "size_pct": 0.032,
      "limit": 0.10
    },
    "portfolio_heat": {
      "passed": true,
      "current": 0.08,
      "limit": 0.15
    },
    "per_trade_risk": {
      "passed": true,
      "risk_pct": 0.01,
      "limit": 0.02
    }
  }
}
```

---

### Get Portfolio Risk Metrics

```http
GET /portfolio/metrics
```

Get current portfolio risk metrics.

**Response:**
```json
{
  "timestamp": "2026-03-02T10:30:00Z",
  "portfolio": {
    "equity": 100000,
    "cash": 35000,
    "gross_exposure": 65000,
    "net_exposure": 45000,
    "long_exposure": 55000,
    "short_exposure": 10000
  },
  "risk": {
    "portfolio_heat": 0.085,
    "var_95": 0.14,
    "var_99": 0.21,
    "expected_shortfall": 0.18,
    "max_single_position": 0.055,
    "max_sector_exposure": 0.12
  },
  "drawdown": {
    "current": 0.03,
    "max": 0.08,
    "peak_equity": 103000
  },
  "correlation": {
    "avg_correlation": 0.45,
    "stress_triggered": false
  }
}
```

---

### Get Position Risk

```http
GET /positions/{symbol}/risk
```

Get risk metrics for a specific position.

**Response:**
```json
{
  "symbol": "AAPL",
  "position": {
    "quantity": 181,
    "entry_price": 175.5,
    "current_price": 178.0,
    "unrealized_pnl": 452.5
  },
  "risk": {
    "current_risk": 995.5,
    "risk_pct": 0.01,
    "stop_price": 170.0,
    "target_price": 185.0,
    "r_multiple": 0.45
  },
  "exposure": {
    "position_value": 32218,
    "position_pct": 0.032
  }
}
```

---

### Run Monte Carlo Simulation

```http
POST /monte-carlo/simulate
```

Run Monte Carlo simulation for risk analysis.

**Request Body:**
```json
{
  "n_trades": 1000,
  "n_sims": 20000,
  "win_probability": 0.52,
  "win_loss_ratio": 2.1,
  "risk_per_trade": 0.01,
  "starting_equity": 100000,
  "ruin_threshold": 0.20
}
```

**Response:**
```json
{
  "simulation_id": "mc_1234567890",
  "parameters": {
    "n_trades": 1000,
    "n_sims": 20000,
    "risk_per_trade": 0.01
  },
  "results": {
    "ruin_probability": 0.0005,
    "terminal_wealth_mean": 128450,
    "terminal_wealth_median": 125000,
    "terminal_wealth_std": 15230,
    "terminal_wealth_percentiles": {
      "5": 98500,
      "25": 115000,
      "50": 125000,
      "75": 140000,
      "95": 158000
    },
    "max_drawdown_mean": 0.085,
    "max_drawdown_median": 0.08,
    "max_drawdown_percentiles": {
      "95": 0.18
    },
    "probability_profit": 0.82,
    "probability_double": 0.15,
    "expected_return": 0.284
  }
}
```

---

### Get Circuit Breaker Status

```http
GET /circuit-breakers/status
```

Get current circuit breaker status.

**Response:**
```json
{
  "timestamp": "2026-03-02T10:30:00Z",
  "trading_halted": false,
  "halt_reason": null,
  "halt_time": null,
  "current_drawdown": 0.03,
  "peak_equity": 103000,
  "size_reduction_factor": 1.0,
  "limits": {
    "daily_loss": {
      "limit": 0.05,
      "current": 0.01,
      "remaining": 0.04
    },
    "monthly_loss": {
      "limit": 0.20,
      "current": 0.03,
      "remaining": 0.17
    },
    "quarterly_loss": {
      "limit": 0.30,
      "current": 0.03,
      "remaining": 0.27
    }
  },
  "throttling": {
    "drawdown_5pct": "normal",
    "drawdown_10pct": "normal",
    "drawdown_15pct": "normal"
  }
}
```

---

### Reset Circuit Breaker

```http
POST /circuit-breakers/reset
```

Reset circuit breaker (requires admin authorization).

**Request Body:**
```json
{
  "reason": "Manual reset after review",
  "authorized_by": "risk_manager_001"
}
```

**Response:**
```json
{
  "status": "reset",
  "timestamp": "2026-03-02T10:30:00Z",
  "previous_halt_reason": "15% drawdown reached",
  "reset_by": "risk_manager_001"
}
```

---

### Get Risk Limits

```http
GET /limits
```

Get current risk limit configuration.

**Response:**
```json
{
  "per_trade": {
    "max_risk_per_trade": 0.02,
    "default_risk_per_trade": 0.005
  },
  "position": {
    "max_single_position": 0.10,
    "max_sector_exposure": 0.25,
    "max_total_positions": 20
  },
  "portfolio": {
    "max_portfolio_heat": 0.15,
    "target_volatility": 0.10
  },
  "drawdown": {
    "daily_loss_limit": 0.05,
    "monthly_loss_limit": 0.20,
    "quarterly_loss_limit": 0.30
  },
  "circuit_breakers": {
    "correlation_threshold": 0.70,
    "vol_stress_multiplier": 1.5
  }
}
```

---

### Update Risk Limits

```http
PUT /limits
```

Update risk limits (requires admin authorization).

**Request Body:**
```json
{
  "per_trade": {
    "max_risk_per_trade": 0.015,
    "default_risk_per_trade": 0.005
  },
  "position": {
    "max_single_position": 0.08
  }
}
```

**Response:**
```json
{
  "status": "updated",
  "timestamp": "2026-03-02T10:30:00Z",
  "updated_limits": {
    "per_trade.max_risk_per_trade": 0.015,
    "position.max_single_position": 0.08
  },
  "updated_by": "risk_manager_001"
}
```

---

### Kelly Analysis

```http
POST /kelly/analyze
```

Analyze Kelly criterion for given parameters.

**Request Body:**
```json
{
  "win_probability": 0.52,
  "win_loss_ratio": 2.1,
  "risk_fractions": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
}
```

**Response:**
```json
{
  "full_kelly": 0.242,
  "half_kelly": 0.121,
  "quarter_kelly": 0.06,
  "analysis": [
    {
      "risk_fraction": 0.05,
      "kelly_fraction": 0.207,
      "geometric_growth_rate": 0.023
    },
    {
      "risk_fraction": 0.121,
      "kelly_fraction": 0.5,
      "geometric_growth_rate": 0.045
    },
    {
      "risk_fraction": 0.242,
      "kelly_fraction": 1.0,
      "geometric_growth_rate": 0.052
    }
  ],
  "recommendation": "Use Quarter-Kelly (0.06) for conservative sizing"
}
```

---

## WebSocket API

### Real-time Risk Updates

Connect to WebSocket for real-time risk updates.

```
wss://ws.ai-trading.system/v1/risk
```

**Subscribe Message:**
```json
{
  "action": "subscribe",
  "channels": ["portfolio", "circuit_breakers", "positions"]
}
```

**Portfolio Update:**
```json
{
  "type": "portfolio",
  "data": {
    "timestamp": "2026-03-02T10:30:00Z",
    "portfolio_heat": 0.085,
    "current_drawdown": 0.03
  }
}
```

**Circuit Breaker Alert:**
```json
{
  "type": "circuit_breaker",
  "data": {
    "timestamp": "2026-03-02T10:30:00Z",
    "trading_halted": true,
    "reason": "Daily loss limit exceeded",
    "current_loss": 0.052
  }
}
```

---

## Rate Limits

- **REST API:** 1000 requests per minute
- **WebSocket:** 50 messages per second
- **Monte Carlo:** 10 simulations per minute

---

## Error Codes

| Code | Description |
|------|-------------|
| `RISK_LIMIT_EXCEEDED` | Signal exceeds risk limits |
| `TRADING_HALTED` | Trading is currently halted |
| `INSUFFICIENT_EQUITY` | Not enough equity for position |
| `POSITION_LIMIT_REACHED` | Maximum position count reached |
| `UNAUTHORIZED` | Admin authorization required |

---

## Data Models

### PositionSizingResult

| Field | Type | Description |
|-------|------|-------------|
| `sizing_id` | string | Unique sizing identifier |
| `quantity` | float | Recommended position quantity |
| `dollar_risk` | float | Dollar amount at risk |
| `position_value` | float | Total position value |
| `leverage` | float | Position leverage |
| `risk_fraction` | float | Risk as fraction of equity |
| `approved` | boolean | Whether sizing is approved |

### RiskMetrics

| Field | Type | Description |
|-------|------|-------------|
| `portfolio_heat` | float | sqrt(r^T Σ r) |
| `var_95` | float | 95% Value at Risk |
| `var_99` | float | 99% Value at Risk |
| `expected_shortfall` | float | Conditional VaR |
| `current_drawdown` | float | Current drawdown |
| `max_drawdown` | float | Maximum historical drawdown |
