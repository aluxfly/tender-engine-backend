// CDP抓取 - 直接访问搜索结果
const { chromium } = require('playwright');
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_PATH = path.join(__dirname, 'database.db');

async function main() {
  console.log('=== CDP抓取搜索结果 ===');
  
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
  const page = await context.newPage();
  
  // 直接访问搜索结果页面
  const keywords = ['物联网卡', '布控球', '视频监控'];
  const crawlTime = new Date().toISOString();
  let totalInserted = 0;
  
  for (const keyword of keywords) {
    console.log(`\n=== 搜索: ${keyword} ===`);
    
    const searchUrl = `https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/search_list/${Date.now()}?keyword=${encodeURIComponent(keyword)}`;
    console.log('URL:', searchUrl);
    
    await page.goto(searchUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(8000);
    
    // 截图
    await page.screenshot({ path: `/tmp/search_${keyword}.png` });
    
    // 提取搜索结果
    const results = await page.evaluate(() => {
      const items = [];
      
      // 查找所有链接
      document.querySelectorAll('a').forEach(a => {
        const href = a.href;
        const text = a.textContent?.trim();
        
        if (href && text && text.length > 15 && (
          text.includes('招标') ||
          text.includes('采购') ||
          text.includes('公告') ||
          text.includes('项目') ||
          href.includes('detail') ||
          href.includes('doc')
        )) {
          items.push({ href, text: text.substring(0, 150) });
        }
      });
      
      return items;
    });
    
    console.log(`找到 ${results.length} 个结果`);
    
    for (const item of results) {
      if (item.href.startsWith('http')) {
        console.log(`- ${item.text}`);
        console.log(`  ${item.href}`);
        
        try {
          const contentHash = crypto.createHash('md5').update(item.href).digest('hex');
          db.run(
            `INSERT OR IGNORE INTO bid_notices (title, source_url, source_site, category, crawl_time, content_hash) VALUES (?, ?, ?, ?, ?, ?)`,
            [item.text, item.href, '国家电网电子商务平台', keyword, crawlTime, contentHash]
          );
          if (db.getRowsModified() > 0) totalInserted++;
        } catch (e) {}
      }
    }
  }
  
  // 保存
  const data = db.export();
  fs.writeFileSync(DB_PATH, Buffer.from(data));
  
  console.log(`\n=== 完成 ===`);
  console.log(`插入: ${totalInserted} 条`);
  
  // 验证
  const result = db.exec('SELECT COUNT(*) FROM bid_notices');
  console.log(`总计: ${result[0]?.values[0]?.[0] || 0} 条`);
}

main().catch(console.error);
