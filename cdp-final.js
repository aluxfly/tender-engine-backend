// CDP抓取 - 使用正确的页面并等待数据加载
const { chromium } = require('playwright');
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_PATH = path.join(__dirname, 'database.db');

async function main() {
  console.log('=== CDP抓取真实数据 ===');
  console.log('时间:', new Date().toISOString());
  
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
  
  // 创建新页面
  const page = await context.newPage();
  
  // 访问招标公告列表
  const url = 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/list/list-spe/2018032600289606_1_2018032700291334';
  console.log('访问:', url);
  
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  console.log('页面加载，等待数据...');
  
  // 等待数据加载 - 多次检查
  for (let i = 0; i < 10; i++) {
    await page.waitForTimeout(3000);
    
    const links = await page.evaluate(() => {
      return document.querySelectorAll('a').length;
    });
    
    console.log(`检查 ${i+1}: 找到 ${links} 个链接`);
    
    if (links > 50) {
      console.log('数据加载完成！');
      break;
    }
  }
  
  // 截图
  await page.screenshot({ path: '/tmp/cdp_final.png', fullPage: true });
  
  // 提取所有链接
  const allLinks = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('a').forEach(a => {
      const href = a.href;
      const text = a.textContent?.trim();
      if (href && text && text.length > 5) {
        results.push({ href, text: text.substring(0, 150) });
      }
    });
    return results;
  });
  
  console.log(`\n总链接数: ${allLinks.length}`);
  
  // 过滤招标相关
  const bidLinks = allLinks.filter(l => 
    l.text.includes('招标') ||
    l.text.includes('采购') ||
    l.text.includes('公告') ||
    l.text.includes('项目') ||
    l.href.includes('detail') ||
    l.href.includes('doc')
  );
  
  console.log(`招标相关: ${bidLinks.length} 个\n`);
  
  // 打印并插入
  const crawlTime = new Date().toISOString();
  let inserted = 0;
  
  for (const link of bidLinks) {
    if (link.href.startsWith('http') && link.text.length > 10) {
      console.log(`- ${link.text}`);
      console.log(`  ${link.href}`);
      
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
  
  console.log(`\n=== 完成 ===`);
  console.log(`插入: ${inserted} 条`);
  console.log(`数据库: ${DB_PATH}`);
  
  // 验证
  const result = db.exec('SELECT COUNT(*) as count FROM bid_notices');
  console.log(`总计: ${result[0]?.values[0]?.[0] || 0} 条`);
}

main().catch(console.error);
