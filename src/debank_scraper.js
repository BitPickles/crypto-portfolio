#!/usr/bin/env node
/**
 * Debank 钱包资产抓取器
 * 自动获取链上钱包的 DeFi 仓位
 */

const puppeteer = require('puppeteer');
const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = path.join(__dirname, '..', 'portfolio.db');

class DebankScraper {
  constructor() {
    this.db = new Database(DB_PATH);
  }

  async getWallets() {
    return this.db.prepare('SELECT * FROM wallets WHERE is_active = 1').all();
  }

  async scrapeAddress(address) {
    const browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    
    try {
      const url = `https://debank.com/profile/${address}`;
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
      
      // 等待资产加载
      await page.waitForSelector('[class*="HeaderInfo_totalAssetInner"]', { timeout: 15000 });
      
      // 提取总资产
      const totalText = await page.$eval('[class*="HeaderInfo_totalAssetInner"]', el => el.textContent).catch(() => '$0');
      const totalMatch = totalText.match(/\$([\d,]+\.?\d*)/);
      const totalUsd = totalMatch ? parseFloat(totalMatch[1].replace(/,/g, '')) : 0;
      
      // 尝试提取 token 列表 (可能需要调整选择器)
      const tokens = await page.evaluate(() => {
        const items = document.querySelectorAll('[class*="TokenCell_tokenCell"]');
        return Array.from(items).map(item => {
          const symbol = item.querySelector('[class*="TokenCell_tokenSymbol"]')?.textContent || '';
          const amount = item.querySelector('[class*="TokenCell_tokenAmount"]')?.textContent || '';
          const value = item.querySelector('[class*="TokenCell_tokenValue"]')?.textContent || '';
          return { symbol, amount, value };
        }).filter(t => t.symbol);
      }).catch(() => []);
      
      return { address, totalUsd, tokens, success: true };
      
    } catch (error) {
      console.error(`Error scraping ${address}:`, error.message);
      return { address, totalUsd: 0, tokens: [], success: false, error: error.message };
    } finally {
      await browser.close();
    }
  }

  saveToSnapshot(snapshotId, wallet, data) {
    // 保存到 balances 表
    const stmt = this.db.prepare(`
      INSERT INTO balances (snapshot_id, source, account_label, coin, quantity, price_usd, value_usd, extra_info)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    
    // 如果有详细 token 列表
    if (data.tokens && data.tokens.length > 0) {
      for (const token of data.tokens) {
        const amount = parseFloat(token.amount.replace(/,/g, '')) || 0;
        const value = parseFloat(token.value.replace(/[$,]/g, '')) || 0;
        const price = amount > 0 ? value / amount : 0;
        
        stmt.run(
          snapshotId,
          'debank_wallet',
          wallet.label,
          token.symbol.toUpperCase(),
          amount,
          price,
          value,
          JSON.stringify({ address: wallet.address })
        );
      }
    } else {
      // 只有总资产，存为 WALLET_TOTAL
      stmt.run(
        snapshotId,
        'debank_wallet',
        wallet.label,
        'WALLET_TOTAL',
        1,
        data.totalUsd,
        data.totalUsd,
        JSON.stringify({ address: wallet.address, note: '总资产(无明细)' })
      );
    }
  }

  async run(snapshotId = null) {
    const wallets = await this.getWallets();
    
    if (wallets.length === 0) {
      console.log('没有配置需要追踪的钱包');
      return [];
    }
    
    console.log(`=== Debank 钱包抓取 (${wallets.length} 个) ===\n`);
    
    const results = [];
    
    for (const wallet of wallets) {
      console.log(`抓取: ${wallet.label} (${wallet.address.slice(0,6)}...${wallet.address.slice(-4)})`);
      
      const data = await this.scrapeAddress(wallet.address);
      results.push({ wallet, data });
      
      if (data.success) {
        console.log(`  ✅ $${data.totalUsd.toLocaleString()}`);
        
        if (snapshotId) {
          this.saveToSnapshot(snapshotId, wallet, data);
        }
      } else {
        console.log(`  ❌ ${data.error}`);
      }
      
      console.log('');
    }
    
    return results;
  }

  close() {
    this.db.close();
  }
}

// CLI 入口
async function main() {
  const scraper = new DebankScraper();
  const jsonMode = process.argv.includes('--json');
  
  try {
    const results = await scraper.run();
    
    if (jsonMode) {
      // JSON 模式供 Python 调用
      console.log(JSON.stringify(results));
    } else {
      // 人类可读模式
      console.log('=== 汇总 ===');
      let total = 0;
      for (const { wallet, data } of results) {
        if (data.success) {
          total += data.totalUsd;
          console.log(`${wallet.label}: $${data.totalUsd.toLocaleString()}`);
          if (wallet.expires_at) {
            console.log(`  ⏰ 到期: ${wallet.expires_at}`);
          }
        }
      }
      console.log(`\n总计: $${total.toLocaleString()}`);
    }
    
  } finally {
    scraper.close();
  }
}

// 导出供 collector.py 调用
module.exports = { DebankScraper };

if (require.main === module) {
  main();
}
