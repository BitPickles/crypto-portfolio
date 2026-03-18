#!/usr/bin/env python3
"""
Crypto Portfolio - 加密资产统计系统
主程序入口
"""
import os
import sys
import yaml
import argparse
from datetime import datetime
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.models import init_db, get_session, Wallet, CexAccount, Snapshot, AssetDetail
from src.collectors.evm_scanner import EVMScannerCollector
from src.collectors.binance import BinanceCollector
from src.collectors.bybit import BybitCollector
from src.collectors.okx import OKXCollector
from src.collectors.bitget import BitgetCollector


def load_config():
    """加载配置文件"""
    config_dir = PROJECT_ROOT / "config"
    
    secrets = {}
    wallets = []
    
    secrets_file = config_dir / "secrets.yaml"
    if secrets_file.exists():
        with open(secrets_file) as f:
            secrets = yaml.safe_load(f) or {}
    
    wallets_file = config_dir / "wallets.yaml"
    if wallets_file.exists():
        with open(wallets_file) as f:
            data = yaml.safe_load(f) or {}
            wallets = data.get("wallets", [])
    
    return secrets, wallets


def collect_wallets(secrets: dict, wallets: list, session) -> list:
    """采集所有钱包数据"""
    results = []
    
    etherscan_key = secrets.get("etherscan", {}).get("api_key")
    if not etherscan_key:
        print("⚠️  未配置 Etherscan API Key")
        return results
    
    if not wallets:
        print("⚠️  未配置钱包地址")
        return results
    
    collector = EVMScannerCollector(etherscan_key)
    
    for w in wallets:
        address = w.get("address")
        label = w.get("label", address[:10])
        
        if not address:
            continue
        
        print(f"\n📍 采集钱包: {label}")
        print("-" * 40)
        
        # 检查或创建钱包记录
        wallet = session.query(Wallet).filter_by(address=address.lower()).first()
        if not wallet:
            wallet = Wallet(address=address.lower(), label=label)
            session.add(wallet)
            session.commit()
        
        # 采集数据
        data = collector.collect_wallet(address, chains=["eth", "arbitrum", "optimism", "polygon"])
        
        # 创建快照
        snapshot = Snapshot(
            source_type="wallet",
            wallet_id=wallet.id,
            total_usd=data["total_usd"],
            snapshot_time=datetime.utcnow()
        )
        session.add(snapshot)
        session.commit()
        
        # 添加资产明细
        for chain, chain_data in data["chains"].items():
            if chain_data["native_balance"] > 0:
                detail = AssetDetail(
                    snapshot_id=snapshot.id,
                    asset_type="token",
                    symbol=chain_data["native_symbol"],
                    chain=chain,
                    amount=chain_data["native_balance"],
                    price_usd=chain_data["native_price"],
                    value_usd=chain_data["native_value_usd"]
                )
                session.add(detail)
        
        session.commit()
        
        results.append({
            "type": "wallet",
            "label": label,
            "total_usd": data["total_usd"]
        })
        
        print(f"✅ 总计: ${data['total_usd']:,.2f}")
    
    return results


def collect_exchanges(secrets: dict, session) -> list:
    """采集所有交易所数据"""
    results = []
    exchanges = secrets.get("exchanges", {})
    
    collectors = {
        "binance": BinanceCollector,
        "bybit": BybitCollector,
        "okx": OKXCollector,
        "bitget": BitgetCollector
    }
    
    for exchange_name, accounts in exchanges.items():
        if not accounts or exchange_name not in collectors:
            continue
        
        for acc in accounts:
            api_key = acc.get("api_key")
            api_secret = acc.get("api_secret")
            label = acc.get("label", "default")
            
            if not api_key or not api_secret:
                continue
            
            print(f"\n🏦 采集 {exchange_name.upper()}: {label}")
            print("-" * 40)
            
            try:
                # 创建采集器
                if exchange_name in ["okx", "bitget"]:
                    passphrase = acc.get("passphrase", "")
                    collector = collectors[exchange_name](api_key, api_secret, passphrase, label)
                else:
                    collector = collectors[exchange_name](api_key, api_secret, label)
                
                # 检查或创建 CEX 账户记录
                cex_account = session.query(CexAccount).filter_by(
                    exchange=exchange_name,
                    account_label=label
                ).first()
                
                if not cex_account:
                    cex_account = CexAccount(
                        exchange=exchange_name,
                        account_label=label,
                        api_key_ref=f"{exchange_name}:{label}"
                    )
                    session.add(cex_account)
                    session.commit()
                
                # 采集数据
                data = collector.collect()
                
                # 创建快照
                snapshot = Snapshot(
                    source_type="cex",
                    cex_account_id=cex_account.id,
                    total_usd=data["total_usd"],
                    snapshot_time=datetime.utcnow()
                )
                session.add(snapshot)
                session.commit()
                
                # 添加资产明细
                for asset_type in ["spot", "futures", "coin_futures", "earn", "unified", "trading", "funding"]:
                    for item in data.get(asset_type, []):
                        if item.get("value_usd", 0) > 0 or item.get("usd_value", 0) > 0:
                            detail = AssetDetail(
                                snapshot_id=snapshot.id,
                                asset_type=asset_type,
                                symbol=item.get("asset", "UNKNOWN"),
                                amount=item.get("total", item.get("balance", item.get("equity", 0))),
                                price_usd=item.get("price_usd", 0),
                                value_usd=item.get("value_usd", item.get("usd_value", 0))
                            )
                            session.add(detail)
                
                session.commit()
                
                results.append({
                    "type": "cex",
                    "exchange": exchange_name,
                    "label": label,
                    "total_usd": data["total_usd"]
                })
                
                print(f"✅ 总计: ${data['total_usd']:,.2f}")
                
            except Exception as e:
                print(f"❌ 采集失败: {e}")
    
    return results


def cmd_collect(args):
    """执行数据采集"""
    print("=" * 50)
    print("📊 Crypto Portfolio - 数据采集")
    print("=" * 50)
    
    secrets, wallets = load_config()
    
    # 初始化数据库
    db_path = PROJECT_ROOT / "portfolio.db"
    engine = init_db(str(db_path))
    session = get_session(engine)
    
    all_results = []
    
    # 采集钱包
    wallet_results = collect_wallets(secrets, wallets, session)
    all_results.extend(wallet_results)
    
    # 采集交易所
    exchange_results = collect_exchanges(secrets, session)
    all_results.extend(exchange_results)
    
    # 汇总
    print("\n" + "=" * 50)
    print("📈 采集汇总")
    print("=" * 50)
    
    total_usd = sum(r["total_usd"] for r in all_results)
    
    for r in all_results:
        if r["type"] == "wallet":
            print(f"  🔗 钱包 {r['label']}: ${r['total_usd']:,.2f}")
        else:
            print(f"  🏦 {r['exchange'].upper()} {r['label']}: ${r['total_usd']:,.2f}")
    
    print("-" * 50)
    print(f"  💰 总资产: ${total_usd:,.2f}")
    print("=" * 50)
    
    session.close()


def cmd_summary(args):
    """查看资产汇总"""
    db_path = PROJECT_ROOT / "portfolio.db"
    
    if not db_path.exists():
        print("❌ 数据库不存在，请先运行 collect 命令")
        return
    
    engine = init_db(str(db_path))
    session = get_session(engine)
    
    print("=" * 50)
    print("📊 资产汇总")
    print("=" * 50)
    
    # 获取最新快照
    from sqlalchemy import func
    
    # 钱包
    print("\n🔗 链上钱包:")
    wallets = session.query(Wallet).all()
    wallet_total = 0
    for w in wallets:
        latest = session.query(Snapshot).filter_by(
            source_type="wallet", wallet_id=w.id
        ).order_by(Snapshot.snapshot_time.desc()).first()
        
        if latest:
            print(f"  {w.label}: ${latest.total_usd:,.2f}")
            wallet_total += latest.total_usd
    
    print(f"  小计: ${wallet_total:,.2f}")
    
    # 交易所
    print("\n🏦 交易所:")
    cex_accounts = session.query(CexAccount).all()
    cex_total = 0
    for acc in cex_accounts:
        latest = session.query(Snapshot).filter_by(
            source_type="cex", cex_account_id=acc.id
        ).order_by(Snapshot.snapshot_time.desc()).first()
        
        if latest:
            print(f"  {acc.exchange.upper()} ({acc.account_label}): ${latest.total_usd:,.2f}")
            cex_total += latest.total_usd
    
    print(f"  小计: ${cex_total:,.2f}")
    
    print("\n" + "=" * 50)
    print(f"💰 总资产: ${wallet_total + cex_total:,.2f}")
    print("=" * 50)
    
    session.close()


def main():
    parser = argparse.ArgumentParser(description="Crypto Portfolio - 加密资产统计系统")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # collect 命令
    collect_parser = subparsers.add_parser("collect", help="采集资产数据")
    collect_parser.set_defaults(func=cmd_collect)
    
    # summary 命令
    summary_parser = subparsers.add_parser("summary", help="查看资产汇总")
    summary_parser.set_defaults(func=cmd_summary)
    
    args = parser.parse_args()
    
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
