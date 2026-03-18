"""
Bitget 交易所资产采集器
支持统一账户模式 (UTA) - 完整版
获取：交易账户 + 资金账户 + 借贷负债
"""
import ccxt
from typing import Optional, List, Dict
from datetime import datetime


class BitgetCollector:
    """
    Bitget 资产采集器
    支持统一账户 (Unified Trading Account) 模式
    完整获取所有账户类型的资产和负债
    """
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, label: str = "default"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.label = label
        
        # 使用 ccxt 库，启用 UTA 模式
        self.exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': api_secret,
            'password': passphrase,
            'options': {
                'uta': True,  # 关键：启用统一账户模式
            }
        })
    
    def get_uta_assets(self) -> Dict:
        """
        获取 UTA 交易账户资产
        API: /api/v3/account/assets
        """
        try:
            result = self.exchange.privateUtaGetV3AccountAssets()
            if result.get('code') == '00000':
                data = result.get('data', {})
                return {
                    'account_equity': float(data.get('accountEquity', 0)),
                    'usdt_equity': float(data.get('usdtEquity', 0)),
                    'unrealised_pnl': float(data.get('unrealisedPnl', 0)),
                    'assets': [
                        {
                            'coin': a.get('coin'),
                            'equity': float(a.get('equity', 0)),
                            'balance': float(a.get('balance', 0)),
                            'available': float(a.get('available', 0)),
                            'debt': float(a.get('debt', 0)),
                            'locked': float(a.get('locked', 0)),
                            'usd_value': float(a.get('usdValue', 0))
                        }
                        for a in data.get('assets', [])
                        if float(a.get('equity', 0)) > 0 or float(a.get('debt', 0)) > 0
                    ]
                }
        except Exception as e:
            print(f"[Bitget] 获取 UTA 账户失败: {e}")
        return {'account_equity': 0, 'usdt_equity': 0, 'unrealised_pnl': 0, 'assets': []}
    
    def get_funding_assets(self) -> List[Dict]:
        """
        获取资金账户资产（理财/提现账户）
        API: /api/v3/account/funding-assets
        """
        try:
            result = self.exchange.privateUtaGetV3AccountFundingAssets()
            if result.get('code') == '00000':
                assets = []
                for a in result.get('data', []):
                    balance = float(a.get('balance', 0))
                    if balance > 0:
                        assets.append({
                            'coin': a.get('coin'),
                            'balance': balance,
                            'available': float(a.get('available', 0)),
                            'frozen': float(a.get('frozen', 0))
                        })
                return assets
        except Exception as e:
            print(f"[Bitget] 获取资金账户失败: {e}")
        return []
    
    def get_loan_debts(self) -> List[Dict]:
        """
        获取借贷负债
        API: /api/v3/loan/debts
        """
        try:
            result = self.exchange.privateUtaGetV3LoanDebts()
            if result.get('code') == '00000':
                return result.get('data', [])
        except Exception as e:
            # 40054 表示没有数据，不是错误
            if '40054' not in str(e):
                print(f"[Bitget] 获取借贷负债失败: {e}")
        return []
    
    def get_positions(self) -> List[Dict]:
        """
        获取合约仓位
        """
        try:
            positions = self.exchange.fetch_positions()
            return [
                {
                    'symbol': p.get('symbol'),
                    'side': p.get('side'),
                    'contracts': float(p.get('contracts', 0)),
                    'entry_price': float(p.get('entryPrice', 0)),
                    'mark_price': float(p.get('markPrice', 0)),
                    'unrealized_pnl': float(p.get('unrealizedPnl', 0)),
                    'notional': float(p.get('notional', 0))
                }
                for p in positions
                if float(p.get('contracts', 0)) > 0
            ]
        except Exception as e:
            print(f"[Bitget] 获取仓位失败: {e}")
        return []
    
    def get_prices(self, coins: List[str]) -> Dict[str, float]:
        """获取指定币种的价格"""
        prices = {'USDT': 1.0, 'USDC': 1.0}
        
        for coin in coins:
            if coin in prices:
                continue
            try:
                ticker = self.exchange.fetch_ticker(f'{coin}/USDT')
                prices[coin] = ticker.get('last', 0) or 0
            except:
                # 尝试其他交易对
                try:
                    ticker = self.exchange.fetch_ticker(f'{coin}/USDC')
                    prices[coin] = ticker.get('last', 0) or 0
                except:
                    prices[coin] = 0
        
        return prices
    
    def collect(self) -> dict:
        """
        采集完整资产数据
        包括：UTA交易账户 + 资金账户 + 借贷负债 + 合约仓位
        """
        result = {
            "exchange": "bitget",
            "label": self.label,
            "total_usd": 0.0,
            "total_debt_usd": 0.0,
            "net_usd": 0.0,
            "uta_account": {},
            "funding_account": [],
            "loan_debts": [],
            "positions": [],
            "collected_at": datetime.utcnow().isoformat()
        }
        
        # 先获取资金账户数据，再获取价格
        funding = self.get_funding_assets()
        
        # 收集所有需要价格的币种
        all_coins = set()
        for a in funding:
            all_coins.add(a.get('coin'))
        
        # 获取价格
        prices = self.get_prices(list(all_coins))
        
        # 1. UTA 交易账户
        uta = self.get_uta_assets()
        result["uta_account"] = uta
        uta_total = uta.get('usdt_equity', 0)
        uta_debt = sum(a.get('debt', 0) * prices.get(a.get('coin'), 0) for a in uta.get('assets', []))
        
        # 2. 资金账户（理财/提现）- 数据已在上面获取
        funding_total = 0
        for a in funding:
            coin = a.get('coin')
            balance = a.get('balance', 0)
            price = prices.get(coin, 0)
            a['price_usd'] = price
            a['usd_value'] = balance * price
            funding_total += a['usd_value']
        result["funding_account"] = funding
        
        # 3. 借贷负债
        debts = self.get_loan_debts()
        result["loan_debts"] = debts
        debt_total = sum(float(d.get('debtUsdValue', 0)) for d in debts)
        
        # 4. 合约仓位
        positions = self.get_positions()
        result["positions"] = positions
        positions_pnl = sum(p.get('unrealized_pnl', 0) for p in positions)
        
        # 汇总
        result["total_usd"] = uta_total + funding_total + positions_pnl
        result["total_debt_usd"] = uta_debt + debt_total
        result["net_usd"] = result["total_usd"] - result["total_debt_usd"]
        
        return result


if __name__ == "__main__":
    import yaml
    import os
    
    config_path = os.path.join(os.path.dirname(__file__), '../../config/secrets.yaml')
    
    if os.path.exists(config_path):
        with open(config_path) as f:
            secrets = yaml.safe_load(f)
        
        accounts = secrets.get("exchanges", {}).get("bitget", [])
        
        if not accounts:
            print("未配置 Bitget API，跳过测试")
        else:
            for acc in accounts:
                collector = BitgetCollector(
                    acc["api_key"],
                    acc["api_secret"],
                    acc["passphrase"],
                    acc.get("label", "default")
                )
                result = collector.collect()
                
                print(f"\n{'='*60}")
                print(f"[{result['label']}] Bitget 完整资产报告")
                print(f"{'='*60}")
                
                print(f"\n📊 UTA 交易账户:")
                for a in result['uta_account'].get('assets', []):
                    debt_str = f" (负债: {a['debt']})" if a['debt'] > 0 else ""
                    print(f"   {a['coin']}: {a['equity']:.8f} (${a['usd_value']:.2f}){debt_str}")
                
                print(f"\n💰 资金账户（理财/提现）:")
                for a in result['funding_account']:
                    print(f"   {a['coin']}: {a['balance']:.8f} (${a['usd_value']:.2f})")
                
                if result['positions']:
                    print(f"\n📈 合约仓位:")
                    for p in result['positions']:
                        print(f"   {p['symbol']}: {p['contracts']} contracts, PnL: ${p['unrealized_pnl']:.2f}")
                
                if result['loan_debts']:
                    print(f"\n🔴 借贷负债:")
                    for d in result['loan_debts']:
                        print(f"   {d}")
                
                print(f"\n{'='*60}")
                print(f"总资产: ${result['total_usd']:,.2f}")
                print(f"总负债: ${result['total_debt_usd']:,.2f}")
                print(f"净资产: ${result['net_usd']:,.2f}")
                print(f"{'='*60}")
    else:
        print(f"配置文件不存在: {config_path}")
