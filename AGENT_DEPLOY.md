# Agent Quick Deploy Guide | Agent 快速部署指南

This document is designed for AI agents to quickly understand and deploy the Crypto Portfolio tracker.

---

## Project Overview | 项目概述

**Purpose**: Aggregate crypto assets from multiple exchanges and on-chain wallets into a SQLite database.

**Tech Stack**: Python 3 + SQLite + Node.js (Puppeteer for wallet scraping)

**Key Files**:
```
crypto-portfolio/
├── config/
│   ├── secrets.yaml          # API keys (NEVER commit)
│   ├── secrets.yaml.example  # Template
│   ├── wallets.yaml          # Wallet addresses (NEVER commit)
│   └── wallets.yaml.example  # Template
├── src/
│   ├── collector.py          # Main entry point
│   ├── debank_scraper.js     # Wallet scraper
│   ├── collectors/           # Exchange adapters
│   │   ├── binance.py
│   │   ├── bitget.py
│   │   ├── bybit.py
│   │   └── okx.py
│   └── db/
│       ├── database.py       # DB operations
│       └── schema.sql        # Table definitions
├── portfolio.db              # SQLite database (generated)
├── requirements.txt          # Python deps
└── package.json              # Node deps
```

---

## Quick Deploy Steps | 快速部署步骤

### 1. Environment Setup

```bash
# Check Python version (need 3.8+)
python3 --version

# Check Node.js version (need 18+)
node --version

# Install dependencies
pip install -r requirements.txt
npm install
```

### 2. Configuration

```bash
# Copy templates
cp config/secrets.yaml.example config/secrets.yaml
cp config/wallets.yaml.example config/wallets.yaml
```

**Required Config**:
- `config/secrets.yaml`: Fill in exchange API keys (read-only)
- `config/wallets.yaml`: Add wallet addresses to track

### 3. Initialize Database

```bash
# Database auto-initializes on first run
cd src && python3 collector.py
```

### 4. Verify Installation

```bash
# Check summary
python3 collector.py summary
```

---

## Critical Rules | 关键规则

### ⚠️ Debt Calculation

The `balances` table stores debt with `is_debt=1`. The `value_usd` is **positive** but must be **subtracted**:

```sql
-- WRONG
SELECT SUM(value_usd) FROM balances;

-- CORRECT
SELECT 
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE -value_usd END) as net_value
FROM balances 
WHERE snapshot_id = ?;
```

### ⚠️ Stablecoin Merging

When reporting, merge stablecoins: USDT, USDC, USD1, BYUSDT, USDE → show as "Stablecoins"

### ⚠️ Source Merging

Same coin across multiple exchanges should be merged in reports.

---

## Common Commands | 常用命令

```bash
# Full collection
cd src && python3 collector.py

# View latest summary
python3 collector.py summary

# Weekly report
python3 collector.py weekly

# Check expiring assets
python3 collector.py check-expiry
```

---

## Database Queries | 常用查询

### Latest Snapshot

```sql
SELECT * FROM snapshots ORDER BY collected_at DESC LIMIT 1;
```

### Net Value by Coin

```sql
SELECT coin,
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE 0 END) as assets,
  SUM(CASE WHEN is_debt=1 THEN value_usd ELSE 0 END) as debt,
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE -value_usd END) as net
FROM balances 
WHERE snapshot_id = (SELECT id FROM snapshots ORDER BY collected_at DESC LIMIT 1)
GROUP BY coin 
ORDER BY net DESC;
```

### Manual Entries

```sql
SELECT project, coin, quantity, expires_at 
FROM manual_entries 
WHERE is_active = 1;
```

### Add Manual Entry

```sql
INSERT INTO manual_entries (project, coin, quantity, price_usd, value_usd, notes, expires_at)
VALUES ('Staking', 'ETH', 10.5, 3000, 31500, 'Locked staking', '2026-12-31');
```

---

## Agent Integration | Agent 集成

### Expected Agent Behavior

1. **On user asks "show my crypto assets"**:
   - Query latest snapshot from database
   - Calculate net value (subtract debt)
   - Merge same coins, merge stablecoins
   - Include manual entries
   - Format as readable report

2. **On scheduled collection**:
   - Run `python3 collector.py`
   - Report any errors
   - Compare with previous snapshot

3. **On expiry check**:
   - Run `python3 collector.py check-expiry`
   - Alert user if any entries expire today

### Report Format Template

```
📊 Crypto Portfolio - YYYY-MM-DD

💰 Net Value: $XXX,XXX
   Assets: $XXX,XXX
   Debt: -$XX,XXX

📋 By Source:
   Binance: $XX,XXX
   Bybit: $XX,XXX
   OKX: $XX,XXX
   Wallets: $XX,XXX

🪙 Top Holdings:
   BTC: X.XX ($XX,XXX)
   ETH: X.XX ($XX,XXX)
   Stablecoins: $XX,XXX

📝 Manual Entries:
   [Project] COIN: X.XX
```

---

## Security Checklist | 安全检查

- [ ] `secrets.yaml` not in git
- [ ] `wallets.yaml` not in git
- [ ] `portfolio.db` not in git
- [ ] All API keys are read-only
- [ ] No hardcoded credentials in code

---

## Troubleshooting | 故障排除

| Issue | Solution |
|-------|----------|
| "No module named 'requests'" | `pip install requests` |
| "Puppeteer timeout" | Check network, increase timeout |
| "API rate limit" | Wait and retry, add delays |
| "Database locked" | Close other connections |

---

## File to Remember | 记住这个文件

When user asks about crypto assets, read this database:
```
~/.openclaw/workspace-engineer/crypto-portfolio/portfolio.db
```
