#!/usr/bin/env python3
"""
CDP 真实数据爬取脚本
从国家电网电子商务平台和中国政府采购网抓取真实招标数据
"""
import json
import sqlite3
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 数据库路径
DB_PATH = '/root/.openclaw/workspace-dev-backend/database.db'

# 关键词定义
IOT_KEYWORDS = ['物联网', 'IoT', 'SIM卡', '流量卡', '通信模块', 'NB-IoT', '4G模块', '5G模块', '物联网卡', '物联卡', '通信卡', '数据卡']
CAMERA_KEYWORDS = ['布控球', '监控球', '摄像头', '视频监控', '智能监控', '安防设备', '监控设备', '球机', '布控', '巡检']

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """初始化数据库表"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bid_notices'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE bid_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                region TEXT,
                budget REAL,
                deadline TEXT,
                description TEXT,
                source_url TEXT,
                source_site TEXT,
                category TEXT,
                publish_date TEXT,
                crawl_time TEXT DEFAULT CURRENT_TIMESTAMP,
                content_hash TEXT
            )
        ''')
        print("✅ bid_notices 表已创建")
    
    conn.commit()
    conn.close()

def is_relevant_project(title):
    """判断项目是否相关（物联网卡或布控球）"""
    title_lower = title.lower()
    
    # 检查物联网卡关键词
    for kw in IOT_KEYWORDS:
        if kw.lower() in title_lower:
            return '物联网卡'
    
    # 检查布控球关键词
    for kw in CAMERA_KEYWORDS:
        if kw.lower() in title_lower:
            return '布控球'
    
    return None

def extract_budget(text):
    """从文本中提取预算金额"""
    if not text:
        return 0
    
    # 匹配 "XX万元" 或 "XX万" 或 "XX元"
    patterns = [
        r'(\d+\.?\d*)\s*万元',
        r'(\d+\.?\d*)\s*万',
        r'预算[：:]\s*(\d+\.?\d*)',
        r'金额[：:]\s*(\d+\.?\d*)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = float(match.group(1))
            if '万' in text:
                return int(value * 10000)
            return int(value)
    
    return 0

def extract_date(text):
    """从文本中提取日期"""
    if not text:
        return ''
    
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{4}/\d{2}/\d{2})',
        r'(\d{4}年\d{1,2}月\d{1,2}日)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            # 统一格式为 YYYY-MM-DD
            date_str = date_str.replace('/', '-').replace('年', '-').replace('月', '-').replace('日', '')
            return date_str
    
    return ''

def scrape_sgcc_ecp(page):
    """
    爬取国家电网电子商务平台
    URL: https://ecp.sgcc.com.cn
    """
    projects = []
    
    print("\n" + "="*60)
    print("🔍 开始爬取国家电网电子商务平台")
    print("="*60)
    
    # 国家电网 ECP 平台招标公告列表页
    list_urls = [
        {
            'name': '招标公告',
            'url': 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/bid-public-announcement',
        },
        {
            'name': '采购公告',
            'url': 'https://ecp.sgcc.com.cn/ecp2.0/portal/#/procurement-announcement',
        }
    ]
    
    for list_info in list_urls:
        print(f"\n📍 访问: {list_info['name']}")
        print(f"   URL: {list_info['url']}")
        
        try:
            page.goto(list_info['url'], wait_until='networkidle', timeout=60000)
            print("   ⏳ 等待页面加载...")
            page.wait_for_timeout(10000)  # 等待动态内容加载
            
            # 尝试多种选择器
            selectors = [
                'a[href*="/doc/"]',
                '.project-item a',
                '.list-item a',
                'table a',
                '.bid-item',
                '.notice-item',
            ]
            
            links = []
            for selector in selectors:
                try:
                    found = page.query_selector_all(selector)
                    if found:
                        links = found
                        print(f"   ✅ 找到 {len(found)} 个链接 (选择器: {selector})")
                        break
                except:
                    continue
            
            if not links:
                print("   ⚠️ 未找到项目链接，尝试获取页面内容...")
                # 获取页面文本内容
                page_text = page.content()
                print(f"   页面长度: {len(page_text)} 字符")
                
                # 尝试截图调试
                screenshot_path = f'/tmp/sgcc_{list_info["name"]}.png'
                page.screenshot(path=screenshot_path)
                print(f"   📸 截图已保存: {screenshot_path}")
                continue
            
            # 提取项目信息
            for i, link in enumerate(links[:50]):  # 最多50条
                try:
                    title = link.inner_text().strip()
                    href = link.get_attribute('href') or ''
                    
                    if len(title) < 10:  # 跳过太短的标题
                        continue
                    
                    # 检查是否相关
                    category = is_relevant_project(title)
                    if not category:
                        continue
                    
                    # 构建完整URL
                    if href.startswith('#'):
                        full_url = f"https://ecp.sgcc.com.cn/ecp2.0/portal/{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://ecp.sgcc.com.cn/ecp2.0/portal/#{href}"
                    
                    # 获取父元素文本（可能包含日期等信息）
                    parent_text = ''
                    try:
                        parent = link.evaluate_handle('el => el.parentElement?.innerText || ""')
                        parent_text = str(parent) if parent else ''
                    except:
                        pass
                    
                    # 提取日期
                    publish_date = extract_date(parent_text) or extract_date(title)
                    if not publish_date:
                        publish_date = datetime.now().strftime('%Y-%m-%d')
                    
                    # 提取预算
                    budget = extract_budget(parent_text) or extract_budget(title)
                    
                    # 提取地区（从标题中）
                    region = ''
                    region_patterns = [
                        r'国网(.+?)电力',
                        r'(.+?)省',
                        r'(.+?)市',
                    ]
                    for pattern in region_patterns:
                        match = re.search(pattern, title)
                        if match:
                            region = match.group(1).strip()
                            if not region.endswith('省') and not region.endswith('市'):
                                region = region + ('省' if len(region) > 2 else '市')
                            break
                    
                    project = {
                        'title': title,
                        'region': region,
                        'budget': budget,
                        'deadline': '',
                        'description': f'{title} - 来自国家电网电子商务平台',
                        'source_url': full_url,
                        'source_site': '国家电网电子商务平台',
                        'category': category,
                        'publish_date': publish_date
                    }
                    
                    projects.append(project)
                    print(f"   ✅ [{category}] {title[:50]}...")
                    
                except Exception as e:
                    print(f"   ⚠️ 解析链接失败: {e}")
                    continue
            
        except PlaywrightTimeoutError:
            print(f"   ❌ 页面加载超时")
            continue
        except Exception as e:
            print(f"   ❌ 爬取失败: {e}")
            continue
    
    print(f"\n✅ 国家电网爬取完成，获取 {len(projects)} 条相关项目")
    return projects

def scrape_ccgp(page):
    """
    爬取中国政府采购网
    URL: http://www.ccgp.gov.cn
    """
    projects = []
    
    print("\n" + "="*60)
    print("🔍 开始爬取中国政府采购网")
    print("="*60)
    
    # 搜索关键词
    search_keywords = ['物联网', '监控设备', '布控球', 'SIM卡']
    
    for keyword in search_keywords:
        print(f"\n📍 搜索关键词: {keyword}")
        
        try:
            # 中国政府采购网搜索URL
            search_url = f"http://search.ccgp.gov.cn/bxsearch?searchtype=1&bidSort=0&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx&kw={keyword}&start_time=&end_time=&page_index=1"
            
            page.goto(search_url, wait_until='networkidle', timeout=60000)
            print("   ⏳ 等待页面加载...")
            page.wait_for_timeout(8000)
            
            # 尝试多种选择器
            selectors = [
                '.list-item a',
                '.result-item a',
                'table a',
                '.notice-title',
                'a[href*="ccgp.gov.cn"]',
            ]
            
            links = []
            for selector in selectors:
                try:
                    found = page.query_selector_all(selector)
                    if found:
                        links = found
                        print(f"   ✅ 找到 {len(found)} 个链接 (选择器: {selector})")
                        break
                except:
                    continue
            
            if not links:
                print("   ⚠️ 未找到项目链接")
                # 截图调试
                screenshot_path = f'/tmp/ccgp_{keyword}.png'
                page.screenshot(path=screenshot_path)
                print(f"   📸 截图已保存: {screenshot_path}")
                continue
            
            # 提取项目信息
            for i, link in enumerate(links[:30]):  # 每个关键词最多30条
                try:
                    title = link.inner_text().strip()
                    href = link.get_attribute('href') or ''
                    
                    if len(title) < 10:
                        continue
                    
                    # 检查是否相关
                    category = is_relevant_project(title)
                    if not category:
                        continue
                    
                    # 构建完整URL
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"http://www.ccgp.gov.cn{href}"
                    
                    # 获取父元素文本
                    parent_text = ''
                    try:
                        parent = link.evaluate_handle('el => el.parentElement?.innerText || ""')
                        parent_text = str(parent) if parent else ''
                    except:
                        pass
                    
                    # 提取日期
                    publish_date = extract_date(parent_text) or extract_date(title)
                    if not publish_date:
                        publish_date = datetime.now().strftime('%Y-%m-%d')
                    
                    # 提取预算
                    budget = extract_budget(parent_text) or extract_budget(title)
                    
                    # 提取地区
                    region = ''
                    region_patterns = [
                        r'(.+?)省',
                        r'(.+?)市',
                        r'(.+?)自治区',
                    ]
                    for pattern in region_patterns:
                        match = re.search(pattern, title)
                        if match:
                            region = match.group(1).strip()
                            break
                    
                    project = {
                        'title': title,
                        'region': region,
                        'budget': budget,
                        'deadline': '',
                        'description': f'{title} - 来自中国政府采购网',
                        'source_url': full_url,
                        'source_site': '中国政府采购网',
                        'category': category,
                        'publish_date': publish_date
                    }
                    
                    # 避免重复
                    if not any(p['title'] == title for p in projects):
                        projects.append(project)
                        print(f"   ✅ [{category}] {title[:50]}...")
                    
                except Exception as e:
                    print(f"   ⚠️ 解析链接失败: {e}")
                    continue
            
            # 延迟，避免被封
            time.sleep(2)
            
        except PlaywrightTimeoutError:
            print(f"   ❌ 页面加载超时")
            continue
        except Exception as e:
            print(f"   ❌ 爬取失败: {e}")
            continue
    
    print(f"\n✅ 中国政府采购网爬取完成，获取 {len(projects)} 条相关项目")
    return projects

def save_projects(projects):
    """保存项目到数据库"""
    if not projects:
        print("⚠️ 没有项目需要保存")
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    
    crawl_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    saved_count = 0
    
    for p in projects:
        try:
            # 检查是否已存在（根据标题）
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
            print(f"⚠️ 保存失败: {e}")
            continue
    
    conn.commit()
    
    # 统计
    c.execute('SELECT COUNT(*) FROM bid_notices')
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bid_notices WHERE category = '物联网卡'")
    iot_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bid_notices WHERE category = '布控球'")
    camera_count = c.fetchone()[0]
    
    conn.close()
    
    print(f"\n✅ 新增 {saved_count} 条项目数据")
    print(f"   数据库统计:")
    print(f"   - 物联网卡项目: {iot_count} 条")
    print(f"   - 布控球项目: {camera_count} 条")
    print(f"   - 总计: {total} 条")

def verify_database():
    """验证数据库内容"""
    print("\n" + "="*60)
    print("🔍 验证数据库内容")
    print("="*60)
    
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
    
    # 显示前5条
    print("\n📋 前5条项目:")
    c.execute('SELECT id, title, category, source_url FROM bid_notices LIMIT 5')
    for row in c.fetchall():
        print(f"   [{row['category']}] {row['title'][:60]}...")
        print(f"      URL: {row['source_url']}")
    
    conn.close()
    return total, iot_count, camera_count

def main():
    print("="*60)
    print("🚀 CDP 真实数据爬取任务")
    print("="*60)
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 初始化数据库
    init_database()
    
    # 2. 连接 CDP 浏览器
    print("\n🔌 连接 Chrome CDP (端口 9222)...")
    
    try:
        with sync_playwright() as p:
            # 连接到真实 Chrome 浏览器
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("✅ CDP 连接成功")
            
            # 获取或创建页面
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
            
            # 设置视口大小
            page.set_viewport_size({'width': 1920, 'height': 1080})
            
            all_projects = []
            
            # 3. 爬取国家电网
            try:
                sgcc_projects = scrape_sgcc_ecp(page)
                all_projects.extend(sgcc_projects)
            except Exception as e:
                print(f"❌ 国家电网爬取失败: {e}")
            
            # 4. 爬取中国政府采购网
            try:
                ccgp_projects = scrape_ccgp(page)
                all_projects.extend(ccgp_projects)
            except Exception as e:
                print(f"❌ 中国政府采购网爬取失败: {e}")
            
            # 5. 保存到数据库
            if all_projects:
                save_projects(all_projects)
            else:
                print("\n⚠️ 未获取到任何项目数据")
            
            # 关闭浏览器连接（不关闭浏览器本身）
            # browser.close()  # 不关闭，保持浏览器运行
    
    except Exception as e:
        print(f"❌ CDP 连接失败: {e}")
        print("   请确保 Chrome 已启动并开启远程调试端口 9222")
        return False
    
    # 6. 验证数据库
    verify_database()
    
    print("\n" + "="*60)
    print("✅ 爬取任务完成")
    print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    return True

if __name__ == '__main__':
    main()
