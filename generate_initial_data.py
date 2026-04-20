#!/usr/bin/env python3
"""
从 update_real_data.py 的数据生成 initial_data.json
"""
import json
import re

# 真实数据（从 update_real_data.py 提取）
raw_data = [
    {"title": "【国网(嘉兴)综合能源服务有限公司】国网（嘉兴）综合能源服务有限公司2026-2027年涉网试验辅助服务项目", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026042058389896_2018032700291334_2026042058390591/old", "date": "2026-04-20", "status": "正在招标", "project_id": "ZHNYJX20260401"},
    {"title": "【淮南力达电气安装有限公司】国网安徽电力淮南供电公司2026年原集体企业第十次服务授权公开招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026042057508180_2018032700291334_2026042057783706/old", "date": "2026-04-20", "status": "正在招标", "project_id": "CY1226SHN010"},
    {"title": "【华东送变电工程有限公司】国网上海电力华东送变电公司2026年第二次服务授权招标采购变更公告1", "link": "https://sgccetp.com.cn/portal/#/doc/doci-change/2026042057355551_2018032700291334_2026042057362225/old", "date": "2026-04-20", "status": "正在招标", "project_id": "CY0926SHSFZ2"},
    {"title": "【国网安徽省电力有限公司】国网安徽电力2026年原集体企业第四次物资公开招标采购（二）", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041853573694_2018032700291334_2026041853575432/old", "date": "2026-04-18", "status": "正在招标", "project_id": "CY1226J008"},
    {"title": "【国网安徽省电力有限公司】国网安徽电力2026年原集体企业第四次物资公开招标采购（一）", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041852753165_2018032700291334_2026041853544979/old", "date": "2026-04-18", "status": "正在招标", "project_id": "CY1226J007"},
    {"title": "【安徽送变电工程有限公司】国网安徽电力送变电公司2026年原集体企业第六次服务授权公开招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041853456835_2018032700291334_2026041853462147/old", "date": "2026-04-18", "status": "正在招标", "project_id": "CY1226SBD019"},
    {"title": "【国网安徽省电力有限公司】国网安徽电力2026年原集体企业第三次物资公开招标采购（二）变更公告1", "link": "https://sgccetp.com.cn/portal/#/doc/doci-change/2026041852592734_2018032700291334_2026041852603585/old", "date": "2026-04-18", "status": "已经截止", "project_id": "CY1226J006"},
    {"title": "【国网湖北省电力有限公司】国网湖北省电力有限公司2026年子公司战新产业原集体企业物资类第一次公开招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041749162908_2018032700291334_2026041749165563/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1526J101"},
    {"title": "【国网江苏省电力有限公司】国网江苏电力2026年原集体企业第三次物资公开招标采购-1", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748798739_2018032700291334_2026041748811843/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1026J003-1"},
    {"title": "【国网江苏省电力有限公司】国网江苏电力2026年原集体企业第三次物资框架协议公开招标采购-1", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748801072_2018032700291334_2026041748811695/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1026JB03-1"},
    {"title": "【国网江苏省电力有限公司】国网江苏电力2026年原集体企业第三次物资公开招标采购-2", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748657744_2018032700291334_2026041748663138/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1026J003-2"},
    {"title": "【国网江苏省电力有限公司】国网江苏电力2026年原集体企业第三次物资框架协议公开招标采购-2", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748658785_2018032700291334_2026041748661625/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1026JB03-2"},
    {"title": "【国网江苏省电力有限公司】国网江苏电力2026年原集体企业第三次物资框架协议公开招标采购-3", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748648878_2018032700291334_2026041748649763/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1026JB03-3"},
    {"title": "【国网江苏省电力有限公司】国网江苏电力2026年原集体企业第三次物资公开招标采购-3", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748640338_2018032700291334_2026041748645034/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1026J003-3"},
    {"title": "【中铁隧道局集团有限公司大盾构工程分公司】福莆宁城际铁路F2F3线长乐机场段工程JCZQ-1标盾构机施工用电架设工程", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748574463_2018032700291334_2026041748578256/old", "date": "2026-04-17", "status": "正在招标", "project_id": "FJYLDLZB-2026004"},
    {"title": "【中交第二航务工程局有限公司】福莆宁城际铁路F2F3线长乐机场段工程JCZQ-2标盾构机施工用电架设工程", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748570008_2018032700291334_2026041748570809/old", "date": "2026-04-17", "status": "正在招标", "project_id": "FJYLDLZB-2026003"},
    {"title": "【国网电力空间技术有限公司】国家电网有限公司2026年第二次直属单位联合采购物资招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748541766_2018032700291334_2026041748543748/old", "date": "2026-04-17", "status": "正在招标", "project_id": "7226LH02-WZ"},
    {"title": "【国网电力空间技术有限公司】国家电网有限公司2026年第二次直属单位联合采购服务招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748541766_2018032700291334_2026041748543748/old", "date": "2026-04-17", "status": "正在招标", "project_id": "7226LH02-FZ"},
    {"title": "【国网电力空间技术有限公司】国家电网有限公司2026年第二次直属单位联合采购服务框架招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748541766_2018032700291334_2026041748543748/old", "date": "2026-04-17", "status": "正在招标", "project_id": "7226LH02-FKZ"},
    {"title": "【国网湖南省电力有限公司水电分公司】国网湖南电力水电分公司2026年原集体企业新增第一次服务授权公开招标采购", "link": "https://sgccetp.com.cn/portal/#/doc/doci-bid/2026041748541766_2018032700291334_2026041748543748/old", "date": "2026-04-17", "status": "正在招标", "project_id": "CY1626SSDF02"},
]

def extract_region(title):
    """从标题提取地区"""
    provinces = {
        "安徽": "安徽",
        "湖北": "湖北",
        "江苏": "江苏",
        "湖南": "湖南",
        "上海": "上海",
        "浙江": "浙江",
        "嘉兴": "浙江",
        "淮南": "安徽",
        "华东": "上海",
    }
    
    for keyword, region in provinces.items():
        if keyword in title:
            return region
    
    return ""

def generate_initial_data():
    """生成 initial_data.json 格式的数据"""
    initial_data = []
    
    for item in raw_data:
        data = {
            "title": item['title'],
            "region": extract_region(item['title']),
            "budget": 0,
            "deadline": "",
            "description": item['title'],
            "source_url": item['link'],
            "source_site": "国家电网电子商务平台",
            "category": "电力设备",
            "publish_date": item['date']
        }
        initial_data.append(data)
    
    return initial_data

if __name__ == '__main__':
    data = generate_initial_data()
    
    # 写入 initial_data.json
    with open('initial_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已生成 {len(data)} 条数据到 initial_data.json")
    print(f"   - 2026-04-20: {sum(1 for d in data if d['publish_date'] == '2026-04-20')} 条")
    print(f"   - 2026-04-18: {sum(1 for d in data if d['publish_date'] == '2026-04-18')} 条")
    print(f"   - 2026-04-17: {sum(1 for d in data if d['publish_date'] == '2026-04-17')} 条")
