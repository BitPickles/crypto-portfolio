-- Crypto Portfolio 数据库结构
-- SQLite

-- 自动采集的余额记录
CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,          -- 关联快照
    source TEXT NOT NULL,                  -- 来源: binance, bitget, wallet, etc.
    account_label TEXT,                    -- 账户标签
    coin TEXT NOT NULL,                    -- 币种
    quantity REAL NOT NULL,                -- 数量
    price_usd REAL,                        -- 单价 USD
    value_usd REAL,                        -- 价值 USD
    is_debt INTEGER DEFAULT 0,             -- 是否为负债 (1=负债)
    extra_info TEXT,                       -- JSON 额外信息
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
);

-- 手动记账
CREATE TABLE IF NOT EXISTS manual_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,                 -- 项目名称
    coin TEXT NOT NULL,                    -- 币种
    quantity REAL NOT NULL,                -- 数量
    price_usd REAL,                        -- 记录时单价
    value_usd REAL,                        -- 记录时价值
    notes TEXT,                            -- 备注
    is_active INTEGER DEFAULT 1,           -- 是否有效 (0=已退出)
    expires_at TEXT,                       -- 到期时间 (YYYY-MM-DD)
    reminded INTEGER DEFAULT 0,            -- 是否已提醒 (1=已提醒)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 快照（每次采集一条记录）
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    total_assets REAL,                     -- 总资产
    total_debt REAL,                       -- 总负债
    net_value REAL,                        -- 净资产
    manual_value REAL,                     -- 手动记账总值
    grand_total REAL,                      -- 最终总计
    source_summary TEXT                    -- JSON: 各来源汇总
);

-- 价格缓存（减少 API 调用）
CREATE TABLE IF NOT EXISTS prices (
    coin TEXT PRIMARY KEY,
    price_usd REAL NOT NULL,
    source TEXT,                           -- binance, coingecko, etc.
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_balances_snapshot ON balances(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_balances_coin ON balances(coin);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(collected_at);
CREATE INDEX IF NOT EXISTS idx_manual_project ON manual_entries(project);
