"""
数据库管理器
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '../../portfolio.db')
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path) as f:
            schema = f.read()
        
        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema)
        conn.commit()
        conn.close()
    
    def _connect(self):
        return sqlite3.connect(self.db_path)
    
    # ========== 快照操作 ==========
    
    def create_snapshot(self, total_assets: float, total_debt: float, 
                       manual_value: float, source_summary: dict) -> int:
        """创建新快照，返回 snapshot_id"""
        conn = self._connect()
        cursor = conn.cursor()
        
        net_value = total_assets - total_debt
        grand_total = net_value + manual_value
        
        cursor.execute('''
            INSERT INTO snapshots (total_assets, total_debt, net_value, manual_value, grand_total, source_summary)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (total_assets, total_debt, net_value, manual_value, grand_total, json.dumps(source_summary)))
        
        snapshot_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return snapshot_id
    
    def get_latest_snapshot(self) -> Optional[dict]:
        """获取最新快照"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM snapshots ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_snapshots(self, days: int = 30) -> List[dict]:
        """获取最近 N 天的快照"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM snapshots 
            WHERE collected_at >= datetime('now', ?)
            ORDER BY collected_at DESC
        ''', (f'-{days} days',))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ========== 余额操作 ==========
    
    def add_balance(self, snapshot_id: int, source: str, coin: str, quantity: float,
                   price_usd: float, value_usd: float, is_debt: bool = False,
                   account_label: str = None, extra_info: dict = None):
        """添加余额记录"""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO balances (snapshot_id, source, account_label, coin, quantity, price_usd, value_usd, is_debt, extra_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (snapshot_id, source, account_label, coin, quantity, price_usd, value_usd, 
              1 if is_debt else 0, json.dumps(extra_info) if extra_info else None))
        
        conn.commit()
        conn.close()
    
    def get_balances_by_snapshot(self, snapshot_id: int) -> List[dict]:
        """获取某次快照的所有余额"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM balances WHERE snapshot_id = ? ORDER BY value_usd DESC', (snapshot_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_latest_balances(self) -> List[dict]:
        """获取最新的余额数据"""
        snapshot = self.get_latest_snapshot()
        if snapshot:
            return self.get_balances_by_snapshot(snapshot['id'])
        return []
    
    def get_coin_history(self, coin: str, days: int = 30) -> List[dict]:
        """获取某币种的历史持仓"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.*, s.collected_at 
            FROM balances b
            JOIN snapshots s ON b.snapshot_id = s.id
            WHERE b.coin = ? AND s.collected_at >= datetime('now', ?)
            ORDER BY s.collected_at DESC
        ''', (coin, f'-{days} days'))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ========== 手动记账 ==========
    
    def add_manual_entry(self, project: str, coin: str, quantity: float,
                        price_usd: float = None, notes: str = None,
                        expires_at: str = None) -> int:
        """
        添加手动记账
        
        Args:
            project: 项目名称
            coin: 币种
            quantity: 数量
            price_usd: 单价
            notes: 备注
            expires_at: 到期日期 (YYYY-MM-DD 格式)
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        value_usd = quantity * price_usd if price_usd else None
        
        cursor.execute('''
            INSERT INTO manual_entries (project, coin, quantity, price_usd, value_usd, notes, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (project, coin, quantity, price_usd, value_usd, notes, expires_at))
        
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return entry_id
    
    def update_manual_entry(self, entry_id: int, **kwargs):
        """更新手动记账"""
        conn = self._connect()
        cursor = conn.cursor()
        
        allowed_fields = ['project', 'coin', 'quantity', 'price_usd', 'value_usd', 'notes', 'is_active']
        updates = []
        values = []
        
        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f'{key} = ?')
                values.append(value)
        
        if updates:
            updates.append('updated_at = CURRENT_TIMESTAMP')
            values.append(entry_id)
            
            cursor.execute(f'''
                UPDATE manual_entries SET {', '.join(updates)} WHERE id = ?
            ''', values)
            
            conn.commit()
        conn.close()
    
    def get_manual_entries(self, active_only: bool = True) -> List[dict]:
        """获取手动记账列表"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('SELECT * FROM manual_entries WHERE is_active = 1 ORDER BY project, coin')
        else:
            cursor.execute('SELECT * FROM manual_entries ORDER BY project, coin')
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_manual_total(self, prices: Dict[str, float] = None) -> float:
        """计算手动记账总值"""
        entries = self.get_manual_entries(active_only=True)
        total = 0.0
        
        for entry in entries:
            if prices and entry['coin'] in prices:
                total += entry['quantity'] * prices[entry['coin']]
            elif entry['value_usd']:
                total += entry['value_usd']
        
        return total
    
    def get_expiring_entries(self, date: str = None) -> List[dict]:
        """
        获取指定日期到期的记账（未提醒过的）
        
        Args:
            date: 日期 (YYYY-MM-DD)，默认今天
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM manual_entries 
            WHERE is_active = 1 
            AND expires_at = ? 
            AND reminded = 0
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def mark_reminded(self, entry_id: int):
        """标记为已提醒"""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('UPDATE manual_entries SET reminded = 1 WHERE id = ?', (entry_id,))
        conn.commit()
        conn.close()
    
    # ========== 价格缓存 ==========
    
    def update_price(self, coin: str, price_usd: float, source: str = 'binance'):
        """更新价格缓存"""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO prices (coin, price_usd, source, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (coin, price_usd, source))
        
        conn.commit()
        conn.close()
    
    def get_prices(self) -> Dict[str, float]:
        """获取所有缓存价格"""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT coin, price_usd FROM prices')
        rows = cursor.fetchall()
        conn.close()
        
        return {row[0]: row[1] for row in rows}
    
    # ========== 统计分析 ==========
    
    def get_weekly_snapshots(self) -> List[dict]:
        """获取最近7天的快照"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM snapshots 
            WHERE collected_at >= datetime('now', '-7 days')
            ORDER BY collected_at ASC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_asset_summary(self) -> dict:
        """获取资产汇总"""
        snapshot = self.get_latest_snapshot()
        if not snapshot:
            return {}
        
        balances = self.get_balances_by_snapshot(snapshot['id'])
        manual = self.get_manual_entries()
        
        # 按来源分组
        by_source = {}
        for b in balances:
            source = b['source']
            if source not in by_source:
                by_source[source] = {'assets': 0, 'debt': 0}
            if b['is_debt']:
                by_source[source]['debt'] += b['value_usd'] or 0
            else:
                by_source[source]['assets'] += b['value_usd'] or 0
        
        # 按币种分组
        by_coin = {}
        for b in balances:
            coin = b['coin']
            if coin not in by_coin:
                by_coin[coin] = {'quantity': 0, 'value': 0}
            if not b['is_debt']:
                by_coin[coin]['quantity'] += b['quantity']
                by_coin[coin]['value'] += b['value_usd'] or 0
        
        return {
            'snapshot': snapshot,
            'by_source': by_source,
            'by_coin': dict(sorted(by_coin.items(), key=lambda x: -x[1]['value'])),
            'manual_entries': manual
        }
