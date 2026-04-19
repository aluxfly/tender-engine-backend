// CDP抓取 - 直接提取所有链接
const { chromium } = require('playwright');
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_PATH = path.join(__dirname, 'database.db');

async function main() {
  console.log('=== CDP抓取 ===');
  
  const SQL = await initSqlJs();
  const db = new SQL.Database();
  db.run(`
    CREATE TABLE bid_notices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      region TEXT,
      budget REAL,
      deadline TEXT,
      description TEXT,
      source_url TEXT UNIQUE NOT NULL,
      source_site TEXT NOT NULL,
      category TEXT,
      publish_date TEXT,
      crawl_time TEXT NOT NULL,
      content_hash TEXT
    )
  `);
  
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const context = browser.contexts()[0];
  const pages = context.pages();
  
  // 找到招标列表页面
  let targetPage = null;
  for (const page of pages) {
    const url = page.url();
    console.log('页面:', url);
    if (url.includes('list-spe') && url.includes('2018032700291334')) {
      targetPage = page;
      break;
    }
  }
  
  if (!targetPage) {
    targetPage = pages[0];
  }
  
  console.log('使用页面:', targetPage.url());
  
  // 等待一下
  await targetPage.waitForTimeout(5000);
  
  // 截图
  await targetPage.screenshot({ path: '/tmp/cdp_current.png' });
  
  // 提取所有链接
  const links = await targetPage.evaluate(() => {
    const results = [];
    document.querySelectorAll('a').forEach(a => {
      const href = a.href;
      const text = a.textContent?.trim();
      if (href && text && text.length > 5) {
        results.push({ href, text: text.substring(0, 100) });
      }
    });
    return results;
  });
  
  console.log(`\n找到 ${links.length} 个链接`);
  
  // 过滤招标相关链接
  const bidLinks = links.filter(l => 
    l.text.includes('招标') ||
    l.text.includes('采购') ||
    l.text.includes('公告') ||
    l.href.includes('detail') ||
    l.href.includes('doc')
  );
  
  console.log(`招标相关: ${bidLinks.length} 个\n`);
  
  // 打印前20个
  bidLinks.slice(0, 20).forEach((l, i) => {
    console.log(`${i+1}. ${l.text}`);
    console.log(`   ${l.href}`);
  });
  
  // 插入数据库
  const crawlTime = new Date().toISOString();
  let inserted = 0;
  
  for (const link of bidLinks) {
    if (link.href.startsWith('http')) {
      try {
        const contentHash = crypto.createHash('md5').update(link.href).digest('hex');
        db.run(
          `INSERT OR IGNORE INTO bid_notices (title, source_url, source_site, category, crawl_time, content_hash) VALUES (?, ?, ?, ?, ?, ?)`,
          [link.text, link.href, '国家电网电子商务平台', '招标公告', crawlTime, contentHash]
        );
        if (db.getRowsModified() > 0) inserted++;
      } catch (e) {}
    }
  }
  
  // 保存
  const data = db.export();
  fs.writeFileSync(DB_PATH, Buffer.from(data));
  
  console.log(`\n插入: ${inserted} 条`);
  console.log(`数据库: ${DB_PATH}`);
}

main().catch(console.error);
