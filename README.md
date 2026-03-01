# AI Trading System - Research & Edge Detection Platform

A comprehensive, production-ready trading system designed to detect small, persistent statistical edges while prioritizing capital preservation through robust risk management.

## 🎯 Mission Statement

**"Survival first, compounding second."**

This system targets probabilistic expected value, not guaranteed outcomes. Expected alpha is modest (0.5-3% annualized) and fragile; costs, slippage, and correlation spikes can erase gross edge. Long-run success depends on preserving capital through adverse regimes so compounding can continue.

## 📊 System Overview

### Key Differentiators

- **Sub-50ms Signal Path Latency**: Optimized for real-time trading
- **Mathematical Risk Framework**: Kelly Criterion, CPPI, Monte Carlo ruin analysis
- **Human-in-the-Loop Execution**: No autonomous trading; human approval required
- **Immutable Audit Trails**: Cryptographically signed, tamper-evident logging
- **Walk-Forward Validation**: Prevents overfitting through proper cross-validation

### Performance Targets

| Metric | Target |
|--------|--------|
| Signal Latency | < 45ms |
| Sharpe Ratio | > 1.0 |
| Max Drawdown | < 15% |
| Net Alpha | > 0.5% |
| System Uptime | > 99.9% |

## 🏗️ Architecture

### High-Level Design

```
[Data Sources] → [Ingestion] → [Feature Store] → [Signal Engine] → [Risk Engine] → [Execution] → [Brokers]
                     ↓                ↓               ↓              ↓              ↓
               [Data Lake]    [Model Registry]  [Position Sizing] [Order Mgmt]  [Audit Logs]
```

### Core Components

1. **Signal Engine**: Multi-strategy signal generation (momentum, mean reversion, stat arb, volatility)
2. **Risk Engine**: Position sizing, portfolio heat, circuit breakers, Monte Carlo simulation
3. **Feature Store**: Point-in-time feature engineering with strict temporal discipline
4. **Backtesting Framework**: Walk-forward optimization with realistic slippage/impact models
5. **Execution Layer**: Smart order routing with throttling and idempotent handling

### Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Data Processing | Pandas, Polars, Spark |
| ML Models | XGBoost, LightGBM, PyTorch |
| Database | TimescaleDB, PostgreSQL, Redis |
| Message Bus | Apache Kafka (MSK) |
| Cloud | AWS (ECS/EKS, S3, MSK, ElastiCache) |
| Monitoring | Prometheus, Grafana, CloudWatch |

## 📁 Repository Structure

```
ai_trading_system/
├── src/                          # Source code
│   ├── common/                   # Shared utilities and types
│   ├── signal/                   # Signal generation engine
│   │   ├── features.py           # Feature engineering
│   │   ├── strategies.py         # Trading strategies
│   │   └── ensemble.py           # Signal ensemble methods
│   ├── risk/                     # Risk management
│   │   ├── position_sizing.py    # Position sizing algorithms
│   │   ├── risk_manager.py       # Portfolio risk controls
│   │   ├── stop_loss.py          # Stop loss management
│   │   └── monte_carlo.py        # Monte Carlo simulation
│   ├── backtest/                 # Backtesting framework
│   │   ├── engine.py             # Backtest engine
│   │   ├── walk_forward.py       # Walk-forward optimizer
│   │   ├── metrics.py            # Performance metrics
│   │   └── slippage.py           # Slippage models
│   └── execution/                # Execution layer
├── infrastructure/               # Infrastructure as Code
│   ├── terraform/                # AWS infrastructure
│   ├── kubernetes/               # K8s manifests
│   └── ci-cd/                    # CI/CD pipelines
├── docs/                         # Documentation
│   ├── api/                      # API specifications
│   ├── runbooks/                 # Operational runbooks
│   └── compliance/               # Compliance documentation
├── diagrams/                     # Architecture diagrams
├── presentation/                 # Executive presentation
├── notebooks/                    # Jupyter notebooks
└── tests/                        # Test suite
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker
- AWS CLI
- kubectl
- Terraform

### Installation

```bash
# Clone repository
git clone https://github.com/ai-trading/system.git
cd ai_trading_system

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

### Running Tests

```bash
# Run unit tests
pytest tests/unit -v

# Run integration tests
pytest tests/integration -v

# Run with coverage
pytest --cov=src --cov-report=html
```

### Running Backtests

```python
from src.backtest.engine import BacktestEngine, BacktestConfig
from src.signal.strategies import MomentumStrategy
from src.risk.position_sizing import FixedFractionalSizer

# Configure backtest
config = BacktestConfig(
    initial_capital=100000,
    commission_rate=0.001,
    slippage_model="fixed",
    slippage_bps=1.0
)

# Create engine
engine = BacktestEngine(config)

# Run backtest
strategy = MomentumStrategy()
sizer = FixedFractionalSizer(risk_fraction=0.01)

metrics = engine.run(data, strategy.generate_signal, sizer)
print(metrics.summary())
```

### Monte Carlo Simulation

```python
from src.risk.monte_carlo import MonteCarloSimulator

# Run simulation
sim = MonteCarloSimulator(seed=42)
results = sim.simulate_fixed_parameters(
    n_trades=1000,
    n_sims=20000,
    win_probability=0.52,
    win_loss_ratio=2.1,
    risk_per_trade=0.01,
    starting_equity=100000
)

print(results.summary())
```

## 📈 Position Sizing Algorithms

The system implements multiple position sizing frameworks:

### 1. Fixed Fractional Sizing
```python
from src.risk.position_sizing import FixedFractionalSizer

sizer = FixedFractionalSizer(risk_fraction=0.01)  # 1% risk per trade
```

### 2. Kelly Criterion (Constrained)
```python
from src.risk.position_sizing import KellySizer

sizer = KellySizer(
    win_probability=0.52,
    win_loss_ratio=2.1,
    kelly_fraction=0.25  # Quarter-Kelly for safety
)
```

### 3. Volatility Targeting
```python
from src.risk.position_sizing import VolatilityTargetSizer

sizer = VolatilityTargetSizer(
    target_volatility=0.10,  # 10% annualized
    max_leverage=2.0
)
```

### 4. CPPI (Constant Proportion Portfolio Insurance)
```python
from src.risk.position_sizing import CPPISizer

sizer = CPPISizer(
    floor_fraction=0.90,  # 90% of peak equity
    multiplier=3.0
)
```

## 🛡️ Risk Management

### Circuit Breakers

| Condition | Action |
|-----------|--------|
| -5% daily loss | 50% size reduction |
| -10% drawdown | 75% size reduction |
| -15% drawdown | Halt new positions |
| -20% monthly | Full shutdown + review |

### Portfolio Heat Calculation

```
Portfolio Heat = √(r^T × Σ × r)

Where:
- r = vector of per-position risk budgets
- Σ = correlation matrix
```

### Recovery Mathematics

For drawdown fraction D, required recovery gain:
```
G_recover = D / (1 - D)

Examples:
- 10% drawdown → 11.1% recovery needed
- 20% drawdown → 25.0% recovery needed
- 50% drawdown → 100.0% recovery needed
```

## 🔧 Infrastructure

### AWS Deployment

```bash
# Initialize Terraform
cd infrastructure/terraform
terraform init

# Plan deployment
terraform plan -var-file=environments/production.tfvars

# Apply deployment
terraform apply -var-file=environments/production.tfvars
```

### Kubernetes Deployment

```bash
# Apply manifests
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/signal-engine.yaml
kubectl apply -f infrastructure/kubernetes/risk-engine.yaml

# Verify deployment
kubectl get pods -n ai-trading
kubectl get services -n ai-trading
```

## 📊 Monitoring

### Key Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| Signal Latency (p99) | < 50ms | > 100ms |
| Portfolio Heat | < 10% | > 12% |
| Current Drawdown | < 5% | > 5% |
| System Uptime | > 99.9% | Any downtime |

### Grafana Dashboards

Access dashboards at: `https://grafana.ai-trading.system`

- Trading Performance
- Risk Metrics
- System Health
- Data Quality

## 📚 Documentation

- [API Specification - Signal Engine](docs/api/signal-api.md)
- [API Specification - Risk Engine](docs/api/risk-api.md)
- [Operational Runbook](docs/runbooks/operations.md)
- [Compliance Package](docs/compliance/compliance-package.md)

## 🎓 Research Methodology

### Walk-Forward Optimization

```python
from src.backtest.walk_forward import WalkForwardOptimizer, WalkForwardConfig

config = WalkForwardConfig(
    train_size=252,      # 1 year training
    test_size=63,        # 3 months testing
    step_size=21,        # Monthly rebalancing
    window_type="rolling"
)

wfo = WalkForwardOptimizer(config)
results = wfo.run(
    data=data,
    strategy_class=MomentumStrategy,
    param_grid=param_grid,
    backtest_config=backtest_config
)
```

### Leakage Prevention

- Strict point-in-time joins
- No future timestamp features
- Rolling/expanding windows only
- Parameter updates at rebalance checkpoints

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Standards

- PEP 8 style guide
- Type hints required
- Unit tests mandatory
- Documentation required

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [QuantStart](https://www.quantstart.com/) for algorithmic trading resources
- [Advances in Financial Machine Learning](https://www.amazon.com/Advances-Financial-Machine-Learning-Marcos/dp/1119482089) by Marcos López de Prado
- [Quantitative Trading](https://www.amazon.com/Quantitative-Trading-Build-Algorithmic-Business/dp/0470284889) by Ernest P. Chan

## 📞 Contact

- **Engineering Team:** engineering@ai-trading.system
- **Risk Management:** risk@ai-trading.system
- **Compliance:** compliance@ai-trading.system

---

**Disclaimer:** This system targets probabilistic expected value, not guaranteed outcomes. Trading involves substantial risk of loss. Past performance is not indicative of future results.
