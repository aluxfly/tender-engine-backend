#!/usr/bin/env python3
"""
国家电网电子商务平台（ecp.sgcc.com.cn）招标公告爬虫

功能：
1. 使用 Playwright 连接 CDP 浏览器（端口 9222）
2. 自动翻页抓取招标公告数据
3. 支持指定页数范围
4. 增量更新（避免重复抓取）
5. 保存到 JSON 文件

数据字段：
- 项目名称
- 项目编号
- 项目状态（正在招标/已经截止）
- 创建时间
- 详情链接

使用方法：
    python scripts/crawl_ecp_sgcc.py --max-pages 10
    python scripts/crawl_ecp_sgcc.py --start-page 1 --end-page 100
    python scripts/crawl_ecp_sgcc.py --incremental
"""
import json
import re
import argparse
import os
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# 配置
CDP_PORT = 9222
BASE_URL = "https://ecp.sgcc.com.cn"
PORTAL_URL = f"{BASE_URL}/ecp2.0/portal/#/"
BID_ANNOUNCEMENT_URL = f"{BASE_URL}/ecp2.0/portal/#/bid-public-announcement"

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_existing_data(output_file: str) -> dict:
    """加载已有数据（用于增量更新）"""
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载已有数据失败: {e}")
    return {"projects": [], "crawl_info": {}}


def save_data(data: dict, output_file: str):
    """保存数据到 JSON 文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 数据已保存到: {output_file}")


def extract_project_id_from_url(url: str) -> str:
    """从 URL 提取项目 ID"""
    # 尝试匹配各种格式的项目 ID
    patterns = [
        r'docID=([^&]+)',
        r'/doc/([^/]+)',
        r'projectId=([^&]+)',
        r'id=([^&]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def parse_table_row(row_element, page) -> dict:
    """解析表格行数据"""
    try:
        # 获取所有单元格
        cells = row_element.query_selector_all('td')
        if not cells or len(cells) < 2:
            return None
        
        project = {}
        
        # 尝试从单元格提取数据
        for i, cell in enumerate(cells):
            text = (cell.inner_text() or '').strip()
            
            # 检查是否有链接
            link_el = cell.query_selector('a')
            if link_el:
                href = link_el.get_attribute('href') or ''
                text = link_el.inner_text().strip()
                
                # 构建完整 URL
                if href and href != '#':
                    if href.startswith('http'):
                        project['detail_url'] = href
                    elif href.startswith('#'):
                        project['detail_url'] = f"{BASE_URL}/ecp2.0/portal/{href}"
                    else:
                        project['detail_url'] = f"{BASE_URL}{href}"
        
        # 尝试从行文本提取信息
        row_text = row_element.inner_text()
        
        # 提取项目编号（通常是字母数字组合）
        id_patterns = [
            r'([A-Z0-9]{10,30})',  # 标准项目编号
            r'项目编号[：:]\s*([^\s]+)',
            r'编号[：:]\s*([^\s]+)',
        ]
        for pattern in id_patterns:
            match = re.search(pattern, row_text)
            if match:
                project['project_id'] = match.group(1)
                break
        
        # 提取日期
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{4}/\d{2}/\d{2})',
            r'(\d{4}\.\d{2}\.\d{2})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, row_text)
            if match:
                date_str = match.group(1)
                # 统一格式为 YYYY-MM-DD
                date_str = date_str.replace('/', '-').replace('.', '-')
                project['create_time'] = date_str
                break
        
        # 提取状态
        if '正在招标' in row_text or '招标中' in row_text or '投标中' in row_text:
            project['status'] = '正在招标'
        elif '已截止' in row_text or '截止' in row_text or '结束' in row_text:
            project['status'] = '已经截止'
        else:
            project['status'] = '未知'
        
        # 提取项目名称（通常是最长的文本）
        texts = [t.strip() for t in row_text.split('\n') if len(t.strip()) > 5]
        if texts:
            # 找最长的作为项目名称
            project['project_name'] = max(texts, key=len)
        
        return project if project.get('project_name') else None
        
    except Exception as e:
        print(f"⚠️ 解析行数据失败: {e}")
        return None


def crawl_single_page(page, page_num: int) -> list:
    """爬取单页数据"""
    print(f"📄 正在爬取第 {page_num} 页...")
    
    projects = []
    
    # 等待表格加载
    try:
        # 尝试多种选择器
        table_selectors = [
            'table tbody tr',
            '.el-table__body tr',
            '.data-table tr',
            'table tr',
            '.list-item',
            '.bid-item',
            '.project-item',
        ]
        
        rows = []
        for selector in table_selectors:
            try:
                page.wait_for_selector(selector, timeout=5000)
                rows = page.query_selector_all(selector)
                if rows:
                    print(f"  找到 {len(rows)} 行数据 (选择器: {selector})")
                    break
            except:
                continue
        
        if not rows:
            print(f"⚠️ 第 {page_num} 页未找到数据行")
            return []
        
        # 解析每一行
        for row in rows:
            project = parse_table_row(row, page)
            if project:
                projects.append(project)
        
        print(f"  ✅ 第 {page_num} 页获取 {len(projects)} 条数据")
        
    except PlaywrightTimeoutError:
        print(f"⚠️ 第 {page_num} 页等待超时")
    except Exception as e:
        print(f"⚠️ 第 {page_num} 页爬取失败: {e}")
    
    return projects


def go_to_next_page(page) -> bool:
    """翻到下一页"""
    try:
        # 尝试多种翻页按钮选择器
        next_button_selectors = [
            'button:has-text("下一页")',
            '.next:not(.disabled)',
            '.el-pagination .btn-next:not(.disabled)',
            'a.next:not(.disabled)',
            '[aria-label="Next"]:not(.disabled)',
            '.pagination .next:not(.disabled)',
        ]
        
        for selector in next_button_selectors:
            try:
                next_btn = page.query_selector(selector)
                if next_btn:
                    # 检查是否禁用
                    is_disabled = next_btn.is_disabled()
                    class_name = next_btn.get_attribute('class') or ''
                    
                    if not is_disabled and 'disabled' not in class_name:
                        next_btn.click()
                        page.wait_for_timeout(3000)  # 等待加载
                        return True
            except:
                continue
        
        print("⚠️ 未找到可用的下一页按钮")
        return False
        
    except Exception as e:
        print(f"⚠️ 翻页失败: {e}")
        return False


def navigate_to_bid_page(page):
    """导航到招标公告页面"""
    print(f"🌐 访问首页: {PORTAL_URL}")
    
    try:
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        
        # 尝试点击"招标采购"菜单
        menu_selectors = [
            'text=招标采购',
            'a:has-text("招标采购")',
            '[title="招标采购"]',
            '.menu-item:has-text("招标采购")',
        ]
        
        for selector in menu_selectors:
            try:
                menu = page.query_selector(selector)
                if menu:
                    menu.click()
                    page.wait_for_timeout(2000)
                    break
            except:
                continue
        
        # 尝试点击"招标公告及投标邀请书"
        submenu_selectors = [
            'text=招标公告及投标邀请书',
            'a:has-text("招标公告")',
            '[title="招标公告及投标邀请书"]',
            'text=招标公告',
        ]
        
        for selector in submenu_selectors:
            try:
                submenu = page.query_selector(selector)
                if submenu:
                    submenu.click()
                    page.wait_for_timeout(5000)
                    break
            except:
                continue
        
        # 直接访问招标公告页面
        print(f"🌐 直接访问招标公告页: {BID_ANNOUNCEMENT_URL}")
        page.goto(BID_ANNOUNCEMENT_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(8000)
        
        # 截图调试
        screenshot_path = OUTPUT_DIR / f"debug_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(screenshot_path))
        print(f"📸 截图已保存: {screenshot_path}")
        
        return True
        
    except Exception as e:
        print(f"⚠️ 导航失败: {e}")
        return False


def crawl_ecp_sgcc(
    max_pages: int = 10,
    start_page: int = 1,
    end_page: int = None,
    output_file: str = None,
    incremental: bool = False,
    cdp_port: int = CDP_PORT
):
    """
    主爬虫函数
    
    Args:
        max_pages: 最大爬取页数
        start_page: 起始页码
        end_page: 结束页码
        output_file: 输出文件路径
        incremental: 是否增量更新
        cdp_port: CDP 端口
    """
    if output_file is None:
        output_file = str(OUTPUT_DIR / "ecp_projects.json")
    
    # 加载已有数据
    existing_data = load_existing_data(output_file) if incremental else {"projects": [], "crawl_info": {}}
    existing_ids = {p.get('project_id') or p.get('detail_url') for p in existing_data.get('projects', [])}
    
    all_projects = existing_data.get('projects', [])
    new_count = 0
    
    print("=" * 60)
    print("🚀 国家电网电子商务平台招标公告爬虫")
    print("=" * 60)
    print(f"📡 CDP 端口: {cdp_port}")
    print(f"📄 爬取范围: 第 {start_page} 页" + (f" 到 第 {end_page} 页" if end_page else f" 起，最多 {max_pages} 页"))
    print(f"📁 输出文件: {output_file}")
    print(f"🔄 增量模式: {'是' if incremental else '否'}")
    print("=" * 60)
    
    with sync_playwright() as p:
        try:
            # 连接 CDP 浏览器
            print(f"🔌 连接 CDP 浏览器 (端口 {cdp_port})...")
            browser = p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
            
            # 获取或创建页面
            contexts = browser.contexts
            if contexts and contexts[0].pages:
                page = contexts[0].pages[0]
            else:
                context = contexts[0] if contexts else browser.new_context()
                page = context.new_page()
            
            # 设置视口
            page.set_viewport_size({"width": 1920, "height": 1080})
            
            # 导航到招标公告页
            if not navigate_to_bid_page(page):
                print("❌ 导航失败，尝试直接访问...")
            
            # 计算爬取页数
            if end_page:
                pages_to_crawl = end_page - start_page + 1
            else:
                pages_to_crawl = max_pages
            
            # 如果不是第一页，先翻到起始页
            if start_page > 1:
                print(f"📄 翻到第 {start_page} 页...")
                for _ in range(start_page - 1):
                    if not go_to_next_page(page):
                        print("⚠️ 无法翻到起始页")
                        break
            
            # 爬取每一页
            for i in range(pages_to_crawl):
                current_page = start_page + i
                
                # 爬取当前页
                projects = crawl_single_page(page, current_page)
                
                # 过滤已存在的项目
                for project in projects:
                    project_id = project.get('project_id') or project.get('detail_url')
                    if project_id and project_id not in existing_ids:
                        all_projects.append(project)
                        existing_ids.add(project_id)
                        new_count += 1
                
                # 尝试翻页
                if i < pages_to_crawl - 1:  # 不是最后一页
                    if not go_to_next_page(page):
                        print("⚠️ 无法继续翻页，停止爬取")
                        break
            
            browser.close()
            
        except Exception as e:
            print(f"❌ 爬虫执行失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 保存数据
    crawl_info = {
        "crawl_time": datetime.now().isoformat(),
        "total_projects": len(all_projects),
        "new_projects": new_count,
        "pages_crawled": pages_to_crawl if 'pages_to_crawl' in dir() else 0,
        "source": BASE_URL,
    }
    
    output_data = {
        "crawl_info": crawl_info,
        "projects": all_projects,
    }
    
    save_data(output_data, output_file)
    
    print("=" * 60)
    print(f"✅ 爬取完成！")
    print(f"   总项目数: {len(all_projects)}")
    print(f"   新增项目: {new_count}")
    print(f"   输出文件: {output_file}")
    print("=" * 60)
    
    return output_data


def main():
    parser = argparse.ArgumentParser(description='国家电网电子商务平台招标公告爬虫')
    parser.add_argument('--max-pages', type=int, default=10, help='最大爬取页数')
    parser.add_argument('--start-page', type=int, default=1, help='起始页码')
    parser.add_argument('--end-page', type=int, default=None, help='结束页码')
    parser.add_argument('--output', type=str, default=None, help='输出文件路径')
    parser.add_argument('--incremental', action='store_true', help='增量更新模式')
    parser.add_argument('--cdp-port', type=int, default=CDP_PORT, help='CDP 端口')
    
    args = parser.parse_args()
    
    crawl_ecp_sgcc(
        max_pages=args.max_pages,
        start_page=args.start_page,
        end_page=args.end_page,
        output_file=args.output,
        incremental=args.incremental,
        cdp_port=args.cdp_port
    )


if __name__ == '__main__':
    main()
