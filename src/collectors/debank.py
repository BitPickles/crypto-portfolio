"""
DeBank OpenAPI 数据采集器
文档: https://docs.cloud.debank.com/en/readme/api-pro-reference
"""
import requests
from typing import Optional
from datetime import datetime


class DeBankCollector:
    """DeBank 链上资产采集器"""
    
    BASE_URL = "https://pro-openapi.debank.com/v1"
    
    def __init__(self, access_key: str):
        self.access_key = access_key
        self.session = requests.Session()
        self.session.headers.update({
            "AccessKey": access_key
        })
    
    def get_total_balance(self, address: str) -> Optional[dict]:
        """
        获取钱包总资产（USD）
        """
        url = f"{self.BASE_URL}/user/total_balance"
        params = {"id": address.lower()}
        
        try:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[DeBank] 获取总资产失败: {e}")
            return None
    
    def get_token_list(self, address: str, chain_id: str = None) -> Optional[list]:
        """
        获取代币列表
        chain_id: eth, bsc, arb, op, matic, avax, ftm, etc.
        """
        url = f"{self.BASE_URL}/user/all_token_list"
        params = {"id": address.lower()}
        if chain_id:
            params["chain_id"] = chain_id
        
        try:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[DeBank] 获取代币列表失败: {e}")
            return None
    
    def get_protocol_list(self, address: str) -> Optional[list]:
        """
        获取 DeFi 协议仓位
        """
        url = f"{self.BASE_URL}/user/all_complex_protocol_list"
        params = {"id": address.lower()}
        
        try:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[DeBank] 获取 DeFi 仓位失败: {e}")
            return None
    
    def collect_wallet(self, address: str) -> dict:
        """
        采集钱包完整数据
        返回格式:
        {
            "address": "0x...",
            "total_usd": 12345.67,
            "tokens": [...],
            "protocols": [...],
            "collected_at": "2024-..."
        }
        """
        result = {
            "address": address,
            "total_usd": 0.0,
            "tokens": [],
            "protocols": [],
            "collected_at": datetime.utcnow().isoformat()
        }
        
        # 获取总资产
        balance = self.get_total_balance(address)
        if balance:
            result["total_usd"] = balance.get("total_usd_value", 0.0)
        
        # 获取代币列表
        tokens = self.get_token_list(address)
        if tokens:
            result["tokens"] = [
                {
                    "chain": t.get("chain"),
                    "symbol": t.get("symbol"),
                    "amount": t.get("amount", 0),
                    "price_usd": t.get("price", 0),
                    "value_usd": t.get("amount", 0) * t.get("price", 0)
                }
                for t in tokens
                if t.get("amount", 0) * t.get("price", 0) > 0.01  # 过滤小额
            ]
        
        # 获取 DeFi 仓位
        protocols = self.get_protocol_list(address)
        if protocols:
            for p in protocols:
                protocol_name = p.get("name", "Unknown")
                chain = p.get("chain", "")
                for item in p.get("portfolio_item_list", []):
                    net_usd = item.get("stats", {}).get("net_usd_value", 0)
                    if net_usd > 0.01:
                        result["protocols"].append({
                            "protocol": protocol_name,
                            "chain": chain,
                            "name": item.get("name", ""),
                            "value_usd": net_usd
                        })
        
        return result


if __name__ == "__main__":
    # 测试
    import yaml
    
    with open("config/secrets.yaml") as f:
        secrets = yaml.safe_load(f)
    
    collector = DeBankCollector(secrets["debank"]["access_key"])
    
    # 测试地址（Vitalik）
    test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    result = collector.collect_wallet(test_address)
    print(f"总资产: ${result['total_usd']:,.2f}")
    print(f"代币数: {len(result['tokens'])}")
    print(f"DeFi 仓位数: {len(result['protocols'])}")
