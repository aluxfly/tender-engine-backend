// CDP抓取脚本 - 使用Playwright连接真实Chrome浏览器
const { chromium } = require('playwright');
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_PATH = path.join(__dirname, 'database.db');
const CDP_PORT = 9222;

async function initDB() {
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
  return { SQL, db };
}

function saveDB(SQL, db) {
  const data = db.export();
  const buffer = Buffer.from(data);
  fs.writeFileSync(DB_PATH, buffer);
}

function insertProject(db, project) {
  const crawlTime = new Date().toISOString();
  const contentHash = crypto.createHash('md5').update(project.source_url).digest('hex');
  
  try {
    db.run(
      `INSERT OR IGNORE INTO bid_notices (title, region, budget, deadline, description, source_url, source_site, category, publish_date, crawl_time, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [project.title, project.region, project.budget, project.deadline, project.description, project.source_url, project.source_site, project.category, project.publish_date, crawlTime, contentHash]
    );
    return db.getRowsModified();
  } catch (e) {
    return 0;
  }
}

async function main() {
  console.log('=== CDP抓取真实数据 ===');
  console.log('时间:', new Date().toISOString());
  
  const { SQL, db } = await initDB();
  console.log('[DB] 数据库初始化完成');
  
  let browser;
  try {
    // 连接到CDP
    console.log(`[CDP] 连接到 localhost:${CDP_PORT}...`);
    browser = await chromium.connectOverCDP(`http://localhost:${CDP_PORT}`);
    console.log('[CDP] 连接成功！');
    
    // 获取现有上下文
    const contexts = browser.contexts();
    console.log(`[CDP] 找到 ${contexts.length} 个上下文`);
    
    const context = contexts[0] || await browser.newContext();
    const pages = context.pages();
    console.log(`[CDP] 找到 ${pages.length} 个页面`);
    
    // 打印所有页面URL
    for (let i = 0; i < pages.length; i++) {
      const url = pages[i].url();
      console.log(`[PAGE ${i}] ${url}`);
    }
    
    // 使用第一个页面或创建新页面
    let page = pages[0];
    if (!page) {
      page = await context.newPage();
    }
    
    // 访问国家电网ECP招标公告列表
    const targetUrl = 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/list/list-spe/2018032600289606_1_2018032700291334';
    console.log(`[NAV] 导航到: ${targetUrl}`);
    
    await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 60000 });
    console.log('[NAV] 页面加载完成');
    
    // 等待SPA渲染 - 增加等待时间
    console.log('[WAIT] 等待动态内容加载...');
    await page.waitForTimeout(15000);
    
    // 截图
    await page.screenshot({ path: '/tmp/cdp_sgcc_full.png', fullPage: true });
    console.log('[SCREEN] 截图保存: /tmp/cdp_sgcc_full.png');
    
    // 获取页面内容
    const html = await page.content();
    fs.writeFileSync('/tmp/cdp_sgcc_content.html', html);
    console.log('[HTML] 内容保存: /tmp/cdp_sgcc_content.html');
    
    // 提取项目列表 - 使用多种选择器
    const projects = await page.evaluate(() => {
      const items = [];
      
      // 方法1: 查找表格行
      const tableRows = document.querySelectorAll('tr, .el-table__row, [class*="row"]');
      console.log('表格行数:', tableRows.length);
      
      tableRows.forEach((row, idx) => {
        const text = row.textContent || '';
        const links = row.querySelectorAll('a');
        
        links.forEach(link => {
          const title = link.textContent?.trim();
          const href = link.href;
          
          if (title && title.length > 10 && href && (
            href.includes('detail') || 
            href.includes('doc') ||
            text.includes('招标') ||
            text.includes('采购')
          )) {
            // 提取预算
            const budgetMatch = text.match(/(\d+[,，]?\d*\.?\d*)\s*[万元]/);
            const budget = budgetMatch ? parseFloat(budgetMatch[1].replace(/[^\d.]/g, '')) : null;
            
            // 提取日期
            const dateMatch = text.match(/(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)/);
            const date = dateMatch ? dateMatch[1] : null;
            
            items.push({ title, href, budget, date });
          }
        });
      });
      
      // 方法2: 查找所有包含招标信息的链接
      const allLinks = document.querySelectorAll('a');
      console.log('总链接数:', allLinks.length);
      
      allLinks.forEach(link => {
        const title = link.textContent?.trim();
        const href = link.href;
        
        if (title && title.length > 15 && href && (
          title.includes('招标') ||
          title.includes('采购') ||
          title.includes('公告') ||
          title.includes('项目')
        )) {
          // 避免重复
          if (!items.find(i => i.href === href)) {
            items.push({ title, href, budget: null, date: null });
          }
        }
      });
      
      return items;
    });
    
    console.log(`[DATA] 找到 ${projects.length} 个项目`);
    
    // 插入数据库
    let inserted = 0;
    for (const project of projects) {
      if (project.href && project.href.startsWith('http')) {
        const changes = insertProject(db, {
          title: project.title,
          region: '国家电网',
          budget: project.budget,
          deadline: project.date,
          description: project.title,
          source_url: project.href,
          source_site: '国家电网电子商务平台',
          category: '招标公告',
          publish_date: project.date
        });
        if (changes > 0) {
          inserted++;
          console.log(`[INSERT] ${project.title.substring(0, 50)}...`);
          console.log(`         URL: ${project.href}`);
        }
      }
    }
    
    // 保存数据库
    saveDB(SQL, db);
    
    console.log(`\n=== 抓取完成 ===`);
    console.log(`插入: ${inserted} 条`);
    console.log(`数据库: ${DB_PATH}`);
    
  } catch (error) {
    console.error('[ERROR]', error.message);
    console.error(error.stack);
  } finally {
    // 不关闭browser，保持CDP连接
    console.log('[DONE] 保持CDP连接');
  }
}

main().catch(console.error);
