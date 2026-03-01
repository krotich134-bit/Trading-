# AI Trading System - Operational Runbook

## Table of Contents

1. [System Overview](#system-overview)
2. [Daily Operations](#daily-operations)
3. [Incident Response](#incident-response)
4. [Circuit Breaker Procedures](#circuit-breaker-procedures)
5. [Deployment Procedures](#deployment-procedures)
6. [Monitoring and Alerting](#monitoring-and-alerting)
7. [Backup and Recovery](#backup-and-recovery)

---

## System Overview

### Architecture Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Signal Engine | Python/ECS | Generate trading signals |
| Risk Engine | Python/ECS | Position sizing and risk checks |
| Feature Store | Redis/TimescaleDB | Feature storage and retrieval |
| Message Bus | MSK (Kafka) | Event streaming |
| Data Lake | S3 | Historical data storage |

### Critical Dependencies

- **Market Data Feeds**: Real-time price data
- **Kafka Cluster**: Message streaming
- **Redis Cache**: Feature cache
- **TimescaleDB**: Time-series data

---

## Daily Operations

### Pre-Market Checklist (8:00 AM ET)

```bash
#!/bin/bash
# pre_market_check.sh

echo "=== Pre-Market System Check ==="

# Check system health
curl -f https://api.ai-trading.system/v1/health
curl -f https://api.ai-trading.system/v1/risk/health

# Check circuit breaker status
curl https://api.ai-trading.system/v1/risk/circuit-breakers/status

# Check portfolio risk metrics
curl https://api.ai-trading.system/v1/risk/portfolio/metrics

# Verify data freshness
kubectl exec -it redis-pod -- redis-cli ping
kubectl exec -it timescaledb-pod -- pg_isready

# Check Kafka lag
kafka-consumer-groups.sh --bootstrap-server $KAFKA_BROKERS --describe --group signal-engine

echo "=== Pre-Market Check Complete ==="
```

### Market Hours Monitoring (9:30 AM - 4:00 PM ET)

**Key Metrics to Monitor:**

1. **Signal Latency**
   - Target: < 50ms
   - Alert: > 100ms
   - Critical: > 200ms

2. **Portfolio Heat**
   - Target: < 10%
   - Alert: > 12%
   - Critical: > 15%

3. **Current Drawdown**
   - Normal: < 5%
   - Alert: > 5%
   - Critical: > 10%

4. **System Uptime**
   - Target: > 99.9%
   - Alert: Any downtime

### Post-Market Procedures (4:30 PM ET)

1. **Generate Daily Report**
```bash
python scripts/generate_daily_report.py --date $(date +%Y-%m-%d)
```

2. **Verify Trade Reconciliation**
```bash
python scripts/reconcile_trades.py --date $(date +%Y-%m-%d)
```

3. **Backup Critical Data**
```bash
# Backup TimescaleDB
pg_dump -h $DB_HOST -U $DB_USER trading_data > backups/trading_data_$(date +%Y%m%d).sql

# Backup Redis
kubectl exec -it redis-pod -- redis-cli BGSAVE
```

---

## Incident Response

### Severity Levels

| Level | Description | Response Time | Escalation |
|-------|-------------|---------------|------------|
| P1 | Trading halted, data loss | 5 minutes | Immediate |
| P2 | Degraded performance | 15 minutes | 30 minutes |
| P3 | Minor issues | 1 hour | 4 hours |
| P4 | Cosmetic issues | 24 hours | Next business day |

### Common Incidents

#### 1. Signal Engine Down

**Symptoms:**
- No new signals generated
- Health check failing
- High Kafka lag

**Response:**
```bash
# Check pod status
kubectl get pods -n ai-trading -l app=signal-engine

# Check logs
kubectl logs -n ai-trading -l app=signal-engine --tail=100

# Restart if necessary
kubectl rollout restart deployment/signal-engine -n ai-trading

# Verify recovery
kubectl rollout status deployment/signal-engine -n ai-trading
```

#### 2. Risk Engine Circuit Breaker Triggered

**Symptoms:**
- Trading halted
- Circuit breaker status: `trading_halted: true`

**Response:**
```bash
# Check current status
curl https://api.ai-trading.system/v1/risk/circuit-breakers/status

# Review drawdown and losses
curl https://api.ai-trading.system/v1/risk/portfolio/metrics

# DO NOT reset without risk manager approval
# If approved, reset with authorization:
curl -X POST https://api.ai-trading.system/v1/risk/circuit-breakers/reset \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "reason": "Manual reset after review",
    "authorized_by": "risk_manager_001"
  }'
```

#### 3. High Latency

**Symptoms:**
- Signal latency > 100ms
- Slow order execution

**Response:**
```bash
# Check Kafka consumer lag
kafka-consumer-groups.sh --bootstrap-server $KAFKA_BROKERS --describe

# Check Redis latency
redis-cli --latency -h $REDIS_HOST

# Check database performance
kubectl exec -it timescaledb-pod -- psql -c "SELECT * FROM pg_stat_activity;"

# Scale up if needed
kubectl scale deployment/signal-engine --replicas=5 -n ai-trading
```

#### 4. Data Feed Disruption

**Symptoms:**
- Stale market data
- Missing ticks

**Response:**
```bash
# Check data freshness
python scripts/check_data_freshness.py

# Switch to backup feed if available
kubectl apply -f k8s/config/backup-feed-config.yaml

# Alert data vendor
# Contact: vendor-support@datavendor.com
```

---

## Circuit Breaker Procedures

### Automatic Triggers

| Condition | Action | Recovery |
|-----------|--------|----------|
| -5% daily loss | 50% size reduction | Manual reset after review |
| -10% drawdown | 75% size reduction | Manual reset after review |
| -15% drawdown | Halt new positions | Risk manager approval required |
| -20% monthly | Full shutdown | Governance review required |

### Manual Override

**⚠️ WARNING: Manual override should be used only in emergency situations**

```bash
# Requires admin authorization
curl -X POST https://api.ai-trading.system/v1/risk/circuit-breakers/reset \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Emergency-Override: true" \
  -d '{
    "reason": "Emergency market conditions",
    "authorized_by": "risk_manager_001",
    "emergency_type": "market_crash"
  }'
```

**Audit Trail:**
- All overrides are logged
- Requires two-person authorization
- Post-incident review mandatory

---

## Deployment Procedures

### Pre-Deployment Checklist

- [ ] All tests passing
- [ ] Security scan clean
- [ ] Database migrations prepared
- [ ] Rollback plan documented
- [ ] Change approval obtained

### Deployment Steps

```bash
#!/bin/bash
# deploy.sh

ENVIRONMENT=$1
VERSION=$2

echo "Deploying version $VERSION to $ENVIRONMENT"

# 1. Update kubeconfig
aws eks update-kubeconfig --name ai-trading-$ENVIRONMENT

# 2. Deploy canary (10% traffic)
kubectl apply -f k8s/canary/
sleep 60

# 3. Run smoke tests
./scripts/smoke_tests.sh

# 4. Promote to full deployment
kubectl set image deployment/signal-engine \
  signal-engine=$ECR_REGISTRY/ai-trading/signal-engine:$VERSION \
  -n ai-trading

kubectl set image deployment/risk-engine \
  risk-engine=$ECR_REGISTRY/ai-trading/risk-engine:$VERSION \
  -n ai-trading

# 5. Verify rollout
kubectl rollout status deployment/signal-engine -n ai-trading --timeout=300s
kubectl rollout status deployment/risk-engine -n ai-trading --timeout=300s

# 6. Run integration tests
./scripts/integration_tests.sh

echo "Deployment complete"
```

### Rollback Procedure

```bash
#!/bin/bash
# rollback.sh

ENVIRONMENT=$1

echo "Rolling back $ENVIRONMENT"

# Rollback deployments
kubectl rollout undo deployment/signal-engine -n ai-trading
kubectl rollout undo deployment/risk-engine -n ai-trading

# Verify rollback
kubectl rollout status deployment/signal-engine -n ai-trading
kubectl rollout status deployment/risk-engine -n ai-trading

# Notify team
slack-notify "#trading-alerts" "Rollback completed for $ENVIRONMENT"
```

---

## Monitoring and Alerting

### Key Metrics Dashboard

**Grafana Dashboard:** `https://grafana.ai-trading.system/d/trading`

**Key Panels:**
1. Signal Latency (p50, p95, p99)
2. Portfolio Heat
3. Current Drawdown
4. System Uptime
5. Kafka Consumer Lag
6. Error Rate

### Alert Rules

```yaml
# prometheus-alerts.yaml
groups:
- name: trading-alerts
  rules:
  - alert: HighSignalLatency
    expr: signal_latency_p99 > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High signal latency detected"
      
  - alert: TradingHalted
    expr: circuit_breaker_trading_halted == 1
    for: 0m
    labels:
      severity: critical
    annotations:
      summary: "Trading has been halted"
      
  - alert: HighDrawdown
    expr: current_drawdown > 0.10
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Drawdown exceeded 10%"
      
  - alert: DatabaseConnectionFailed
    expr: up{job="timescaledb"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Database connection failed"
```

### On-Call Rotation

| Day | Primary | Secondary |
|-----|---------|-----------|
| Mon-Wed | Engineer A | Engineer B |
| Thu-Sun | Engineer B | Engineer C |

**Escalation Path:**
1. On-call engineer (5 min)
2. Secondary on-call (15 min)
3. Engineering manager (30 min)
4. CTO (1 hour)

---

## Backup and Recovery

### Backup Schedule

| Data | Frequency | Retention |
|------|-----------|-----------|
| TimescaleDB | Daily | 30 days |
| Redis | Hourly | 7 days |
| Kafka | Real-time | 7 days |
| S3 Data Lake | Versioned | 90 days |

### Recovery Procedures

#### Database Recovery

```bash
# Restore from backup
psql -h $DB_HOST -U $DB_USER trading_data < backups/trading_data_20260301.sql

# Verify data integrity
psql -h $DB_HOST -U $DB_USER -c "SELECT COUNT(*) FROM trades;"
```

#### Kafka Recovery

```bash
# Restore consumer offsets
kafka-consumer-groups.sh --bootstrap-server $KAFKA_BROKERS \
  --group signal-engine \
  --reset-offsets --to-datetime 2026-03-01T00:00:00.000
```

#### Full System Recovery

```bash
# 1. Restore infrastructure
terraform apply -var-file=environments/production.tfvars

# 2. Restore databases
./scripts/restore_databases.sh

# 3. Deploy applications
./scripts/deploy.sh production latest

# 4. Verify system health
./scripts/health_check.sh
```

---

## Contact Information

| Role | Name | Contact |
|------|------|---------|
| Engineering Manager | John Smith | john@ai-trading.system |
| Risk Manager | Jane Doe | jane@ai-trading.system |
| On-Call Hotline | - | +1-555-TRADING |
| AWS Support | - | aws-support@amazon.com |

---

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-03-02 | 1.0 | Engineering Team | Initial release |
