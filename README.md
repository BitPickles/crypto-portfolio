# Crypto Portfolio Tracker

A unified crypto asset tracker that aggregates balances from multiple exchanges and on-chain wallets.

## Features | 功能特性

- 🏦 **Multi-Exchange Support**: Binance, Bybit, OKX, Bitget
- 🔗 **On-Chain Wallets**: DeBank integration for DeFi positions
- 📊 **SQLite Storage**: Local database, no cloud dependency
- ⏰ **Expiry Reminders**: Track time-locked assets
- 📈 **Weekly Reports**: Automated asset change reports
- 🤖 **AI Agent Ready**: Designed for AI assistant integration

---

## Quick Start | 快速开始

### Prerequisites | 前置条件

- Python 3.8+
- Node.js 18+ (for DeBank wallet scraping)
- SQLite3

### Installation | 安装

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/crypto-portfolio.git
cd crypto-portfolio

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies (for wallet tracking)
npm install

# Configure API keys
cp config/secrets.yaml.example config/secrets.yaml
cp config/wallets.yaml.example config/wallets.yaml

# Edit config files with your API keys
nano config/secrets.yaml
nano config/wallets.yaml
```

### Usage | 使用方法

```bash
# Collect all assets
cd src && python3 collector.py

# View summary
python3 collector.py summary

# Generate weekly report
python3 collector.py weekly

# Check expiring entries
python3 collector.py check-expiry
```

---

## Configuration | 配置说明

### Exchange API Keys

Create read-only API keys on each exchange:
1. Binance: API Management → Create API → Enable "Read Only"
2. Bybit: API → Create New Key → Permission: "Read Only"
3. OKX: API → Create API V5 → Permission: "Read"
4. Bitget: API Management → Create API → Permission: "Read Only"

### Wallet Configuration

Add your Ethereum addresses to `config/wallets.yaml`:

```yaml
wallets:
  - address: "0x..."
    label: "My Wallet"
    expires_at: "2026-12-31"  # Optional expiry date
```

---

## Database Schema | 数据库结构

| Table | Description |
|-------|-------------|
| `snapshots` | Collection timestamps and totals |
| `balances` | Detailed holdings per snapshot |
| `manual_entries` | Manual tracking entries |
| `prices` | Price cache |

### Key Fields | 关键字段

- `is_debt = 1`: Indicates a debt/liability entry (value stored as positive, subtract for net value)
- `expires_at`: Expiry date for time-locked assets
- `source`: Origin of data (binance, bitget, debank_wallet, etc.)

---

## Net Value Calculation | 净值计算

⚠️ **Important**: Debt entries store positive values but must be subtracted:

```sql
-- Correct net value calculation
SELECT 
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE 0 END) as assets,
  SUM(CASE WHEN is_debt=1 THEN value_usd ELSE 0 END) as debt,
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE -value_usd END) as net
FROM balances 
WHERE snapshot_id = (SELECT id FROM snapshots ORDER BY collected_at DESC LIMIT 1);
```

---

## Automation | 自动化

### Cron Jobs

```cron
# Daily collection at 10:00 and 22:00
0 10,22 * * * cd /path/to/crypto-portfolio/src && python3 collector.py

# Expiry check at 10:15
15 10 * * * cd /path/to/crypto-portfolio/src && python3 collector.py check-expiry

# Weekly report on Monday 10:45
45 10 * * 1 cd /path/to/crypto-portfolio/src && python3 collector.py weekly
```

---

## Security Notes | 安全须知

- 🔐 Never commit `secrets.yaml` or `wallets.yaml` to git
- 🔑 Use read-only API keys only
- 💾 Backup your `portfolio.db` regularly
- 🚫 Don't expose the database to public networks

---

## For AI Agents | AI Agent 接入

See [AGENT_DEPLOY.md](./AGENT_DEPLOY.md) for quick deployment instructions designed for AI assistants.

---

## License | 许可证

MIT License

---

## Contributing | 贡献

Issues and pull requests are welcome!

---

## Roadmap | 路线图

- [ ] More exchange support (Coinbase, Kraken)
- [ ] Telegram bot integration
- [ ] Web dashboard
- [ ] Historical charts
- [ ] Multi-currency support
