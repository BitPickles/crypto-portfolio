"""
OKX 交易所资产采集器
文档: https://www.okx.com/docs-v5/
"""
import hmac
import hashlib
import base64
import time
import requests
from typing import Optional, List, Dict
from datetime import datetime


class OKXCollector:
    """
    OKX 资产采集器
    
    支持账户类型：
    1. 交易账户 - /api/v5/account/balance
    2. 资金账户 - /api/v5/asset/balances
    3. 理财账户 - 通过 /api/v5/asset/asset-valuation 估算
    """
    
    BASE_URL = "https://www.okx.com"
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, label: str = "default"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.label = label
        self.session = requests.Session()
    
    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """生成签名"""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()
    
    def _request(self, endpoint: str) -> Optional[list]:
        """发送签名请求"""
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        signature = self._sign(timestamp, "GET", endpoint)
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            data = resp.json()
            
            if data.get("code") == "0":
                return data.get("data", [])
            else:
                print(f"[OKX] API 错误 ({endpoint}): {data.get('msg', 'Unknown')}")
                return None
        except Exception as e:
            print(f"[OKX] 请求失败 ({endpoint}): {e}")
            return None
    
    def get_balance(self) -> List[dict]:
        """获取交易账户余额"""
        data = self._request("/api/v5/account/balance")
        if not data:
            return []
        
        balances = []
        for account in data:
            for detail in account.get("details", []):
                eq = float(detail.get("eq", 0))
                if eq > 0:
                    balances.append({
                        "asset": detail["ccy"],
                        "equity": eq,
                        "available": float(detail.get("availBal", 0)),
                        "frozen": float(detail.get("frozenBal", 0)),
                        "usd_value": float(detail.get("eqUsd", 0))
                    })
        
        return balances
    
    def get_funding_balance(self) -> List[dict]:
        """获取资金账户余额"""
        data = self._request("/api/v5/asset/balances")
        if not data:
            return []
        
        balances = []
        for item in data:
            bal = float(item.get("bal", 0))
            if bal > 0:
                balances.append({
                    "asset": item["ccy"],
                    "balance": bal,
                    "available": float(item.get("availBal", 0)),
                    "frozen": float(item.get("frozenBal", 0))
                })
        
        return balances
    
    def get_asset_valuation(self) -> dict:
        """获取资产估值（BTC 计价）"""
        data = self._request("/api/v5/asset/asset-valuation")
        if not data:
            return {}
        
        return {
            "trading_btc": float(data[0]["details"].get("trading", 0)),
            "funding_btc": float(data[0]["details"].get("funding", 0)),
            "earn_btc": float(data[0]["details"].get("earn", 0)),
            "total_btc": float(data[0]["totalBal"]),
        }
    
    def get_savings_balance(self) -> List[dict]:
        """获取活期理财余额"""
        data = self._request("/api/v5/finance/savings/balance")
        if not data:
            return []
        
        balances = []
        for item in data:
            amt = float(item.get("amt", 0))
            if amt > 0:
                balances.append({
                    "asset": item["ccy"],
                    "amount": amt,
                    "earnings": float(item.get("earnings", 0)),
                })
        
        return balances
    
    def collect(self) -> dict:
        """采集完整资产数据"""
        result = {
            "exchange": "okx",
            "label": self.label,
            "total_usd": 0.0,
            "trading": [],
            "funding": [],
            "savings": [],
            "earn_btc": 0.0,
            "valuation": {},
            "collected_at": datetime.utcnow().isoformat()
        }
        
        # 交易账户
        trading = self.get_balance()
        for b in trading:
            result["total_usd"] += b["usd_value"]
        result["trading"] = trading
        
        # 资金账户
        result["funding"] = self.get_funding_balance()
        
        # 活期理财
        result["savings"] = self.get_savings_balance()
        
        # 资产估值（用于获取 earn 总额）
        valuation = self.get_asset_valuation()
        result["valuation"] = valuation
        result["earn_btc"] = valuation.get("earn_btc", 0)
        
        return result


if __name__ == "__main__":
    import yaml
    import os
    
    config_path = os.path.join(os.path.dirname(__file__), '../config/secrets.yaml')
    with open(config_path) as f:
        secrets = yaml.safe_load(f)
    
    accounts = secrets.get("exchanges", {}).get("okx", [])
    
    if not accounts:
        print("未配置 OKX API，跳过测试")
    else:
        for acc in accounts:
            collector = OKXCollector(
                acc["api_key"],
                acc["api_secret"],
                acc["passphrase"],
                acc.get("label", "default")
            )
            result = collector.collect()
            print(f"[{result['label']}]")
            print(f"  交易账户: ${result['total_usd']:,.2f}")
            print(f"  资金账户: {len(result['funding'])} 币种")
            print(f"  活期理财: {len(result['savings'])} 币种")
            print(f"  理财账户 (BTC): {result['earn_btc']:.8f} BTC")
            print(f"  资产估值: {result['valuation']}")
