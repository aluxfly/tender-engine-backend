// CDP抓取 - 点击菜单后抓取数据
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
  const page = await context.newPage();
  
  // 访问招标公告页面
  const url = 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/list/list-spe/2018032600289606_1_2018032700291334';
  console.log('访问:', url);
  
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);
  
  // 点击"招标公告及投标邀请书"
  console.log('查找"招标公告及投标邀请书"菜单...');
  
  const menuItems = await page.$$('a');
  for (const item of menuItems) {
    const text = await item.textContent();
    if (text?.includes('招标公告及投标邀请书')) {
      console.log('找到菜单，点击...');
      await item.click();
      await page.waitForTimeout(8000);
      break;
    }
  }
  
  // 截图
  await page.screenshot({ path: '/tmp/cdp_after_click.png', fullPage: true });
  
  // 等待表格加载
  console.log('等待表格数据...');
  await page.waitForTimeout(5000);
  
  // 提取表格数据
  const tableData = await page.evaluate(() => {
    const results = [];
    
    // 查找表格
    const tables = document.querySelectorAll('table, .el-table');
    console.log('找到表格:', tables.length);
    
    tables.forEach(table => {
      const rows = table.querySelectorAll('tr');
      console.log('表格行数:', rows.length);
      
      rows.forEach(row => {
        const cells = row.querySelectorAll('td, th');
        const rowData = [];
        cells.forEach(cell => {
          rowData.push(cell.textContent?.trim());
        });
        
        // 查找链接
        const link = row.querySelector('a');
        const href = link?.href;
        const title = link?.textContent?.trim();
        
        if (title && title.length > 10 && href) {
          results.push({
            title,
            href,
            cells: rowData
          });
        }
      });
    });
    
    return results;
  });
  
  console.log(`\n找到 ${tableData.length} 条表格数据\n`);
  
  // 插入数据库
  const crawlTime = new Date().toISOString();
  let inserted = 0;
  
  for (const item of tableData) {
    if (item.href && item.href.startsWith('http')) {
      console.log(`- ${item.title}`);
      console.log(`  ${item.href}`);
      console.log(`  数据: ${item.cells?.join(' | ')}`);
      
      try {
        const contentHash = crypto.createHash('md5').update(item.href).digest('hex');
        db.run(
          `INSERT OR IGNORE INTO bid_notices (title, source_url, source_site, category, crawl_time, content_hash) VALUES (?, ?, ?, ?, ?, ?)`,
          [item.title, item.href, '国家电网电子商务平台', '招标公告', crawlTime, contentHash]
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
}

main().catch(console.error);
