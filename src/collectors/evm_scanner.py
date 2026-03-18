"""
EVM 链资产采集器 (Etherscan API V2)
统一端点，支持 60+ 条链
文档: https://docs.etherscan.io/v2-migration
"""
import requests
from typing import Optional, Dict, List
from datetime import datetime
import time


class EVMScannerCollector:
    """
    Etherscan API V2 采集器
    单一 API Key 支持所有 EVM 链
    """
    
    # V2 统一端点
    BASE_URL = "https://api.etherscan.io/v2/api"
    
    # Chain ID 映射
    CHAIN_IDS = {
        "eth": 1,
        "bsc": 56,
        "polygon": 137,
        "arbitrum": 42161,
        "optimism": 10,
        "base": 8453,
        "avalanche": 43114,
        "fantom": 250,
        "linea": 59144,
        "scroll": 534352,
        "zksync": 324,
        "mantle": 5000,
    }
    
    # 各链的原生代币
    NATIVE_TOKENS = {
        "eth": {"symbol": "ETH", "decimals": 18},
        "bsc": {"symbol": "BNB", "decimals": 18},
        "polygon": {"symbol": "POL", "decimals": 18},
        "arbitrum": {"symbol": "ETH", "decimals": 18},
        "optimism": {"symbol": "ETH", "decimals": 18},
        "base": {"symbol": "ETH", "decimals": 18},
        "avalanche": {"symbol": "AVAX", "decimals": 18},
        "fantom": {"symbol": "FTM", "decimals": 18},
        "linea": {"symbol": "ETH", "decimals": 18},
        "scroll": {"symbol": "ETH", "decimals": 18},
        "zksync": {"symbol": "ETH", "decimals": 18},
        "mantle": {"symbol": "MNT", "decimals": 18},
    }
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        # 速率限制：免费版 5 次/秒
        self.last_request_time = 0
        self.min_interval = 0.21
    
    def _rate_limit(self):
        """简单的速率限制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, chain: str, params: dict) -> Optional[dict]:
        """发送 API 请求"""
        if chain not in self.CHAIN_IDS:
            print(f"[EVMScanner] 不支持的链: {chain}")
            return None
        
        self._rate_limit()
        
        params["chainid"] = self.CHAIN_IDS[chain]
        params["apikey"] = self.api_key
        
        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == "1" or data.get("message") == "OK":
                return data
            else:
                msg = data.get("result", data.get("message", "Unknown"))
                if "No transactions found" not in str(msg):
                    print(f"[EVMScanner] API 提示 ({chain}): {msg}")
                return None
        except Exception as e:
            print(f"[EVMScanner] 请求失败 ({chain}): {e}")
            return None
    
    def get_native_balance(self, address: str, chain: str) -> Optional[float]:
        """获取原生代币余额 (ETH/BNB/POL 等)"""
        params = {
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest"
        }
        
        data = self._request(chain, params)
        if data and "result" in data:
            decimals = self.NATIVE_TOKENS.get(chain, {}).get("decimals", 18)
            balance = int(data["result"]) / (10 ** decimals)
            return balance
        return None
    
    def get_token_balances(self, address: str, chain: str) -> Optional[List[dict]]:
        """获取 ERC20 代币余额列表（通过交易历史推断）"""
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "sort": "desc",
            "page": 1,
            "offset": 100
        }
        
        data = self._request(chain, params)
        if not data or "result" not in data:
            return []
        
        # 从交易记录中提取唯一代币
        tokens_seen = {}
        for tx in data["result"]:
            contract = tx.get("contractAddress", "").lower()
            if contract and contract not in tokens_seen:
                tokens_seen[contract] = {
                    "contract": contract,
                    "symbol": tx.get("tokenSymbol", "UNKNOWN"),
                    "name": tx.get("tokenName", ""),
                    "decimals": int(tx.get("tokenDecimal", 18))
                }
        
        # 获取每个代币的当前余额（限制数量避免超出速率限制）
        token_list = []
        for contract, info in list(tokens_seen.items())[:10]:
            balance = self._get_token_balance(address, contract, chain)
            if balance and balance > 0:
                token_list.append({
                    "chain": chain,
                    "symbol": info["symbol"],
                    "name": info["name"],
                    "contract": contract,
                    "amount": balance / (10 ** info["decimals"]),
                    "decimals": info["decimals"]
                })
        
        return token_list
    
    def _get_token_balance(self, address: str, contract: str, chain: str) -> Optional[int]:
        """获取单个 ERC20 代币余额"""
        params = {
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": contract,
            "address": address,
            "tag": "latest"
        }
        
        data = self._request(chain, params)
        if data and "result" in data:
            try:
                return int(data["result"])
            except ValueError:
                return None
        return None
    
    def get_eth_price(self) -> Optional[float]:
        """获取 ETH 价格"""
        params = {
            "module": "stats",
            "action": "ethprice"
        }
        data = self._request("eth", params)
        if data and "result" in data:
            return float(data["result"].get("ethusd", 0))
        return None
    
    def get_bnb_price(self) -> Optional[float]:
        """获取 BNB 价格"""
        params = {
            "module": "stats",
            "action": "bnbprice"
        }
        data = self._request("bsc", params)
        if data and "result" in data:
            return float(data["result"].get("ethusd", 0))
        return None
    
    def collect_wallet(self, address: str, chains: List[str] = None) -> dict:
        """
        采集钱包在多条链上的资产
        """
        if chains is None:
            chains = ["eth", "bsc", "arbitrum", "polygon", "base", "optimism"]
        
        result = {
            "address": address,
            "total_usd": 0.0,
            "chains": {},
            "prices": {},
            "collected_at": datetime.utcnow().isoformat()
        }
        
        # 获取价格
        eth_price = self.get_eth_price() or 0
        bnb_price = self.get_bnb_price() or 0
        
        result["prices"] = {
            "ETH": eth_price,
            "BNB": bnb_price
        }
        
        # 简化的价格映射
        native_prices = {
            "eth": eth_price,
            "bsc": bnb_price,
            "polygon": 0.35,  # 需要单独 API，暂用估算
            "arbitrum": eth_price,
            "optimism": eth_price,
            "base": eth_price,
            "avalanche": 25,
            "fantom": 0.5,
            "linea": eth_price,
            "scroll": eth_price,
            "zksync": eth_price,
            "mantle": 0.8,
        }
        
        for chain in chains:
            if chain not in self.CHAIN_IDS:
                continue
                
            native_token = self.NATIVE_TOKENS.get(chain, {})
            chain_data = {
                "native_symbol": native_token.get("symbol", "?"),
                "native_balance": 0,
                "native_price": native_prices.get(chain, 0),
                "native_value_usd": 0,
                "tokens": []
            }
            
            # 获取原生代币余额
            native_balance = self.get_native_balance(address, chain)
            if native_balance:
                chain_data["native_balance"] = native_balance
                chain_data["native_value_usd"] = native_balance * chain_data["native_price"]
                result["total_usd"] += chain_data["native_value_usd"]
            
            result["chains"][chain] = chain_data
            print(f"  [{chain.upper()}] {native_token.get('symbol', '?')}: {native_balance or 0:.6f} (${chain_data['native_value_usd']:.2f})")
        
        return result


if __name__ == "__main__":
    # 测试
    API_KEY = "BUWR46PIP7JVZK98IP7YRQARRSABIP3V92"
    
    collector = EVMScannerCollector(API_KEY)
    
    # 测试地址（Vitalik）
    test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    
    print(f"\n采集钱包: {test_address[:10]}...")
    print("-" * 50)
    
    result = collector.collect_wallet(test_address, chains=["eth", "bsc", "arbitrum", "base"])
    
    print("-" * 50)
    print(f"总 USD 估值: ${result['total_usd']:,.2f}")
    print(f"ETH 价格: ${result['prices']['ETH']:,.2f}")
