"""
Binance 交易所资产采集器
支持：现货、Portfolio Margin 统一账户、VIP质押借币、理财
文档: https://binance-docs.github.io/apidocs/
"""
import hmac
import hashlib
import time
import requests
from typing import Optional, List, Dict
from datetime import datetime


class BinanceCollector:
    """
    Binance 资产采集器 (完整版)
    
    支持账户类型：
    1. 现货账户 - /api/v3/account
    2. Portfolio Margin 统一账户 - /papi/v1/*
    3. VIP质押借币 - /sapi/v1/loan/vip/*
    4. 理财账户 (Simple Earn) - /sapi/v1/simple-earn/*
    
    需要 API 权限：
    - 允许读取
    - 允许杠杆质押借币（读取VIP借币）
    """
    
    BASE_URL = "https://api.binance.com"
    PM_URL = "https://papi.binance.com"
    
    # 稳定币列表
    STABLECOINS = {"USDT", "USDC", "BUSD", "USD1", "FDUSD", "TUSD", "DAI"}
    
    def __init__(self, api_key: str, api_secret: str, label: str = "default"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.label = label
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": api_key
        })
    
    def _sign(self, params: dict) -> dict:
        """生成签名"""
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params
    
    def _request(self, base_url: str, endpoint: str, params: dict = None) -> Optional[dict]:
        """发送签名请求"""
        if params is None:
            params = {}
        
        params = self._sign(params)
        url = f"{base_url}{endpoint}"
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                # 静默处理非关键错误
                return None
        except Exception as e:
            print(f"[Binance] 请求失败: {e}")
            return None
    
    def get_prices(self) -> Dict[str, float]:
        """获取所有交易对价格"""
        prices = {coin: 1.0 for coin in self.STABLECOINS}
        
        try:
            resp = self.session.get(f"{self.BASE_URL}/api/v3/ticker/price", timeout=10)
            if resp.status_code == 200:
                for item in resp.json():
                    symbol = item["symbol"]
                    if symbol.endswith("USDT"):
                        asset = symbol[:-4]
                        prices[asset] = float(item["price"])
        except Exception as e:
            print(f"[Binance] 获取价格失败: {e}")
        
        return prices
    
    
    def get_wallet_balance(self) -> dict:
        """
        获取各钱包 BTC 估值（Binance 官方估值）
        返回: {'Spot': btc_value, 'Cross Margin (PM)': btc_value, ...}
        """
        data = self._request(self.BASE_URL, "/sapi/v1/asset/wallet/balance")
        if not data:
            return {}
        
        result = {}
        for item in data:
            wallet_name = item.get('walletName', '')
            balance = float(item.get('balance', 0))
            if balance > 0:
                result[wallet_name] = balance
        return result
    
    def get_btc_price(self) -> float:
        """获取 BTC/USDT 价格"""
        try:
            resp = self.session.get(f"{self.BASE_URL}/api/v3/ticker/price?symbol=BTCUSDT", timeout=10)
            if resp.status_code == 200:
                return float(resp.json()['price'])
        except:
            pass
        return 0.0

    def get_spot_balances(self, prices: Dict[str, float]) -> tuple:
        """
        获取现货账户余额
        返回: (资产列表, 总价值)
        """
        data = self._request(self.BASE_URL, "/api/v3/account")
        if not data:
            return [], 0.0
        
        balances = []
        total = 0.0
        
        for b in data.get("balances", []):
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            qty = free + locked
            
            if qty > 0.00001:
                asset = b["asset"]
                price = prices.get(asset, 0)
                if asset in self.STABLECOINS:
                    price = 1.0
                value = qty * price
                
                balances.append({
                    "asset": asset,
                    "free": free,
                    "locked": locked,
                    "total": qty,
                    "price_usd": price,
                    "value_usd": value
                })
                total += value
        
        # 按价值排序
        balances.sort(key=lambda x: -x["value_usd"])
        return balances, total
    
    def get_pm_balances(self, prices: Dict[str, float]) -> tuple:
        """
        获取 Portfolio Margin 资产和负债
        返回: (资产列表, 总资产, 总负债)
        """
        data = self._request(self.PM_URL, "/papi/v1/balance")
        if not data:
            return [], 0.0, 0.0
        
        balances = []
        total_assets = 0.0
        total_debt = 0.0
        
        for b in data:
            asset = b.get("asset")
            wallet = float(b.get("totalWalletBalance", 0))
            borrowed = float(b.get("crossMarginBorrowed", 0))
            
            price = prices.get(asset, 0)
            if asset in self.STABLECOINS:
                price = 1.0
            
            if wallet > 0.00001 or borrowed > 0.00001:
                asset_value = wallet * price
                debt_value = borrowed * price
                
                balances.append({
                    "asset": asset,
                    "wallet_balance": wallet,
                    "borrowed": borrowed,
                    "price_usd": price,
                    "asset_value_usd": asset_value,
                    "debt_value_usd": debt_value
                })
                
                total_assets += asset_value
                total_debt += debt_value
        
        return balances, total_assets, total_debt
    
    def get_pm_account_info(self) -> Optional[dict]:
        """获取 PM 账户概览信息"""
        data = self._request(self.PM_URL, "/papi/v1/account")
        if data:
            return {
                "account_equity": float(data.get("accountEquity", 0)),
                "actual_equity": float(data.get("actualEquity", 0)),
                "uni_mmr": float(data.get("uniMMR", 0)),
            }
        return None
    
    def get_vip_loans(self, prices: Dict[str, float]) -> tuple:
        """
        获取 VIP 质押借币负债
        返回: (借款列表, 总负债)
        """
        data = self._request(self.BASE_URL, "/sapi/v1/loan/vip/ongoing/orders")
        if not data:
            return [], 0.0
        
        loans = []
        total_debt = 0.0
        
        for loan in data.get("rows", []):
            coin = loan.get("loanCoin")
            debt = float(loan.get("totalDebt", 0))
            collateral_value = float(loan.get("collateralValue", 0))
            ltv = float(loan.get("currentLTV", 0))
            
            price = prices.get(coin, 1.0)
            if coin in self.STABLECOINS:
                price = 1.0
            
            debt_value = debt * price
            total_debt += debt_value
            
            loans.append({
                "loan_coin": coin,
                "total_debt": debt,
                "debt_value_usd": debt_value,
                "collateral_value_usd": collateral_value,
                "current_ltv": ltv
            })
        
        return loans, total_debt
    
    def get_earn_balances(self, prices: Dict[str, float]) -> tuple:
        """
        获取理财账户余额
        返回: (理财列表, 总价值)
        """
        balances = []
        total = 0.0
        
        # 活期
        flexible = self._request(self.BASE_URL, "/sapi/v1/simple-earn/flexible/position")
        if flexible and "rows" in flexible:
            for item in flexible["rows"]:
                amount = float(item.get("totalAmount", 0))
                if amount > 0:
                    asset = item["asset"]
                    price = prices.get(asset, 0)
                    if asset in self.STABLECOINS:
                        price = 1.0
                    value = amount * price
                    
                    balances.append({
                        "asset": asset,
                        "amount": amount,
                        "type": "flexible",
                        "price_usd": price,
                        "value_usd": value,
                        "apy": float(item.get("latestAnnualPercentageRate", 0))
                    })
                    total += value
        
        # 定期
        locked = self._request(self.BASE_URL, "/sapi/v1/simple-earn/locked/position")
        if locked and "rows" in locked:
            for item in locked["rows"]:
                amount = float(item.get("amount", 0))
                if amount > 0:
                    asset = item["asset"]
                    price = prices.get(asset, 0)
                    if asset in self.STABLECOINS:
                        price = 1.0
                    value = amount * price
                    
                    balances.append({
                        "asset": asset,
                        "amount": amount,
                        "type": "locked",
                        "price_usd": price,
                        "value_usd": value,
                        "apy": float(item.get("apy", 0))
                    })
                    total += value
        
        return balances, total
    
    def collect(self) -> dict:
        """
        采集完整资产数据
        
        返回结构：
        {
            "exchange": "binance",
            "label": "账户标签",
            "total_assets": 总资产,
            "total_debt": 总负债,
            "net_value": 净资产,
            "spot": 现货列表,
            "pm": PM资产列表,
            "vip_loans": VIP借款列表,
            "earn": 理财列表,
            "collected_at": 采集时间
        }
        """
        # 获取价格
        prices = self.get_prices()
        
        # 初始化结果
        result = {
            "exchange": "binance",
            "label": self.label,
            "total_assets": 0.0,
            "total_debt": 0.0,
            "net_value": 0.0,
            "spot": [],
            "spot_total": 0.0,
            "pm": [],
            "pm_assets": 0.0,
            "pm_debt": 0.0,
            "pm_info": None,
            "vip_loans": [],
            "vip_debt": 0.0,
            "earn": [],
            "earn_total": 0.0,
            "collected_at": datetime.utcnow().isoformat()
        }
        
        # 1. 现货账户
        spot, spot_total = self.get_spot_balances(prices)
        result["spot"] = spot
        result["spot_total"] = spot_total
        result["total_assets"] += spot_total
        
        # 2. Portfolio Margin 统一账户
        pm_info = self.get_pm_account_info()
        result["pm_info"] = pm_info
        
        pm, pm_assets, pm_debt = self.get_pm_balances(prices)
        result["pm"] = pm
        result["pm_assets"] = pm_assets
        result["pm_debt"] = pm_debt
        result["total_assets"] += pm_assets
        result["total_debt"] += pm_debt
        
        # 3. VIP 质押借币
        vip_loans, vip_debt = self.get_vip_loans(prices)
        result["vip_loans"] = vip_loans
        result["vip_debt"] = vip_debt
        result["total_debt"] += vip_debt
        
        # 4. 理财账户
        earn, earn_total = self.get_earn_balances(prices)
        result["earn"] = earn
        result["earn_total"] = earn_total
        result["total_assets"] += earn_total
        
        # 使用 wallet/balance API 校准总资产（Binance 官方估值更准确）
        wallet_balance = self.get_wallet_balance()
        btc_price = self.get_btc_price()
        
        if wallet_balance and btc_price > 0:
            # Spot + Funding 的官方估值
            spot_btc = wallet_balance.get('Spot', 0) + wallet_balance.get('Funding', 0)
            spot_official = spot_btc * btc_price
            
            # PM 的官方估值
            pm_btc = wallet_balance.get('Cross Margin (PM)', 0)
            pm_official = pm_btc * btc_price
            
            # 计算差异并记录
            spot_diff = spot_official - result["spot_total"]
            pm_diff = pm_official - result["pm_assets"]
            
            # 使用官方估值
            result["spot_official"] = spot_official
            result["pm_official"] = pm_official
            result["total_assets"] = spot_official + pm_official + result["earn_total"]
            result["wallet_balance_btc"] = wallet_balance
            result["btc_price"] = btc_price
        
        # 计算净值
        result["net_value"] = result["total_assets"] - result["total_debt"]
        
        return result


if __name__ == "__main__":
    import yaml
    import os
    
    config_path = os.path.join(os.path.dirname(__file__), '../../config/secrets.yaml')
    
    with open(config_path) as f:
        secrets = yaml.safe_load(f)
    
    binance_accounts = secrets.get("exchanges", {}).get("binance", [])
    
    if not binance_accounts:
        print("未配置 Binance API")
    else:
        for acc in binance_accounts:
            collector = BinanceCollector(
                acc["api_key"],
                acc["api_secret"],
                acc.get("label", "default")
            )
            result = collector.collect()
            
            print(f"\n{'='*70}")
            print(f"[{result['label']}] Binance 完整资产报告")
            print(f"{'='*70}")
            
            # 现货
            print(f"\n【现货账户】${result['spot_total']:,.2f}")
            for b in result['spot'][:10]:
                if b['value_usd'] >= 1:
                    print(f"  {b['asset']}: {b['total']:,.4f} = ${b['value_usd']:,.2f}")
            if len(result['spot']) > 10:
                print(f"  ... 还有 {len(result['spot'])-10} 种")
            
            # PM
            if result['pm']:
                print(f"\n【Portfolio Margin】资产 ${result['pm_assets']:,.2f} / 负债 ${result['pm_debt']:,.2f}")
                for b in result['pm']:
                    if b['asset_value_usd'] >= 1 or b['debt_value_usd'] >= 1:
                        debt_str = f" [借入: {b['borrowed']:,.2f}]" if b['borrowed'] > 0 else ""
                        print(f"  {b['asset']}: {b['wallet_balance']:,.4f} = ${b['asset_value_usd']:,.2f}{debt_str}")
            
            # VIP借币
            if result['vip_loans']:
                print(f"\n【VIP质押借币】负债 ${result['vip_debt']:,.2f}")
                for loan in result['vip_loans']:
                    print(f"  {loan['loan_coin']}: {loan['total_debt']:,.2f} = ${loan['debt_value_usd']:,.2f} (LTV: {loan['current_ltv']*100:.2f}%)")
            
            # 理财
            if result['earn']:
                print(f"\n【理财账户】${result['earn_total']:,.2f}")
                for b in result['earn']:
                    print(f"  {b['asset']}: {b['amount']:,.4f} ({b['type']}) = ${b['value_usd']:,.2f}")
            
            # 汇总
            print(f"\n{'='*70}")
            print(f"总资产: ${result['total_assets']:,.2f}")
            print(f"总负债: -${result['total_debt']:,.2f}")
            print(f"{'─'*70}")
            print(f"净资产: ${result['net_value']:,.2f}")
            print(f"{'='*70}")
