"""
废标项校验引擎 — Day 4

扫描已填充的标书数据，检查废标项：
1. 关键资质缺失（营业执照、资质证书等）
2. 报价超过预算上限
3. 必填项未完成
4. 投标有效期不足
5. 法定代表人或授权代表缺失
"""

import logging
import json
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ==================== 废标项定义 ====================

# 必须拥有的关键资质
REQUIRED_QUALIFICATIONS = [
    {"key": "营业执照", "field_pattern": "营业执照"},
    {"key": "资质证书", "field_pattern": "资质"},
]

# 必填字段（公司资料层面）
REQUIRED_COMPANY_FIELDS = [
    {"key": "公司名称", "db_field": "company_name"},
    {"key": "统一社会信用代码", "db_field": "credit_code"},
    {"key": "法定代表人", "db_field": "legal_representative"},
    {"key": "联系人", "db_field": "contact_person"},
    {"key": "联系电话", "db_field": "phone"},
]

# 必填字段（标书项目层面）
REQUIRED_BID_FIELDS = [
    {"key": "项目名称", "parsed_key": "project_name"},
    {"key": "招标编号", "parsed_key": "bid_number"},
]

# 默认投标有效期（天）
DEFAULT_VALIDITY_DAYS = 90


def check_disqualification(project_id: int, get_db_connection=None) -> dict:
    """
    检查废标项，返回 {passed: bool, items: [...]}

    Args:
        project_id: 标书项目 ID
        get_db_connection: 数据库连接获取函数（上下文管理器）

    Returns:
        {
            "passed": bool,
            "total_checks": int,
            "failed_count": int,
            "warning_count": int,
            "items": [
                {
                    "field": str,       # 检查项名称
                    "status": "failed" | "warning" | "passed",
                    "severity": "critical" | "high" | "medium",
                    "message": str,     # 详细描述
                    "suggestion": str   # 修复建议
                }
            ],
            "checked_at": str           # ISO 时间
        }
    """
    if get_db_connection is None:
        raise ValueError("get_db_connection 参数不能为空")

    items = []

    # ---- 1. 获取项目信息 ----
    project_data = _get_project_data(project_id, get_db_connection)
    if project_data is None:
        return {
            "passed": False,
            "total_checks": 0,
            "failed_count": 0,
            "warning_count": 0,
            "items": [{
                "field": "项目存在性",
                "status": "failed",
                "severity": "critical",
                "message": f"项目 ID {project_id} 不存在",
                "suggestion": "请确认项目 ID 是否正确",
            }],
            "checked_at": datetime.now().isoformat(),
        }

    # ---- 2. 获取公司资料 ----
    company_data = _get_company_data(project_id, get_db_connection)

    # ---- 3. 逐项检查 ----
    items.extend(_check_company_fields(company_data))
    items.extend(_check_qualifications(company_data))
    items.extend(_check_budget(project_data))
    items.extend(_check_bid_fields(project_data))
    items.extend(_check_validity_period(project_data))
    items.extend(_check_legal_representative(company_data, project_data))

    # ---- 4. 汇总 ----
    failed = [i for i in items if i["status"] == "failed"]
    warnings = [i for i in items if i["status"] == "warning"]

    return {
        "passed": len(failed) == 0,
        "total_checks": len(items),
        "failed_count": len(failed),
        "warning_count": len(warnings),
        "items": items,
        "checked_at": datetime.now().isoformat(),
    }


# ==================== 内部检查函数 ====================

def _get_project_data(project_id: int, get_db_connection) -> Optional[dict]:
    """获取项目完整数据（含解析数据）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, parsed_data, status, created_at, updated_at
                FROM bid_projects WHERE id = %s
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            cursor.close()
        if not row:
            return None
        parsed = row[2]
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return {
            "id": row[0],
            "title": row[1],
            "parsed_data": parsed or {},
            "status": row[3],
        }
    except Exception as e:
        logger.error(f"获取项目数据失败: {e}")
        return None


def _get_company_data(project_id: int, get_db_connection) -> Optional[dict]:
    """获取关联的公司资料"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 尝试从 parsed_data 中获取 company_profile_id
            cursor.execute(
                "SELECT parsed_data FROM bid_projects WHERE id = %s",
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            parsed = row[0]
            if isinstance(parsed, str):
                parsed = json.loads(parsed)

            company_profile_id = None
            if parsed and isinstance(parsed, dict):
                company_profile_id = parsed.get("company_profile_id")

            if company_profile_id:
                cursor.execute(
                    """
                    SELECT id, company_name, credit_code, legal_representative,
                           contact_person, phone, email, address, bank_info, qualifications
                    FROM company_profiles WHERE id = %s
                    """,
                    (company_profile_id,),
                )
            else:
                # 没有关联公司资料，取第一条
                cursor.execute(
                    """
                    SELECT id, company_name, credit_code, legal_representative,
                           contact_person, phone, email, address, bank_info, qualifications
                    FROM company_profiles ORDER BY created_at DESC LIMIT 1
                    """
                )

            row = cursor.fetchone()
            cursor.close()

            if not row:
                return None

            qual = row[9]
            if isinstance(qual, str):
                qual = json.loads(qual)
            bank = row[8]
            if isinstance(bank, str):
                bank = json.loads(bank)

            return {
                "id": row[0],
                "company_name": row[1],
                "credit_code": row[2],
                "legal_representative": row[3],
                "contact_person": row[4],
                "phone": row[5],
                "email": row[6],
                "address": row[7],
                "bank_info": bank or {},
                "qualifications": qual or [],
            }
    except Exception as e:
        logger.error(f"获取公司资料失败: {e}")
        return None


def _check_company_fields(company_data: Optional[dict]) -> list:
    """检查公司必填字段"""
    items = []
    if company_data is None:
        for f in REQUIRED_COMPANY_FIELDS:
            items.append({
                "field": f["key"],
                "status": "failed",
                "severity": "critical",
                "message": f"公司资料未关联，{f['key']}无法确认",
                "suggestion": "请先录入公司资料并关联到本项目",
            })
        return items

    for f in REQUIRED_COMPANY_FIELDS:
        val = company_data.get(f["db_field"])
        if not val or (isinstance(val, str) and not val.strip()):
            items.append({
                "field": f["key"],
                "status": "failed",
                "severity": "critical" if f["db_field"] in ("company_name", "credit_code") else "high",
                "message": f"{f['key']}缺失或为空",
                "suggestion": f"请在公司资料中补充{f['key']}",
            })
        else:
            items.append({
                "field": f["key"],
                "status": "passed",
                "severity": "medium",
                "message": f"{f['key']}已填写：{val}",
                "suggestion": "",
            })

    return items


def _check_qualifications(company_data: Optional[dict]) -> list:
    """检查关键资质证书"""
    items = []
    if company_data is None:
        for q in REQUIRED_QUALIFICATIONS:
            items.append({
                "field": f"{q['key']}证书",
                "status": "failed",
                "severity": "critical",
                "message": f"公司资料未关联，{q['key']}无法确认",
                "suggestion": "请上传营业执照和资质证书扫描件",
            })
        return items

    qualifications = company_data.get("qualifications", [])

    for q in REQUIRED_QUALIFICATIONS:
        found = False
        qual_name = ""
        for qual in qualifications:
            if isinstance(qual, dict):
                qname = qual.get("name", "") or qual.get("type", "")
            else:
                qname = str(qual)
            if q["field_pattern"] in qname:
                found = True
                qual_name = qname
                break

        if found:
            items.append({
                "field": f"{q['key']}证书",
                "status": "passed",
                "severity": "medium",
                "message": f"{q['key']}已提供：{qual_name}",
                "suggestion": "",
            })
        else:
            items.append({
                "field": f"{q['key']}证书",
                "status": "failed",
                "severity": "critical",
                "message": f"{q['key']}缺失 — 废标风险极高",
                "suggestion": f"请立即上传{q['key']}原件扫描件到公司资料",
            })

    return items


def _check_budget(project_data: Optional[dict]) -> list:
    """检查报价是否超过预算上限"""
    items = []
    if project_data is None:
        return items

    parsed = project_data.get("parsed_data", {})
    key_info = parsed.get("key_info", {}) if isinstance(parsed, dict) else {}

    budget = None
    bid_amount = None

    # 从招标文件解析数据中获取预算
    for src in [key_info, parsed]:
        if isinstance(src, dict):
            budget = src.get("budget") or src.get("project_budget") or src.get("control_price")
            if budget:
                break

    # 从自动填充数据中获取报价
    for src in [key_info, parsed]:
        if isinstance(src, dict):
            bid_amount = src.get("bid_amount") or src.get("报价")
            if bid_amount:
                break

    if budget and bid_amount:
        try:
            budget = float(budget)
            bid_amount = float(bid_amount)
        except (ValueError, TypeError):
            return items

        ratio = (bid_amount / budget * 100) if budget > 0 else 0

        if bid_amount > budget:
            items.append({
                "field": "报价检查",
                "status": "failed",
                "severity": "critical",
                "message": f"报价 ¥{bid_amount:,.2f} 超过预算 ¥{budget:,.2f}（{ratio:.1f}%）— 直接废标",
                "suggestion": "请调整报价至预算范围内",
            })
        elif ratio > 90:
            items.append({
                "field": "报价检查",
                "status": "warning",
                "severity": "high",
                "message": f"报价 ¥{bid_amount:,.2f} 接近预算上限 ¥{budget:,.2f}（{ratio:.1f}%）",
                "suggestion": "报价接近预算，建议适当降低以增强竞争力",
            })
        else:
            items.append({
                "field": "报价检查",
                "status": "passed",
                "severity": "medium",
                "message": f"报价 ¥{bid_amount:,.2f} 在预算 ¥{budget:,.2f} 范围内（{ratio:.1f}%）",
                "suggestion": "",
            })
    elif budget:
        items.append({
            "field": "报价检查",
            "status": "warning",
            "severity": "medium",
            "message": f"预算为 ¥{budget:,.2f}，但未填写报价",
            "suggestion": "请填写投标报价",
        })
    else:
        items.append({
            "field": "报价检查",
            "status": "warning",
            "severity": "medium",
            "message": "招标文件中未明确预算金额",
            "suggestion": "建议与招标方确认预算范围",
        })

    return items


def _check_bid_fields(project_data: Optional[dict]) -> list:
    """检查标书必填项"""
    items = []
    if project_data is None:
        return items

    parsed = project_data.get("parsed_data", {})
    key_info = parsed.get("key_info", {}) if isinstance(parsed, dict) else {}

    for f in REQUIRED_BID_FIELDS:
        # 先查 key_info，再查 title
        val = None
        if isinstance(key_info, dict):
            val = key_info.get(f["parsed_key"])
        if not val and f["parsed_key"] == "project_name":
            val = project_data.get("title")

        if not val or (isinstance(val, str) and not val.strip()):
            items.append({
                "field": f["key"],
                "status": "failed",
                "severity": "high",
                "message": f"{f['key']}缺失",
                "suggestion": f"请在招标文件解析数据中补充{f['key']}",
            })
        else:
            items.append({
                "field": f["key"],
                "status": "passed",
                "severity": "medium",
                "message": f"{f['key']}已填写",
                "suggestion": "",
            })

    return items


def _check_validity_period(project_data: Optional[dict]) -> list:
    """检查投标有效期"""
    items = []
    if project_data is None:
        return items

    parsed = project_data.get("parsed_data", {})
    key_info = parsed.get("key_info", {}) if isinstance(parsed, dict) else {}

    validity_days = None
    for src in [key_info, parsed]:
        if isinstance(src, dict):
            vd = src.get("validity_period") or src.get("validity_days") or src.get("投标有效期")
            if vd is not None:
                try:
                    validity_days = int(str(vd).replace("天", "").replace("日", "").replace("个", ""))
                except ValueError:
                    pass
                if validity_days:
                    break

    if validity_days is not None:
        if validity_days < 60:
            items.append({
                "field": "投标有效期",
                "status": "failed",
                "severity": "critical",
                "message": f"投标有效期 {validity_days} 天，低于最低要求 60 天 — 废标风险",
                "suggestion": "投标有效期应不少于 60 天，建议设置为 90 天",
            })
        elif validity_days < DEFAULT_VALIDITY_DAYS:
            items.append({
                "field": "投标有效期",
                "status": "warning",
                "severity": "medium",
                "message": f"投标有效期 {validity_days} 天，低于建议值 {DEFAULT_VALIDITY_DAYS} 天",
                "suggestion": f"建议投标有效期设置为 {DEFAULT_VALIDITY_DAYS} 天",
            })
        else:
            items.append({
                "field": "投标有效期",
                "status": "passed",
                "severity": "medium",
                "message": f"投标有效期 {validity_days} 天，满足要求",
                "suggestion": "",
            })
    else:
        items.append({
            "field": "投标有效期",
            "status": "warning",
            "severity": "medium",
            "message": "招标文件中未明确投标有效期",
            "suggestion": "默认按 90 天设置，请确认招标文件要求",
        })

    return items


def _check_legal_representative(company_data: Optional[dict], project_data: Optional[dict]) -> list:
    """检查法定代表人或授权代表"""
    items = []

    if company_data is None:
        items.append({
            "field": "法定代表人",
            "status": "failed",
            "severity": "critical",
            "message": "法定代表人缺失 — 废标项",
            "suggestion": "请在公司资料中填写法定代表人姓名",
        })
        items.append({
            "field": "授权代表",
            "status": "warning",
            "severity": "high",
            "message": "授权代表信息缺失",
            "suggestion": "建议填写授权代表信息（如与法定代表人不同）",
        })
        return items

    legal_rep = company_data.get("legal_representative")
    contact_person = company_data.get("contact_person")

    if not legal_rep or (isinstance(legal_rep, str) and not legal_rep.strip()):
        items.append({
            "field": "法定代表人",
            "status": "failed",
            "severity": "critical",
            "message": "法定代表人缺失 — 废标项",
            "suggestion": "请在公司资料中填写法定代表人姓名",
        })
    else:
        items.append({
            "field": "法定代表人",
            "status": "passed",
            "severity": "medium",
            "message": f"法定代表人：{legal_rep}",
            "suggestion": "",
        })

    if not contact_person or (isinstance(contact_person, str) and not contact_person.strip()):
        items.append({
            "field": "授权代表",
            "status": "warning",
            "severity": "high",
            "message": "授权代表信息缺失",
            "suggestion": "建议填写授权代表（联系人）信息",
        })
    else:
        items.append({
            "field": "授权代表",
            "status": "passed",
            "severity": "medium",
            "message": f"授权代表：{contact_person}",
            "suggestion": "",
        })

    return items
