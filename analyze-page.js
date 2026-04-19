// CDP抓取 - 深度分析页面结构
const { chromium } = require('playwright');
const fs = require('fs');

async function main() {
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const context = browser.contexts()[0];
  const page = await context.newPage();
  
  const url = 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/search_list/1776557119421?keyword=%E7%89%A9%E8%81%94%E7%BD%91%E5%8D%A1';
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(10000);
  
  // 保存完整HTML
  const html = await page.content();
  fs.writeFileSync('/tmp/sgcc_search.html', html);
  console.log('HTML保存到 /tmp/sgcc_search.html');
  
  // 分析页面结构
  const analysis = await page.evaluate(() => {
    return {
      title: document.title,
      url: window.location.href,
      iframes: document.querySelectorAll('iframe').length,
      tables: document.querySelectorAll('table').length,
      divs: document.querySelectorAll('div').length,
      links: document.querySelectorAll('a').length,
      // 查找包含招标的文本
      bidText: document.body.innerText.includes('招标'),
      // 查找表格内容
      tableContent: Array.from(document.querySelectorAll('table')).map(t => t.textContent?.substring(0, 200))
    };
  });
  
  console.log('页面分析:', JSON.stringify(analysis, null, 2));
  
  // 尝试提取表格数据
  const tableData = await page.evaluate(() => {
    const results = [];
    
    // 方法1: 查找所有表格行
    document.querySelectorAll('tr').forEach(tr => {
      const text = tr.textContent?.trim();
      if (text && text.length > 20) {
        const link = tr.querySelector('a');
        results.push({
          text: text.substring(0, 100),
          href: link?.href || null
        });
      }
    });
    
    // 方法2: 查找el-table
    document.querySelectorAll('.el-table__row').forEach(row => {
      const text = row.textContent?.trim();
      if (text && text.length > 20) {
        const link = row.querySelector('a');
        results.push({
          text: text.substring(0, 100),
          href: link?.href || null
        });
      }
    });
    
    return results;
  });
  
  console.log('\n表格数据:');
  tableData.forEach((d, i) => {
    console.log(`${i+1}. ${d.text}`);
    if (d.href) console.log(`   URL: ${d.href}`);
  });
  
  // 截图
  await page.screenshot({ path: '/tmp/sgcc_search_final.png', fullPage: true });
  console.log('\n截图保存到 /tmp/sgcc_search_final.png');
}

main().catch(console.error);
