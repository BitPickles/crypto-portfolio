# Crypto Portfolio Tracker | 加密资产追踪器

统一的加密资产管理工具，聚合多个交易所和链上钱包的资产数据。

A unified crypto asset tracker that aggregates balances from multiple exchanges and on-chain wallets.

---

## 功能特性 | Features

- 🏦 **多交易所支持** | Multi-Exchange: Binance、Bybit、OKX、Bitget
- 🔗 **链上钱包** | On-Chain Wallets: 通过 DeBank 获取 DeFi 仓位
- 📊 **本地存储** | Local Storage: SQLite 数据库，无需云端
- ⏰ **到期提醒** | Expiry Reminders: 追踪定期理财到期
- 📈 **周报生成** | Weekly Reports: 自动生成资产变化周报
- 🤖 **AI Agent 友好** | AI Ready: 专为 AI 助手集成设计

---

## 快速开始 | Quick Start

### 前置条件 | Prerequisites

- Python 3.8+
- Node.js 18+（用于钱包抓取）
- SQLite3

### 安装 | Installation

```bash
# 克隆仓库
git clone https://github.com/BitPickles/crypto-portfolio.git
cd crypto-portfolio

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Node.js 依赖（用于钱包追踪）
npm install

# 配置 API Keys
cp config/secrets.yaml.example config/secrets.yaml
cp config/wallets.yaml.example config/wallets.yaml

# 编辑配置文件，填入你的 API Keys
nano config/secrets.yaml
nano config/wallets.yaml
```

### 使用方法 | Usage

```bash
# 采集所有资产
cd src && python3 collector.py

# 查看资产摘要
python3 collector.py summary

# 生成周报
python3 collector.py weekly

# 检查到期项目
python3 collector.py check-expiry
```

---

## 配置说明 | Configuration

### 交易所 API Keys

在各交易所创建**只读权限**的 API Key：

| 交易所 | 创建路径 | 权限 |
|--------|---------|------|
| Binance | API Management → Create API | Read Only |
| Bybit | API → Create New Key | Read Only |
| OKX | API → Create API V5 | Read |
| Bitget | API Management → Create API | Read Only |

### 钱包配置 | Wallet Config

在 `config/wallets.yaml` 添加以太坊地址：

```yaml
wallets:
  - address: "0x..."
    label: "我的钱包"
    expires_at: "2026-12-31"  # 可选：到期提醒日期
```

---

## 数据库结构 | Database Schema

| 表名 | 说明 |
|------|------|
| `snapshots` | 采集时间戳和总计 |
| `balances` | 每次快照的详细持仓 |
| `manual_entries` | 手动记账条目 |
| `prices` | 价格缓存 |

### 关键字段 | Key Fields

- `is_debt = 1`：表示负债条目（值为正数，计算净值时需减去）
- `expires_at`：到期日期
- `source`：数据来源（binance、bitget、debank_wallet 等）

---

## 净值计算 | Net Value Calculation

⚠️ **重要**：负债条目的 `value_usd` 存储为正数，但计算时必须减去：

```sql
-- 正确的净值计算
SELECT 
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE 0 END) as assets,
  SUM(CASE WHEN is_debt=1 THEN value_usd ELSE 0 END) as debt,
  SUM(CASE WHEN is_debt=0 THEN value_usd ELSE -value_usd END) as net
FROM balances 
WHERE snapshot_id = (SELECT id FROM snapshots ORDER BY collected_at DESC LIMIT 1);
```

---

## 自动化 | Automation

### 定时任务 | Cron Jobs

```cron
# 每天采集（10:00 和 22:00）
0 10,22 * * * cd /path/to/crypto-portfolio/src && python3 collector.py

# 到期检查（10:15）
15 10 * * * cd /path/to/crypto-portfolio/src && python3 collector.py check-expiry

# 周报（每周一 10:45）
45 10 * * 1 cd /path/to/crypto-portfolio/src && python3 collector.py weekly
```

---

## 安全须知 | Security Notes

- 🔐 **切勿提交** `secrets.yaml` 或 `wallets.yaml` 到 git
- 🔑 **只使用只读权限**的 API Key
- 💾 **定期备份** `portfolio.db` 数据库
- 🚫 **不要暴露数据库**到公网

---

## AI Agent 接入 | For AI Agents

参见 [AGENT_DEPLOY.md](./AGENT_DEPLOY.md)，专为 AI 助手设计的快速部署指南。

---

## 项目结构 | Project Structure

```
crypto-portfolio/
├── config/
│   ├── secrets.yaml.example    # API Key 模板
│   └── wallets.yaml.example    # 钱包模板
├── src/
│   ├── collector.py            # 主采集器
│   ├── debank_scraper.js       # 钱包抓取脚本
│   ├── collectors/             # 交易所适配器
│   │   ├── binance.py
│   │   ├── bitget.py
│   │   ├── bybit.py
│   │   └── okx.py
│   └── db/
│       ├── database.py         # 数据库操作
│       └── schema.sql          # 表结构
├── README.md
├── AGENT_DEPLOY.md
├── requirements.txt
└── package.json
```

---

## 路线图 | Roadmap

- [ ] 更多交易所支持（Coinbase、Kraken）
- [ ] Telegram 机器人集成
- [ ] Web 仪表盘
- [ ] 历史图表
- [ ] 多币种支持

---

## 许可证 | License

MIT License

---

## 贡献 | Contributing

欢迎提交 Issue 和 Pull Request！
