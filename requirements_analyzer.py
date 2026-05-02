"""
标书 AI 生成系统 — Day 2: 资料需求分析引擎
===========================================
功能:
  1. 扫描三个模板文件的所有占位符
  2. 按类别分组（公司信息/财务/资质/业绩/团队/技术/报价）
  3. 对比已有数据库记录，标记已填充/待补充
  4. 生成结构化需求清单
"""

import json
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ==================== 占位符分类映射 ====================

CATEGORY_MAP = {
    "公司信息": [
        "公司名称", "企业名称", "信用代码", "统一社会信用代码", "注册地址",
        "注册资本", "法定代表人", "成立时间", "营业期限", "经营范围",
        "公司地址", "邮编", "传真", "纳税人", "纳税人识别",
    ],
    "财务": [
        "金额", "报价", "预算", "大写金额", "小写金额", "单价", "合价",
        "总价", "保证金", "大写", "小写", "银行名称", "银行账号",
        "开户银行", "账号", "资信等级", "审计", "财务报表", "资产",
        "利润", "纳税", "完税", "费率", "折扣", "税费",
    ],
    "资质": [
        "资质", "证书", "执照", "许可证", "等级", "ISO", "认证",
        "营业执照", "社保", "守法记录", "信用报告",
    ],
    "业绩": [
        "业绩", "项目经验", "合同金额", "完成时间", "类似项目",
        "中标", "项目状态", "签订时间",
    ],
    "团队": [
        "姓名", "人员", "职称", "学历", "专业", "工作年限",
        "项目经理", "技术负责人", "核心技术人员", "质量管理人员",
        "安全管理人员", "拟任职务", "身份证", "授权", "代表",
        "被授权人", "职务", "简历", "性别", "出生年月",
        "毕业院校", "毕业时间", "执业资格",
        "联系电话", "电话号码", "邮箱", "电子邮箱",
    ],
    "技术": [
        "技术", "方案", "偏差", "参数", "规格", "设备", "材料",
        "质量", "安全", "风险", "进度", "验收", "培训", "服务承诺",
        "条款号", "招标要求", "响应内容", "项目实施", "质量保障",
        "安全保障", "沟通协调", "履约", "售后", "保密",
    ],
    "报价": [
        "投标报价", "报价明细", "分项报价", "报价表",
    ],
    "其他": [],  # 兜底类别
}

# ==================== 数据库填充状态判断 ====================

def get_company_profile(get_db_connection_func) -> Optional[Dict[str, Any]]:
    """获取公司资料。"""
    with get_db_connection_func() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, company_name, credit_code, legal_representative,
                   contact_person, phone, email, address, bank_info, qualifications
            FROM company_profiles
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        cursor.close()

    if not row:
        return None

    return {
        "id": row[0],
        "company_name": row[1],
        "credit_code": row[2],
        "legal_representative": row[3],
        "contact_person": row[4],
        "phone": row[5],
        "email": row[6],
        "address": row[7],
        "bank_info": json.loads(row[8]) if row[8] and isinstance(row[8], str) else (row[8] or {}),
        "qualifications": json.loads(row[9]) if row[9] and isinstance(row[9], str) else (row[9] or []),
    }


def get_project_performance(project_id: int, get_db_connection_func) -> List[Dict[str, Any]]:
    """获取类似项目业绩（从 bid_projects 历史数据）。"""
    with get_db_connection_func() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, parsed_data, status, created_at
            FROM bid_projects
            WHERE id != %s AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        cursor.close()

    results = []
    for row in rows:
        parsed = json.loads(row[2]) if row[2] and isinstance(row[2], str) else (row[2] or {})
        results.append({
            "id": row[0],
            "title": row[1],
            "parsed_data": parsed,
            "status": row[3],
            "created_at": str(row[4]),
        })

    return results


def classify_placeholder(name: str) -> str:
    """将占位符归类。"""
    # 去除占位符的方括号
    clean_name = name.strip().strip("[]")

    for category, keywords in CATEGORY_MAP.items():
        if category == "其他":
            continue
        for keyword in keywords:
            if keyword in clean_name:
                return category

    # 如果没匹配到，检查占位符名称的简短程度
    if len(clean_name) <= 4:
        return "其他"

    return "其他"


def check_placeholder_filled(placeholder_name: str, company_profile: Optional[Dict],
                             project_data: Optional[Dict]) -> Dict[str, Any]:
    """
    检查单个占位符是否可以从已有数据中填充。

    返回:
    {
        "name": "...",
        "category": "...",
        "fill_status": "filled/partial/unfilled",
        "fill_source": "...",
        "suggested_value": "...",
        "is_urgent": True/False,
    }
    """
    clean_name = placeholder_name.strip().strip("[]")
    category = classify_placeholder(clean_name)
    result = {
        "name": placeholder_name,
        "clean_name": clean_name,
        "category": category,
        "fill_status": "unfilled",
        "fill_source": None,
        "suggested_value": None,
        "is_urgent": category in ["报价", "资质", "财务"],  # 这些类别更紧急
    }

    # 尝试从公司资料匹配
    if company_profile:
        company_map = {
            "公司名称": company_profile.get("company_name"),
            "企业名称": company_profile.get("company_name"),
            "信用代码": company_profile.get("credit_code"),
            "统一社会信用代码": company_profile.get("credit_code"),
            "法定代表人": company_profile.get("legal_representative"),
            "联系人": company_profile.get("contact_person"),
            "联系电话": company_profile.get("phone"),
            "电话号码": company_profile.get("phone"),
            "地址": company_profile.get("address"),
            "注册地址": company_profile.get("address"),
            "公司地址": company_profile.get("address"),
            "邮箱": company_profile.get("email"),
            "电子邮箱": company_profile.get("email"),
        }

        # 精确匹配
        for key, value in company_map.items():
            if key in clean_name and value:
                result["fill_status"] = "filled"
                result["fill_source"] = f"company_profiles.{key}"
                result["suggested_value"] = value
                return result

        # 模糊匹配
        for key, value in company_map.items():
            if value and (key in clean_name or clean_name in key):
                result["fill_status"] = "partial"
                result["fill_source"] = f"company_profiles.{key}"
                result["suggested_value"] = value
                return result

        # 银行信息
        if "银行" in clean_name and company_profile.get("bank_info"):
            bank = company_profile["bank_info"]
            if isinstance(bank, dict):
                for bk, bv in bank.items():
                    if bk in clean_name and bv:
                        result["fill_status"] = "filled"
                        result["fill_source"] = f"company_profiles.bank_info.{bk}"
                        result["suggested_value"] = str(bv)
                        return result

        # 资质
        if "资质" in clean_name and company_profile.get("qualifications"):
            quals = company_profile["qualifications"]
            if isinstance(quals, list) and quals:
                result["fill_status"] = "partial"
                result["fill_source"] = "company_profiles.qualifications"
                result["suggested_value"] = json.dumps(quals, ensure_ascii=False)
                return result

    # 尝试从项目数据匹配
    if project_data:
        project_map = {
            "项目名称": project_data.get("project_name"),
            "招标编号": project_data.get("bid_number"),
            "预算": project_data.get("budget"),
            "采购人": project_data.get("buyer"),
            "截止日期": project_data.get("deadline"),
        }

        for key, value in project_map.items():
            if value and key in clean_name:
                result["fill_status"] = "filled"
                result["fill_source"] = f"project_data.{key}"
                result["suggested_value"] = str(value)
                return result

    return result


def analyze_requirements(project_id: int, project_parsed_data: Optional[Dict],
                         get_db_connection_func) -> Dict[str, Any]:
    """
    分析项目的资料需求。

    返回结构化需求清单:
    {
        "project_id": ...,
        "analysis_time": "...",
        "summary": {
            "total": 123,
            "filled": 45,
            "partial": 12,
            "unfilled": 66,
        },
        "by_category": {
            "公司信息": {"total": 10, "filled": 5, ...},
            ...
        },
        "requirements": [
            {"name": "...", "category": "...", "fill_status": "...", ...},
            ...
        ],
        "missing_urgent": [...],  # 紧急但未填充的
    }
    """
    # 获取公司资料
    company_profile = get_company_profile(get_db_connection_func)

    # 从模板中提取占位符（使用 bid_template_engine）
    from bid_template_engine import load_default_template_docx, extract_placeholders_from_docx

    all_placeholders = []
    template_types = ["报价", "商务", "技术"]

    for t_type in template_types:
        doc = load_default_template_docx(t_type)
        if doc:
            placeholders = extract_placeholders_from_docx(doc)
            for ph in placeholders:
                ph["template_type"] = t_type
                all_placeholders.append(ph)

    # 去重（按占位符名称）
    seen = set()
    unique_placeholders = []
    for ph in all_placeholders:
        if ph["name"] not in seen:
            seen.add(ph["name"])
            unique_placeholders.append(ph)

    # 分析每个占位符的填充状态
    requirements = []
    category_stats = {}
    total_filled = 0
    total_partial = 0
    total_unfilled = 0

    for ph in unique_placeholders:
        status = check_placeholder_filled(
            ph["name"], company_profile, project_parsed_data
        )
        status["template_types"] = ph.get("template_type", "unknown")
        status["context"] = ph.get("context", "")
        requirements.append(status)

        # 统计
        cat = status["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "filled": 0, "partial": 0, "unfilled": 0}

        category_stats[cat]["total"] += 1
        if status["fill_status"] == "filled":
            category_stats[cat]["filled"] += 1
            total_filled += 1
        elif status["fill_status"] == "partial":
            category_stats[cat]["partial"] += 1
            total_partial += 1
        else:
            category_stats[cat]["unfilled"] += 1
            total_unfilled += 1

    # 找出紧急但未填充的项
    missing_urgent = [
        r for r in requirements
        if r["fill_status"] == "unfilled" and r["is_urgent"]
    ]

    # 保存到 bid_fill_status 表
    try:
        with get_db_connection_func() as conn:
            cursor = conn.cursor()
            # 清理旧数据
            cursor.execute("DELETE FROM bid_fill_status WHERE project_id = %s", (project_id,))
            for req in requirements:
                cursor.execute(
                    """
                    INSERT INTO bid_fill_status (project_id, field_name, fill_status, fill_source, value)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        project_id,
                        req["name"],
                        req["fill_status"],
                        req["fill_source"],
                        req["suggested_value"],
                    ),
                )
            conn.commit()
            cursor.close()
    except Exception as e:
        logger.warning(f"保存填充状态到数据库失败: {e}")

    return {
        "project_id": project_id,
        "analysis_time": datetime.now().isoformat(),
        "summary": {
            "total": len(requirements),
            "filled": total_filled,
            "partial": total_partial,
            "unfilled": total_unfilled,
            "fill_rate": round(total_filled / len(requirements) * 100, 1) if requirements else 0,
        },
        "by_category": category_stats,
        "requirements": requirements,
        "missing_urgent": missing_urgent,
        "company_profile_available": company_profile is not None,
    }
