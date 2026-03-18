"""
统一采集器 - 采集所有来源的资产数据并存入数据库
"""
import os
import yaml
from datetime import datetime
from typing import Dict, List

from db.database import Database
from collectors.binance import BinanceCollector
from collectors.bitget import BitgetCollector
from collectors.bybit import BybitCollector
from collectors.okx import OKXCollector
import subprocess
import json


class PortfolioCollector:
    """
    资产采集器
    
    使用方法:
        collector = PortfolioCollector()
        result = collector.collect_all()
    """
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '../config/secrets.yaml')
        
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        self.db = Database()
        self.prices = {}  # 价格缓存
    
    def _fetch_prices_from_binance(self) -> Dict[str, float]:
        """从 Binance 获取价格"""
        import requests
        
        prices = {'USDT': 1.0, 'USDC': 1.0, 'USD1': 1.0, 'BUSD': 1.0, 'FDUSD': 1.0, 'DAI': 1.0}
        
        try:
            resp = requests.get('https://api.binance.com/api/v3/ticker/price', timeout=10)
            if resp.status_code == 200:
                for item in resp.json():
                    symbol = item['symbol']
                    if symbol.endswith('USDT'):
                        asset = symbol[:-4]
                        prices[asset] = float(item['price'])
        except Exception as e:
            print(f"[Price] Binance 价格获取失败: {e}")
        
        return prices
    
    def _get_price(self, coin: str) -> float:
        """获取币种价格"""
        if not self.prices:
            self.prices = self._fetch_prices_from_binance()
        
        # 稳定币
        if coin.upper() in ['USDT', 'USDC', 'USD1', 'BUSD', 'FDUSD', 'DAI', 'TUSD']:
            return 1.0
        
        return self.prices.get(coin.upper(), 0)
    
    def collect_binance(self) -> Dict:
        """采集 Binance"""
        accounts = self.config.get('exchanges', {}).get('binance', [])
        results = []
        
        for acc in accounts:
            collector = BinanceCollector(
                acc['api_key'],
                acc['api_secret'],
                acc.get('label', 'default')
            )
            result = collector.collect()
            results.append(result)
        
        return results
    
    def collect_bitget(self) -> Dict:
        """采集 Bitget"""
        accounts = self.config.get('exchanges', {}).get('bitget', [])
        results = []
        
        for acc in accounts:
            collector = BitgetCollector(
                acc['api_key'],
                acc['api_secret'],
                acc['passphrase'],
                acc.get('label', 'default')
            )
            result = collector.collect()
            results.append(result)
        
        return results
    
    def collect_bybit(self) -> Dict:
        """采集 Bybit"""
        accounts = self.config.get('exchanges', {}).get('bybit', [])
        results = []
        
        for acc in accounts:
            collector = BybitCollector(
                acc['api_key'],
                acc['api_secret'],
                acc.get('label', 'default')
            )
            result = collector.collect()
            results.append(result)
        
        return results
    
    def collect_okx(self) -> Dict:
        """采集 OKX"""
        accounts = self.config.get('exchanges', {}).get('okx', [])
        results = []
        
        for acc in accounts:
            collector = OKXCollector(
                acc['api_key'],
                acc['api_secret'],
                acc['passphrase'],
                acc.get('label', 'default')
            )
            result = collector.collect()
            results.append(result)
        
        return results
    
    def collect_debank_wallets(self) -> list:
        """采集 Debank 钱包资产"""
        # 获取活跃钱包
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        wallets = conn.execute(
            'SELECT address, label, expires_at FROM wallets WHERE is_active = 1'
        ).fetchall()
        conn.close()
        
        if not wallets:
            return []
        
        results = []
        script_path = os.path.join(os.path.dirname(__file__), 'debank_scraper.js')
        
        try:
            # 调用 Node 脚本获取数据
            proc = subprocess.run(
                ['node', script_path, '--json'],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=os.path.dirname(script_path)
            )
            
            if proc.returncode == 0:
                # 解析 JSON 输出 (取最后一行)
                output_lines = [l for l in proc.stdout.strip().split('\n') if l.startswith('[')]
                if output_lines:
                    data = json.loads(output_lines[-1])
                    for item in data:
                        if item['data']['success']:
                            results.append({
                                'label': item['wallet']['label'],
                                'address': item['wallet']['address'],
                                'total_usd': item['data']['totalUsd'],
                                'expires_at': item['wallet'].get('expires_at')
                            })
            else:
                print(f"[Debank] 脚本错误: {proc.stderr[:200]}")
                
        except subprocess.TimeoutExpired:
            print("[Debank] 采集超时")
        except Exception as e:
            print(f"[Debank] 采集失败: {e}")
        
        return results
    
    def collect_all(self, save_to_db: bool = True) -> Dict:
        """
        采集所有来源并保存到数据库
        
        返回:
        {
            'total_assets': 总资产,
            'total_debt': 总负债,
            'net_value': 净资产,
            'manual_value': 手动记账,
            'grand_total': 最终总计,
            'sources': {来源明细},
            'snapshot_id': 快照ID
        }
        """
        # 获取价格
        self.prices = self._fetch_prices_from_binance()
        
        # 更新价格缓存
        for coin, price in self.prices.items():
            self.db.update_price(coin, price, 'binance')
        
        total_assets = 0
        total_debt = 0
        source_summary = {}
        all_balances = []  # (source, label, coin, qty, price, value, is_debt)
        
        # Binance
        try:
            binance_results = self.collect_binance()
            for result in binance_results:
                source_summary[f"binance:{result['label']}"] = {
                    'assets': result['total_assets'],
                    'debt': result['total_debt'],
                    'net': result['net_value']
                }
                total_assets += result['total_assets']
                total_debt += result['total_debt']
                
                # 现货
                for b in result.get('spot', []):
                    all_balances.append(('binance', result['label'], b['asset'], 
                                        b['total'], b['price_usd'], b['value_usd'], False))
                
                # PM 资产
                for b in result.get('pm', []):
                    if b['wallet_balance'] > 0:
                        all_balances.append(('binance_pm', result['label'], b['asset'],
                                            b['wallet_balance'], b['price_usd'], b['asset_value_usd'], False))
                    if b['borrowed'] > 0:
                        all_balances.append(('binance_pm', result['label'], b['asset'],
                                            b['borrowed'], b['price_usd'], b['debt_value_usd'], True))
                
                # VIP 借币
                for loan in result.get('vip_loans', []):
                    all_balances.append(('binance_vip_loan', result['label'], loan['loan_coin'],
                                        loan['total_debt'], 1.0, loan['debt_value_usd'], True))
                
                # 理财
                for b in result.get('earn', []):
                    all_balances.append(('binance_earn', result['label'], b['asset'],
                                        b['amount'], b['price_usd'], b['value_usd'], False))
        except Exception as e:
            print(f"[Binance] 采集失败: {e}")
        
        # Bitget
        try:
            bitget_results = self.collect_bitget()
            for result in bitget_results:
                net = result.get('net_usd', 0)
                assets = result.get('total_usd', 0)
                debt = result.get('total_debt_usd', 0)
                
                source_summary[f"bitget:{result['label']}"] = {
                    'assets': assets,
                    'debt': debt,
                    'net': net
                }
                total_assets += assets
                total_debt += debt
                
                # UTA 账户
                for a in result.get('uta_account', {}).get('assets', []):
                    price = self._get_price(a['coin'])
                    value = a.get('usd_value', a['equity'] * price)
                    all_balances.append(('bitget_uta', result['label'], a['coin'],
                                        a['equity'], price, value, False))
                    if a.get('debt', 0) > 0:
                        all_balances.append(('bitget_uta', result['label'], a['coin'],
                                            a['debt'], price, a['debt'] * price, True))
                
                # 资金账户
                for a in result.get('funding_account', []):
                    price = self._get_price(a['coin'])
                    value = a.get('usd_value', a['balance'] * price)
                    all_balances.append(('bitget_funding', result['label'], a['coin'],
                                        a['balance'], price, value, False))
        except Exception as e:
            print(f"[Bitget] 采集失败: {e}")
        
        # Bybit
        try:
            bybit_results = self.collect_bybit()
            for result in bybit_results:
                assets = result.get('total_assets', 0)
                debt = result.get('total_debt', 0)
                net = result.get('net_value', 0)
                
                source_summary[f"bybit:{result['label']}"] = {
                    'assets': assets,
                    'debt': debt,
                    'net': net
                }
                total_assets += assets
                total_debt += debt
                
                # 统一账户
                for a in result.get('unified', []):
                    all_balances.append(('bybit_unified', result['label'], a['asset'],
                                        a['equity'], a.get('usd_value', 0) / a['equity'] if a['equity'] else 0,
                                        a.get('usd_value', 0), False))
                    if a.get('borrowed', 0) > 0:
                        price = self._get_price(a['asset'])
                        all_balances.append(('bybit_unified', result['label'], a['asset'],
                                            a['borrowed'], price, a['borrowed'] * price, True))
                
                # 资金账户
                for a in result.get('funding', []):
                    all_balances.append(('bybit_funding', result['label'], a['asset'],
                                        a['balance'], a.get('usd_value', 0) / a['balance'] if a['balance'] else 0,
                                        a.get('usd_value', 0), False))
        except Exception as e:
            print(f"[Bybit] 采集失败: {e}")
        
        
        # OKX
        try:
            okx_results = self.collect_okx()
            for result in okx_results:
                assets = result.get('total_usd', 0)
                debt = 0
                
                # 交易账户
                for a in result.get('trading', []):
                    all_balances.append(('okx_trading', result['label'], a['asset'],
                                        a['equity'], a['usd_value'] / a['equity'] if a['equity'] else 0,
                                        a['usd_value'], False))
                
                # 资金账户
                funding_total = 0
                for a in result.get('funding', []):
                    price = self._get_price(a['asset'])
                    value = a['balance'] * price
                    all_balances.append(('okx_funding', result['label'], a['asset'],
                                        a['balance'], price, value, False))
                    funding_total += value
                
                # 理财账户 (通过 BTC 估值)
                earn_btc = result.get('earn_btc', 0)
                btc_price = self._get_price('BTC')
                earn_usd = earn_btc * btc_price
                if earn_btc > 0:
                    all_balances.append(('okx_earn', result['label'], 'BTC_EQUIV',
                                        earn_btc, btc_price, earn_usd, False))
                
                # 总计
                okx_total = assets + funding_total + earn_usd
                source_summary[f"okx:{result['label']}"] = {
                    'assets': okx_total,
                    'debt': debt,
                    'net': okx_total,
                    'trading': assets,
                    'funding': funding_total,
                    'earn': earn_usd
                }
                total_assets += okx_total
                print(f"[OKX] 交易:${assets:,.0f} 资金:${funding_total:,.0f} 理财:${earn_usd:,.0f}")
        except Exception as e:
            print(f"[OKX] 采集失败: {e}")

        # Debank 钱包 (链上 DeFi 仓位)
        try:
            debank_results = self.collect_debank_wallets()
            debank_total = 0
            for wallet in debank_results:
                value = wallet['total_usd']
                debank_total += value
                
                source_summary[f"debank:{wallet['label']}"] = {
                    'assets': value,
                    'debt': 0,
                    'net': value,
                    'address': wallet['address'][:10] + '...',
                    'expires_at': wallet.get('expires_at')
                }
                
                # 存为 WALLET_TOTAL (无法分币种)
                all_balances.append(('debank_wallet', wallet['label'], 'WALLET_TOTAL',
                                    1, value, value, False))
            
            total_assets += debank_total
            print(f"[Debank] 钱包资产: ${debank_total:,.2f}")
        except Exception as e:
            print(f"[Debank] 采集失败: {e}")
        
        # 手动记账
        manual_value = self.db.get_manual_total(self.prices)
        
        # 保存到数据库
        snapshot_id = None
        if save_to_db:
            snapshot_id = self.db.create_snapshot(total_assets, total_debt, manual_value, source_summary)
            
            for source, label, coin, qty, price, value, is_debt in all_balances:
                if qty > 0.00001 or is_debt:
                    self.db.add_balance(snapshot_id, source, coin, qty, price, value, is_debt, label)
        
        return {
            'total_assets': total_assets,
            'total_debt': total_debt,
            'net_value': total_assets - total_debt,
            'manual_value': manual_value,
            'grand_total': total_assets - total_debt + manual_value,
            'sources': source_summary,
            'snapshot_id': snapshot_id,
            'collected_at': datetime.utcnow().isoformat()
        }
    
    def get_summary(self) -> str:
        """获取最新资产摘要（文本格式）"""
        summary = self.db.get_asset_summary()
        if not summary:
            return "暂无数据"
        
        snapshot = summary['snapshot']
        lines = [
            f"=== 资产摘要 ({snapshot['collected_at']}) ===",
            f"",
            f"净资产: ${snapshot['net_value']:,.2f}",
            f"  总资产: ${snapshot['total_assets']:,.2f}",
            f"  总负债: -${snapshot['total_debt']:,.2f}",
            f"",
            f"手动记账: ${snapshot['manual_value']:,.2f}",
            f"最终总计: ${snapshot['grand_total']:,.2f}",
            f"",
            f"--- 按来源 ---"
        ]
        
        for source, data in summary['by_source'].items():
            net = data['assets'] - data['debt']
            lines.append(f"  {source}: ${net:,.2f}")
        
        lines.append(f"")
        lines.append(f"--- 主要持仓 (Top 10) ---")
        
        for i, (coin, data) in enumerate(list(summary['by_coin'].items())[:10]):
            lines.append(f"  {coin}: {data['quantity']:,.4f} (${data['value']:,.2f})")
        
        if summary['manual_entries']:
            lines.append(f"")
            lines.append(f"--- 手动记账 ---")
            for entry in summary['manual_entries']:
                lines.append(f"  [{entry['project']}] {entry['coin']}: {entry['quantity']:,.4f}")
        
        return "\n".join(lines)


    def get_weekly_report(self) -> str:
        """生成周报"""
        snapshots = self.db.get_weekly_snapshots()
        
        if not snapshots:
            return "本周暂无数据"
        
        # 计算变化
        first = snapshots[0]
        last = snapshots[-1]
        
        net_change = last['net_value'] - first['net_value']
        net_pct = (net_change / first['net_value'] * 100) if first['net_value'] else 0
        
        lines = [
            "📊 **本周资产周报**",
            "",
            f"📅 统计周期: {first['collected_at'][:10]} ~ {last['collected_at'][:10]}",
            f"📈 采集次数: {len(snapshots)} 次",
            "",
            "**资产变化:**",
            f"  周初净资产: ${first['net_value']:,.2f}",
            f"  周末净资产: ${last['net_value']:,.2f}",
            f"  变化: {'+' if net_change >= 0 else ''}{net_change:,.2f} ({'+' if net_pct >= 0 else ''}{net_pct:.2f}%)",
            "",
            "**当前持仓 (Top 5):**"
        ]
        
        # 获取当前持仓
        summary = self.db.get_asset_summary()
        if summary and 'by_coin' in summary:
            for i, (coin, data) in enumerate(list(summary['by_coin'].items())[:5]):
                lines.append(f"  {coin}: {data['quantity']:,.4f} (${data['value']:,.2f})")
        
        # 手动记账
        manual = self.db.get_manual_entries()
        if manual:
            lines.append("")
            lines.append("**手动记账:**")
            for entry in manual:
                expires = f" (到期: {entry['expires_at']})" if entry.get('expires_at') else ""
                lines.append(f"  [{entry['project']}] {entry['coin']}: {entry['quantity']:,.4f}{expires}")
        
        return "\n".join(lines)
    
    def check_expiring_entries(self) -> List[str]:
        """
        检查今天到期的记账，返回提醒消息列表
        """
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        
        expiring = self.db.get_expiring_entries(today)
        messages = []
        
        for entry in expiring:
            msg = f"⏰ **到期提醒**\n\n项目: {entry['project']}\n币种: {entry['coin']}\n数量: {entry['quantity']:,.4f}\n\n请记得取出！"
            messages.append(msg)
            self.db.mark_reminded(entry['id'])
        
        return messages


if __name__ == "__main__":
    import sys
    
    collector = PortfolioCollector()
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'summary':
            print(collector.get_summary())
        elif cmd == 'weekly':
            print(collector.get_weekly_report())
        elif cmd == 'check-expiry':
            messages = collector.check_expiring_entries()
            if messages:
                for msg in messages:
                    print(msg)
                    print("---")
            else:
                print("今天没有到期的记账")
        else:
            print(f"未知命令: {cmd}")
            print("可用命令: summary, weekly, check-expiry")
    else:
        print("正在采集...")
        result = collector.collect_all()
        print(f"\n采集完成!")
        print(f"净资产: ${result['net_value']:,.2f}")
        print(f"手动记账: ${result['manual_value']:,.2f}")
        print(f"最终总计: ${result['grand_total']:,.2f}")
