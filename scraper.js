const puppeteer = require('puppeteer');
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_PATH = path.join(__dirname, 'database.db');

// 初始化数据库
async function initDB() {
  const SQL = await initSqlJs();
  
  if (fs.existsSync(DB_PATH)) {
    const fileBuffer = fs.readFileSync(DB_PATH);
    const db = new SQL.Database(fileBuffer);
    return { SQL, db };
  }
  
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

// 保存数据库
function saveDB(SQL, db) {
  const data = db.export();
  const buffer = Buffer.from(data);
  fs.writeFileSync(DB_PATH, buffer);
}

// 插入项目
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

// 国家电网 - 获取招标公告列表
async function scrapeSGCC(keyword, browser) {
  const results = [];
  const page = await browser.newPage();
  
  try {
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    
    // 访问招标公告列表
    const listUrl = 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/list/list-spe/2018032600289606_1_2018032700290425';
    console.log(`[SGCC] 访问招标公告列表`);
    
    await page.goto(listUrl, { waitUntil: 'networkidle2', timeout: 60000 });
    await new Promise(r => setTimeout(r, 5000));
    
    // 点击"招标公告及投标邀请书"
    console.log(`[SGCC] 点击"招标公告及投标邀请书"`);
    const bidNoticeLink = await page.$('text=/招标公告及投标邀请书/');
    if (bidNoticeLink) {
      await bidNoticeLink.click();
      await new Promise(r => setTimeout(r, 5000));
    }
    
    await page.screenshot({ path: `/tmp/sgcc_bid_list_${keyword}.png`, fullPage: true });
    
    // 获取页面HTML内容分析
    const pageContent = await page.content();
    fs.writeFileSync(`/tmp/sgcc_html_${keyword}.html`, pageContent);
    
    // 提取项目列表 - 使用更通用的方法
    const projects = await page.evaluate(() => {
      const items = [];
      
      // 获取所有表格行
      const tables = document.querySelectorAll('table, .el-table, [class*="table"]');
      console.log('找到表格数:', tables.length);
      
      // 遍历所有链接，查找包含项目信息的
      const allLinks = document.querySelectorAll('a');
      allLinks.forEach(link => {
        const href = link.href;
        const text = link.textContent.trim();
        const parent = link.closest('tr, li, .row, [class*="item"]');
        const parentText = parent?.textContent || '';
        
        // 匹配项目特征：有编号、有日期、有预算等
        if (href && text && text.length > 10 && (
          href.includes('detail') ||
          href.includes('project') ||
          href.includes('notice') ||
          parentText.includes('万元') ||
          parentText.includes('采购') ||
          parentText.includes('招标')
        )) {
          // 提取预算
          const budgetMatch = parentText.match(/(\d+[,，]?\d*\.?\d*)\s*[万元]/);
          const budget = budgetMatch ? budgetMatch[1] : null;
          
          // 提取日期
          const dateMatch = parentText.match(/(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)/);
          const date = dateMatch ? dateMatch[1] : null;
          
          items.push({
            title: text,
            href: href,
            budget: budget,
            date: date
          });
        }
      });
      
      return items;
    });
    
    console.log(`[SGCC] 找到 ${projects.length} 个潜在项目`);
    
    // 过滤并插入
    const validProjects = projects.filter(p => 
      p.title && 
      p.title.length > 15 && 
      !p.title.includes('首页') &&
      !p.title.includes('登录') &&
      !p.title.includes('注册')
    );
    
    console.log(`[SGCC] 有效项目: ${validProjects.length} 个`);
    
    for (const project of validProjects.slice(0, 30)) {
      results.push({
        title: project.title,
        region: '国家电网',
        budget: project.budget ? parseFloat(project.budget.replace(/[^\d.]/g, '')) : null,
        deadline: project.date,
        description: project.title,
        source_url: project.href,
        source_site: '国家电网电子商务平台',
        category: keyword,
        publish_date: project.date
      });
    }
    
  } catch (error) {
    console.error(`[SGCC] 错误: ${error.message}`);
  } finally {
    await page.close();
  }
  
  return results;
}

// 政府采购网抓取
async function scrapeCCGP(keyword, browser) {
  const results = [];
  const page = await browser.newPage();
  
  try {
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    
    const searchUrl = `http://search.ccgp.gov.cn/bxsearch?searchtype=1&bidSort=0&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx&kw=${encodeURIComponent(keyword)}&start_time=&end_time=&page_index=1`;
    console.log(`[CCGP] 访问: ${searchUrl}`);
    
    await page.goto(searchUrl, { waitUntil: 'networkidle2', timeout: 60000 });
    await new Promise(r => setTimeout(r, 5000));
    
    await page.screenshot({ path: `/tmp/ccgp_search_${keyword}.png`, fullPage: true });
    
    // 保存HTML
    const html = await page.content();
    fs.writeFileSync(`/tmp/ccgp_html_${keyword}.html`, html);
    
    // 提取搜索结果
    const projects = await page.evaluate(() => {
      const items = [];
      
      // 查找所有链接
      document.querySelectorAll('a').forEach(link => {
        const href = link.href;
        const text = link.textContent.trim();
        
        if (href && text && text.length > 20 && (
          href.includes('bidId') ||
          href.includes('notice') ||
          text.includes('采购') ||
          text.includes('招标') ||
          text.includes('公告')
        )) {
          items.push({ text, href });
        }
      });
      
      return items;
    });
    
    console.log(`[CCGP] 找到 ${projects.length} 个项目`);
    
    for (const project of projects.slice(0, 30)) {
      results.push({
        title: project.text,
        region: null,
        budget: null,
        deadline: null,
        description: project.text,
        source_url: project.href,
        source_site: '中国政府采购网',
        category: keyword,
        publish_date: null
      });
    }
    
  } catch (error) {
    console.error(`[CCGP] 错误: ${error.message}`);
  } finally {
    await page.close();
  }
  
  return results;
}

// 主函数
async function main() {
  console.log('=== 开始抓取真实数据 ===');
  console.log('时间:', new Date().toISOString());
  
  const { SQL, db } = await initDB();
  console.log('[DB] 数据库初始化完成');
  
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--window-size=1920,1080'
    ]
  });
  
  const keywords = ['物联网卡', '布控球', '视频监控'];
  let totalInserted = 0;
  
  for (const keyword of keywords) {
    console.log(`\n=== 抓取关键词: ${keyword} ===`);
    
    // 抓取国家电网
    const sgccResults = await scrapeSGCC(keyword, browser);
    for (const project of sgccResults) {
      const changes = insertProject(db, project);
      if (changes > 0) {
        totalInserted++;
        console.log(`[INSERT] ${project.title.substring(0, 50)}...`);
        console.log(`         URL: ${project.source_url}`);
      }
    }
    
    // 抓取政府采购网
    const ccgpResults = await scrapeCCGP(keyword, browser);
    for (const project of ccgpResults) {
      const changes = insertProject(db, project);
      if (changes > 0) {
        totalInserted++;
        console.log(`[INSERT] ${project.title.substring(0, 50)}...`);
        console.log(`         URL: ${project.source_url}`);
      }
    }
  }
  
  await browser.close();
  
  // 查询结果
  const result = db.exec('SELECT COUNT(*) as count FROM bid_notices');
  const count = result[0]?.values[0]?.[0] || 0;
  
  // 保存数据库
  saveDB(SQL, db);
  
  console.log(`\n=== 抓取完成 ===`);
  console.log(`本次插入: ${totalInserted} 条`);
  console.log(`数据库总计: ${count} 条`);
  console.log(`数据库路径: ${DB_PATH}`);
  
  // 显示样本数据
  const sample = db.exec('SELECT id, title, source_url FROM bid_notices ORDER BY id DESC LIMIT 5');
  if (sample[0]) {
    console.log('\n=== 最新数据 ===');
    sample[0].values.forEach(row => {
      console.log(`ID: ${row[0]}, 标题: ${row[1]?.substring(0, 50)}...`);
      console.log(`   URL: ${row[2]}`);
    });
  }
  
  return { totalInserted, totalCount: count };
}

main().catch(console.error);
