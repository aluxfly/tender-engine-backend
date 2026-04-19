#!/usr/bin/env python3
"""
调试脚本：查看 sgccetp.com.cn 页面实际内容
"""
import json
from playwright.sync_api import sync_playwright

def debug_sgccetp():
    print("🔍 调试 sgccetp.com.cn 页面内容")
    
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
        
        # 访问招标公告页
        url = 'https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032700291334/old/1'
        print(f"\n📍 访问: {url}")
        
        page.goto(url, wait_until='networkidle', timeout=90000)
        page.wait_for_timeout(15000)
        
        # 获取所有包含 /doc/ 的链接
        links = page.query_selector_all('a[href*="/doc/"]')
        print(f"\n找到 {len(links)} 个 /doc/ 链接")
        
        # 打印前20个链接的内容
        print("\n前20个链接内容:")
        for i, link in enumerate(links[:20]):
            try:
                href = link.get_attribute('href') or ''
                text = (link.inner_text() or '').strip()
                print(f"{i+1}. [{text[:80]}]")
                print(f"   href: {href}")
            except Exception as e:
                print(f"{i+1}. 错误: {e}")
        
        # 截图
        page.screenshot(path='/tmp/sgccetp_debug.png', full_page=True)
        print("\n📸 截图保存: /tmp/sgccetp_debug.png")
        
        # 获取页面标题
        title = page.title()
        print(f"\n页面标题: {title}")
        
        # 检查是否有物联网/布控球相关内容
        page_text = page.content()
        keywords = ['物联网', '布控球', '监控', 'SIM', '卡']
        print("\n关键词统计:")
        for kw in keywords:
            count = page_text.count(kw)
            print(f"  '{kw}': {count} 次")

if __name__ == '__main__':
    debug_sgccetp()
