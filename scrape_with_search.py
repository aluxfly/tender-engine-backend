#!/usr/bin/env python3
"""
CDP 爬取国家电网电子商务平台 - 搜索特定关键词
"""
import json
import sqlite3
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DB_PATH = '/root/.openclaw/workspace-dev-backend/database.db'

# 关键词定义
IOT_KEYWORDS = ['物联网', 'IoT', 'SIM卡', '流量卡', '通信模块', 'NB-IoT', '4G模块', '5G模块', '物联网卡', '物联卡', '通信卡', '数据卡']
CAMERA_KEYWORDS = ['布控球', '监控球', '摄像头', '视频监控', '智能监控', '安防设备', '监控设备', '球机', '布控', '巡检']

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def is_relevant_project(title):
    title_lower = title.lower()
    for kw in IOT_KEYWORDS:
        if kw.lower() in title_lower:
            return '物联网卡'
    for kw in CAMERA_KEYWORDS:
        if kw.lower() in title_lower:
            return '布控球'
    return None

def extract_date(text):
    if not text:
        return ''
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{4}/\d{2}/\d{2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).replace('/', '-')
    return ''

def search_and_scrape(page, keyword, list_type='bid'):
    """搜索并爬取特定关键词的项目"""
    projects = []
    
    # 构建搜索URL - 国家电网 ECP 搜索
    # 尝试不同的搜索方式
    search_urls = [
        f'https://sgccetp.com.cn/portal/#/search?keyword={keyword}',
        f'https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032700291334/old/1?keyword={keyword}',
    ]
    
    for search_url in search_urls:
        print(f"\n📍 搜索关键词: {keyword}")
        print(f"   URL: {search_url}")
        
        try:
            page.goto(search_url, wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(10000)
            
            # 获取所有链接
            links = page.query_selector_all('a[href*="/doc/"]')
            print(f"   找到 {len(links)} 个链接")
            
            for link in links[:50]:
                try:
                    href = link.get_attribute('href') or ''
                    text = (link.inner_text() or '').strip()
                    
                    if len(text) < 10:
                        continue
                    
                    category = is_relevant_project(text)
                    if not category:
                        continue
                    
                    full_url = f"https://sgccetp.com.cn/portal/{href}" if href.startswith('#') else href
                    
                    parent_text = link.evaluate('el => el.parentElement?.innerText || ""')
                    publish_date = extract_date(parent_text) or extract_date(text) or datetime.now().strftime('%Y-%m-%d')
                    
                    # 提取地区
                    region = ''
                    match = re.search(r'国网(.+?省|.+?市)', text)
                    if match:
                        region = match.group(1)
                    
                    project = {
                        'title': text,
                        'region': region,
                        'budget': 0,
                        'deadline': '',
                        'description': f'{text} - 来自国家电网电子商务平台',
                        'source_url': full_url,
                        'source_site': '国家电网电子商务平台',
                        'category': category,
                        'publish_date': publish_date
                    }
                    
                    if not any(p['title'] == text for p in projects):
                        projects.append(project)
                        print(f"   ✅ [{category}] {text[:60]}...")
                
                except Exception as e:
                    continue
            
            if projects:
                break
                
        except Exception as e:
            print(f"   ❌ 搜索失败: {e}")
            continue
    
    return projects

def scrape_all_list_pages(page):
    """爬取所有列表页，筛选相关项目"""
    projects = []
    
    print("\n" + "="*60)
    print("🔍 爬取所有列表页")
    print("="*60)
    
    # 多个列表页
    LIST_PAGES = [
        {'name': '招标公告', 'url': 'https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032700291334/old/1'},
        {'name': '采购公告', 'url': 'https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032900295987/old/1'},
        {'name': '中标结果', 'url': 'https://sgccetp.com.cn/portal/#/list/list-com/2018032600289606_1_2018060501171111/old/1'},
        {'name': '推荐候选人', 'url': 'https://sgccetp.com.cn/portal/#/list/list-com/2018032600289606_1_2018060501171107/old/1'},
    ]
    
    for list_info in LIST_PAGES:
        print(f"\n📍 {list_info['name']}")
        
        try:
            page.goto(list_info['url'], wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(12000)
            
            links = page.query_selector_all('a[href*="/doc/"]')
            print(f"   找到 {len(links)} 个链接")
            
            for link in links:
                try:
                    href = link.get_attribute('href') or ''
                    text = (link.inner_text() or '').strip()
                    
                    if len(text) < 10:
                        continue
                    
                    category = is_relevant_project(text)
                    if not category:
                        continue
                    
                    full_url = f"https://sgccetp.com.cn/portal/{href}" if href.startswith('#') else href
                    
                    parent_text = link.evaluate('el => el.parentElement?.innerText || ""')
                    publish_date = extract_date(parent_text) or extract_date(text) or datetime.now().strftime('%Y-%m-%d')
                    
                    region = ''
                    match = re.search(r'国网(.+?省|.+?市)', text)
                    if match:
                        region = match.group(1)
                    
                    project = {
                        'title': text,
                        'region': region,
                        'budget': 0,
                        'deadline': '',
                        'description': f'{text} - 来自国家电网电子商务平台',
                        'source_url': full_url,
                        'source_site': '国家电网电子商务平台',
                        'category': category,
                        'publish_date': publish_date
                    }
                    
                    if not any(p['title'] == text for p in projects):
                        projects.append(project)
                        print(f"   ✅ [{category}] {text[:60]}...")
                
                except Exception as e:
                    continue
            
            time.sleep(2)
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            continue
    
    return projects

def scrape_detail_pages(page, projects):
    """爬取详情页获取更多信息"""
    print(f"\n🔍 爬取 {len(projects)} 个项目详情页...")
    
    for i, project in enumerate(projects[:10]):  # 最多爬10个详情页
        try:
            print(f"   [{i+1}/{min(len(projects), 10)}] {project['title'][:40]}...")
            page.goto(project['source_url'], wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(5000)
            
            # 尝试获取预算信息
            budget_selectors = ['.budget', '.price', '.amount', 'table td']
            for selector in budget_selectors:
                try:
                    elements = page.query_selector_all(selector)
                    for el in elements:
                        text = el.inner_text()
                        if '万' in text or '元' in text or '预算' in text:
                            # 提取数字
                            match = re.search(r'(\d+\.?\d*)\s*万', text)
                            if match:
                                project['budget'] = int(float(match.group(1)) * 10000)
                                break
                except:
                    continue
            
            time.sleep(1)
            
        except Exception as e:
            print(f"      详情页爬取失败: {e}")
            continue
    
    return projects

def save_projects(projects):
    if not projects:
        print("⚠️ 没有项目需要保存")
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    
    crawl_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    saved_count = 0
    
    for p in projects:
        try:
            c.execute('SELECT id FROM bid_notices WHERE title = ?', (p['title'],))
            if c.fetchone():
                continue
            
            content_hash = f"hash_{p['category']}_{hash(p['title']) % 1000000}"
            c.execute('''
                INSERT INTO bid_notices 
                (title, region, budget, deadline, description, source_url, source_site, category, publish_date, crawl_time, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                p['title'], p['region'], p['budget'], p['deadline'],
                p['description'], p['source_url'], p['source_site'],
                p['category'], p['publish_date'], crawl_time, content_hash
            ))
            saved_count += 1
        except Exception as e:
            continue
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 新增 {saved_count} 条项目数据")

def verify_database():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM bid_notices')
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bid_notices WHERE category = '物联网卡'")
    iot_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bid_notices WHERE category = '布控球'")
    camera_count = c.fetchone()[0]
    
    print(f"\n📊 数据库统计:")
    print(f"   - 总计: {total} 条")
    print(f"   - 物联网卡: {iot_count} 条")
    print(f"   - 布控球: {camera_count} 条")
    
    print("\n📋 最新5条项目:")
    c.execute('SELECT title, category, source_url FROM bid_notices ORDER BY id DESC LIMIT 5')
    for row in c.fetchall():
        print(f"   [{row['category']}] {row['title'][:60]}...")
        print(f"      URL: {row['source_url'][:80]}")
    
    conn.close()

def main():
    print("="*60)
    print("🚀 CDP 爬取国家电网真实数据")
    print("="*60)
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        print("✅ CDP 连接成功")
        
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = context.new_page()
        else:
            context = browser.new_context()
            page = context.new_page()
        
        page.set_viewport_size({'width': 1920, 'height': 1080})
        
        all_projects = []
        
        # 1. 爬取所有列表页
        projects = scrape_all_list_pages(page)
        all_projects.extend(projects)
        
        # 2. 搜索特定关键词
        search_keywords = ['物联网卡', '布控球', '视频监控', 'SIM卡', '物联网', '监控设备']
        for keyword in search_keywords:
            projects = search_and_scrape(page, keyword)
            all_projects.extend(projects)
            time.sleep(2)
        
        # 3. 爬取详情页获取更多信息
        if all_projects:
            all_projects = scrape_detail_pages(page, all_projects)
        
        # 4. 保存
        if all_projects:
            save_projects(all_projects)
        else:
            print("\n⚠️ 未找到相关项目")
    
    verify_database()
    print("\n✅ 完成")

if __name__ == '__main__':
    main()
