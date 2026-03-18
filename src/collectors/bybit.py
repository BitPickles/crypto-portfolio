"""
Bybit 交易所资产采集器
支持：统一账户、资金账户
文档: https://bybit-exchange.github.io/docs/v5/intro
"""
import hmac
import hashlib
import time
import requests
from typing import Optional, List, Dict
from datetime import datetime


def safe_float(value, default=0.0):
    """安全转换为 float"""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class BybitCollector:
    """
    Bybit 统一账户资产采集器
    """
    
    BASE_URL = "https://api.bybit.com"
    STABLECOINS = {"USDT", "USDC", "DAI", "BUSD"}
    
    def __init__(self, api_key: str, api_secret: str, label: str = "default"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.label = label
        self.session = requests.Session()
    
    def _sign(self, params: dict) -> dict:
        """生成签名 (Bybit V5)"""
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sign_str = f"{timestamp}{self.api_key}{recv_window}{param_str}"
        
        signature = hmac.new(
            self.api_secret.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature
        }
    
    def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """发送签名请求"""
        if params is None:
            params = {}
        
        headers = self._sign(params)
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            
            if data.get("retCode") == 0:
                return data.get("result", {})
            else:
                print(f"[Bybit] API 错误: {data.get('retMsg', 'Unknown')}")
                return None
        except Exception as e:
            print(f"[Bybit] 请求失败: {e}")
            return None
    
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> List[dict]:
        """
        获取钱包余额
        account_type: UNIFIED, CONTRACT, SPOT, FUND
        """
        data = self._request("/v5/account/wallet-balance", {"accountType": account_type})
        if not data:
            return []
        
        balances = []
        for account in data.get("list", []):
            for coin in account.get("coin", []):
                equity = safe_float(coin.get("equity"))
                wallet_balance = safe_float(coin.get("walletBalance"))
                usd_value = safe_float(coin.get("usdValue"))
                
                if equity > 0 or wallet_balance > 0:
                    balances.append({
                        "asset": coin["coin"],
                        "equity": equity,
                        "available": safe_float(coin.get("availableToWithdraw")),
                        "wallet_balance": wallet_balance,
                        "unrealized_pnl": safe_float(coin.get("unrealisedPnl")),
                        "usd_value": usd_value,
                        "borrowed": safe_float(coin.get("borrowAmount")),
                    })
        
        return balances
    
    def get_funding_balance(self) -> List[dict]:
        """获取资金账户余额"""
        data = self._request("/v5/asset/transfer/query-account-coins-balance", 
                            {"accountType": "FUND"})
        if not data:
            return []
        
        balances = []
        for coin in data.get("balance", []):
            balance = safe_float(coin.get("walletBalance"))
            if balance > 0:
                balances.append({
                    "asset": coin["coin"],
                    "balance": balance,
                    "available": safe_float(coin.get("transferBalance")),
                })
        
        return balances
    
    def get_prices(self) -> Dict[str, float]:
        """获取价格"""
        prices = {coin: 1.0 for coin in self.STABLECOINS}
        
        try:
            resp = self.session.get(f"{self.BASE_URL}/v5/market/tickers", 
                                   params={"category": "spot"}, timeout=10)
            data = resp.json()
            if data.get("retCode") == 0:
                for item in data.get("result", {}).get("list", []):
                    symbol = item.get("symbol", "")
                    if symbol.endswith("USDT"):
                        asset = symbol[:-4]
                        prices[asset] = safe_float(item.get("lastPrice"))
        except Exception as e:
            print(f"[Bybit] 获取价格失败: {e}")
        
        return prices
    
    def collect(self) -> dict:
        """采集完整资产数据"""
        result = {
            "exchange": "bybit",
            "label": self.label,
            "total_assets": 0.0,
            "total_debt": 0.0,
            "net_value": 0.0,
            "unified": [],
            "funding": [],
            "collected_at": datetime.utcnow().isoformat()
        }
        
        prices = self.get_prices()
        
        # 统一账户
        unified = self.get_wallet_balance("UNIFIED")
        for b in unified:
            # 使用 API 返回的 usd_value，如果没有则计算
            if b["usd_value"] > 0:
                result["total_assets"] += b["usd_value"]
            else:
                price = prices.get(b["asset"], 0)
                if b["asset"] in self.STABLECOINS:
                    price = 1.0
                b["usd_value"] = b["equity"] * price
                result["total_assets"] += b["usd_value"]
            
            # 计算负债
            if b.get("borrowed", 0) > 0:
                price = prices.get(b["asset"], 0)
                if b["asset"] in self.STABLECOINS:
                    price = 1.0
                result["total_debt"] += b["borrowed"] * price
        
        result["unified"] = unified
        
        # 资金账户
        funding = self.get_funding_balance()
        for b in funding:
            price = prices.get(b["asset"], 0)
            if b["asset"] in self.STABLECOINS:
                price = 1.0
            b["usd_value"] = b["balance"] * price
            result["total_assets"] += b["usd_value"]
        
        result["funding"] = funding
        
        # 计算净值
        result["net_value"] = result["total_assets"] - result["total_debt"]
        
        return result


if __name__ == "__main__":
    import yaml
    import os
    
    config_path = os.path.join(os.path.dirname(__file__), '../../config/secrets.yaml')
    
    with open(config_path) as f:
        secrets = yaml.safe_load(f)
    
    accounts = secrets.get("exchanges", {}).get("bybit", [])
    
    if not accounts:
        print("未配置 Bybit API，跳过测试")
    else:
        for acc in accounts:
            collector = BybitCollector(
                acc["api_key"],
                acc["api_secret"],
                acc.get("label", "default")
            )
            result = collector.collect()
            
            print(f"\n{'='*60}")
            print(f"[{result['label']}] Bybit 资产报告")
            print(f"{'='*60}")
            
            if result['unified']:
                print(f"\n【统一账户】")
                for b in result['unified']:
                    if b['usd_value'] >= 1:
                        debt_str = f" [借入: {b['borrowed']:.4f}]" if b.get('borrowed', 0) > 0 else ""
                        print(f"  {b['asset']}: {b['equity']:.4f} (${b['usd_value']:.2f}){debt_str}")
            
            if result['funding']:
                print(f"\n【资金账户】")
                for b in result['funding']:
                    if b['usd_value'] >= 1:
                        print(f"  {b['asset']}: {b['balance']:.4f} (${b['usd_value']:.2f})")
            
            print(f"\n{'='*60}")
            print(f"总资产: ${result['total_assets']:,.2f}")
            print(f"总负债: -${result['total_debt']:,.2f}")
            print(f"净资产: ${result['net_value']:,.2f}")
            print(f"{'='*60}")
