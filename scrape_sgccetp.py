#!/usr/bin/env python3
"""
CDP 爬取国家电网电子商务平台 (sgccetp.com.cn) 真实招标数据
使用 sgccetp.com.cn 域名（技能文档中验证可用的域名）
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
    
    patterns = [
        r'(\d+\.?\d*)\s*万元',
        r'(\d+\.?\d*)\s*万',
        r'预算[：:]\s*(\d+\.?\d*)',
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
            date_str = date_str.replace('/', '-').replace('年', '-').replace('月', '-').replace('日', '')
            return date_str
    
    return ''

def scrape_sgccetp(page):
    """
    爬取国家电网电子商务平台 (sgccetp.com.cn)
    这是技能文档中验证可用的域名
    """
    projects = []
    
    print("\n" + "="*60)
    print("🔍 开始爬取国家电网电子商务平台 (sgccetp.com.cn)")
    print("="*60)
    
    # 国家电网 ECP 平台列表页（来自技能文档）
    LIST_PAGES = [
        {
            'name': '招标公告',
            'url': 'https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032700291334/old/1',
            'type': 'bid'
        },
        {
            'name': '采购公告', 
            'url': 'https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032900295987/old/1',
            'type': 'procurement'
        },
        {
            'name': '中标结果公告',
            'url': 'https://sgccetp.com.cn/portal/#/list/list-com/2018032600289606_1_2018060501171111/old/1',
            'type': 'win'
        },
    ]
    
    BASE_URL = 'https://sgccetp.com.cn'
    
    for list_info in LIST_PAGES:
        print(f"\n📍 访问: {list_info['name']}")
        print(f"   URL: {list_info['url']}")
        
        try:
            page.goto(list_info['url'], wait_until='networkidle', timeout=90000)
            print("   ⏳ 等待动态内容加载...")
            page.wait_for_timeout(15000)  # SPA 需要更长等待时间
            
            # 使用技能文档中的选择器
            # 格式：a[href*="/doc/"] - 匹配所有包含 /doc/ 的链接
            links = page.query_selector_all('a[href*="/doc/"]')
            
            if not links:
                # 尝试其他选择器
                links = page.query_selector_all('a[href*="doc"]')
            
            if not links:
                # 尝试表格链接
                links = page.query_selector_all('table a')
            
            print(f"   找到 {len(links)} 个链接")
            
            if not links:
                print("   ⚠️ 未找到项目链接")
                # 截图调试
                screenshot_path = f'/tmp/sgccetp_{list_info["type"]}.png'
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"   📸 截图已保存: {screenshot_path}")
                
                # 获取页面内容分析
                content = page.content()
                print(f"   页面内容长度: {len(content)} 字符")
                
                # 尝试获取所有链接
                all_links = page.query_selector_all('a')
                print(f"   页面所有链接数: {len(all_links)}")
                
                # 打印前几个链接的 href
                for i, link in enumerate(all_links[:10]):
                    try:
                        href = link.get_attribute('href') or ''
                        text = link.inner_text().strip()[:50]
                        if href or text:
                            print(f"      链接{i}: href={href[:60]}... text={text}")
                    except:
                        pass
                continue
            
            # 提取项目信息
            for i, link in enumerate(links[:100]):  # 最多100条
                try:
                    href = link.get_attribute('href') or ''
                    text = (link.inner_text() or '').strip()
                    
                    if len(text) < 10:  # 跳过太短的标题
                        continue
                    
                    # 检查是否相关
                    category = is_relevant_project(text)
                    if not category:
                        continue
                    
                    # 构建完整 URL
                    if href.startswith('#'):
                        full_url = f"{BASE_URL}/portal/{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{BASE_URL}/portal/#{href}"
                    
                    # 使用 JavaScript 获取父元素中的日期信息
                    js_code = '''el => {
                        let parent = el.parentElement;
                        while (parent && parent.tagName !== "LI" && parent.tagName !== "DIV" && parent.tagName !== "UL" && parent.tagName !== "TR") {
                            parent = parent.parentElement;
                        }
                        return parent ? parent.innerText : "";
                    }'''
                    parent_text = link.evaluate(js_code)
                    
                    # 提取日期
                    publish_date = extract_date(parent_text) or extract_date(text)
                    if not publish_date:
                        publish_date = datetime.now().strftime('%Y-%m-%d')
                    
                    # 提取预算
                    budget = extract_budget(parent_text) or extract_budget(text)
                    
                    # 提取地区
                    region = ''
                    region_patterns = [
                        r'国网(.+?省)',
                        r'国网(.+?市)',
                        r'(.+?省)电力',
                        r'(.+?市)电力',
                    ]
                    for pattern in region_patterns:
                        match = re.search(pattern, text)
                        if match:
                            region = match.group(1).strip()
                            break
                    
                    project = {
                        'title': text,
                        'region': region,
                        'budget': budget,
                        'deadline': '',
                        'description': f'{text} - 来自国家电网电子商务平台',
                        'source_url': full_url,
                        'source_site': '国家电网电子商务平台',
                        'category': category,
                        'publish_date': publish_date
                    }
                    
                    # 避免重复
                    if not any(p['title'] == text for p in projects):
                        projects.append(project)
                        print(f"   ✅ [{category}] {text[:60]}...")
                    
                except Exception as e:
                    print(f"   ⚠️ 解析链接失败: {e}")
                    continue
            
            # 延迟
            time.sleep(2)
            
        except PlaywrightTimeoutError:
            print(f"   ❌ 页面加载超时")
            # 截图
            try:
                screenshot_path = f'/tmp/sgccetp_{list_info["type"]}_timeout.png'
                page.screenshot(path=screenshot_path)
                print(f"   📸 超时截图: {screenshot_path}")
            except:
                pass
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
            page.wait_for_timeout(10000)
            
            # 尝试多种选择器
            selectors = [
                '.list-item a',
                '.result-item a',
                'table a[href*="ccgp"]',
                '.notice-title',
                'a[href*="notice"]',
                'ul li a',
            ]
            
            links = []
            for selector in selectors:
                try:
                    found = page.query_selector_all(selector)
                    if found and len(found) > 3:
                        links = found
                        print(f"   ✅ 找到 {len(found)} 个链接 (选择器: {selector})")
                        break
                except:
                    continue
            
            if not links:
                print("   ⚠️ 未找到项目链接")
                # 截图调试
                screenshot_path = f'/tmp/ccgp_{keyword}.png'
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"   📸 截图已保存: {screenshot_path}")
                
                # 获取所有链接
                all_links = page.query_selector_all('a')
                print(f"   页面所有链接数: {len(all_links)}")
                continue
            
            # 提取项目信息
            for i, link in enumerate(links[:50]):  # 每个关键词最多50条
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
                    elif href.startswith('/'):
                        full_url = f"http://www.ccgp.gov.cn{href}"
                    else:
                        full_url = f"http://www.ccgp.gov.cn/{href}"
                    
                    # 获取父元素文本
                    parent_text = ''
                    try:
                        parent_text = link.evaluate('el => el.parentElement?.innerText || ""')
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
                        r'(.+?省)',
                        r'(.+?市)',
                        r'(.+?自治区)',
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
            time.sleep(3)
            
        except PlaywrightTimeoutError:
            print(f"   ❌ 页面加载超时")
            continue
        except Exception as e:
            print(f"   ❌ 爬取失败: {e}")
            continue
    
    print(f"\n✅ 中国政府采购网爬取完成，获取 {len(projects)} 条相关项目")
    return projects

def save_projects(projects, clear_existing=False):
    """保存项目到数据库"""
    if not projects:
        print("⚠️ 没有项目需要保存")
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    
    if clear_existing:
        c.execute('DELETE FROM bid_notices')
        print("🗑️ 已清空旧数据")
    
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
    c.execute('SELECT id, title, category, source_url, source_site FROM bid_notices ORDER BY id DESC LIMIT 5')
    for row in c.fetchall():
        print(f"   [{row['category']}] {row['title'][:60]}...")
        print(f"      来源: {row['source_site']}")
        print(f"      URL: {row['source_url'][:80]}...")
    
    conn.close()
    return total, iot_count, camera_count

def main():
    print("="*60)
    print("🚀 CDP 真实数据爬取任务 (sgccetp.com.cn)")
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
            
            # 3. 爬取国家电网 (sgccetp.com.cn)
            try:
                sgcc_projects = scrape_sgccetp(page)
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
                save_projects(all_projects, clear_existing=False)
            else:
                print("\n⚠️ 未获取到任何新项目数据")
            
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
