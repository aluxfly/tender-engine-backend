"""
评分覆盖率报告引擎 — Day 4

基于 PM 定义的评分标准映射表，评估标书的得分覆盖率：
- 技术方案 (30%)
- 项目管理 (15%)
- 业绩经验 (15%)
- 团队资质 (10%)
- 质量保证 (10%)
- 价格 (20%)

预估总得分 + 改进建议
"""

import logging
import json
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ==================== 评分标准定义 ====================

SCORING_CRITERIA = [
    {
        "name": "技术方案",
        "weight": 30,
        "sub_items": [
            {
                "name": "技术架构合理性",
                "max_score": 10,
                "check_keys": ["技术方案", "技术路线", "系统架构", "架构设计"],
                "related_keys": ["架构", "设计", "系统", "技术", "拓扑", "网络", "部署"],
                "content_sections": ["technical_solution", "技术方案", "技术路线", "系统架构"],
                "description": "评估技术方案的整体架构设计",
            },
            {
                "name": "技术先进性",
                "max_score": 8,
                "check_keys": ["技术创新", "技术先进", "前沿技术", "智能化"],
                "related_keys": ["创新", "先进", "智能", "自动化", "云", "AI", "大数据", "物联网"],
                "content_sections": ["technical_solution", "技术创新", "先进性"],
                "description": "方案采用的技术是否先进",
            },
            {
                "name": "技术可行性",
                "max_score": 7,
                "check_keys": ["可行性", "技术实现", "实施方案", "落地"],
                "related_keys": ["实施", "实现", "方案", "落地", "部署", "集成", "测试"],
                "content_sections": ["technical_solution", "实施方案", "技术可行性"],
                "description": "方案是否具备可落地实施的条件",
            },
            {
                "name": "需求响应度",
                "max_score": 5,
                "check_keys": ["需求理解", "需求响应", "需求分析", "功能覆盖"],
                "related_keys": ["需求", "功能", "响应", "满足", "符合", "要求"],
                "content_sections": ["project_understanding", "需求理解", "需求分析"],
                "description": "对招标需求的响应和覆盖程度",
            },
        ],
    },
    {
        "name": "项目管理",
        "weight": 15,
        "sub_items": [
            {
                "name": "实施计划",
                "max_score": 5,
                "check_keys": ["实施计划", "进度安排", "工期", "里程碑"],
                "related_keys": ["计划", "进度", "工期", "阶段", "时间", "节点"],
                "content_sections": ["work_plan", "实施计划", "进度计划"],
                "description": "项目实施计划的合理性和完整性",
            },
            {
                "name": "团队配置",
                "max_score": 5,
                "check_keys": ["团队", "人员配置", "项目团队", "组织"],
                "related_keys": ["人员", "团队", "配置", "组织", "角色", "工程师"],
                "content_sections": ["work_plan", "团队配置", "人员"],
                "description": "项目团队的配置是否合理",
            },
            {
                "name": "风险控制",
                "max_score": 5,
                "check_keys": ["风险", "应急预案", "风险管控", "保障措施"],
                "related_keys": ["风险", "应急", "保障", "预案", "安全", "措施"],
                "content_sections": ["work_plan", "performance_guarantee", "风险控制"],
                "description": "风险识别和应对措施",
            },
        ],
    },
    {
        "name": "业绩经验",
        "weight": 15,
        "sub_items": [
            {
                "name": "类似项目业绩",
                "max_score": 8,
                "check_keys": ["业绩", "类似项目", "案例", "项目经验"],
                "related_keys": ["项目", "业绩", "案例", "经验", "完成", "合作"],
                "content_sections": ["业绩", "项目经验", "案例"],
                "description": "过往类似项目的业绩情况",
            },
            {
                "name": "行业经验",
                "max_score": 4,
                "check_keys": ["行业经验", "行业背景", "深耕", "专注"],
                "related_keys": ["行业", "领域", "经验", "背景", "深耕", "专注", "多年"],
                "content_sections": ["project_understanding", "行业经验"],
                "description": "在招标方所在行业的经验",
            },
            {
                "name": "客户评价",
                "max_score": 3,
                "check_keys": ["客户评价", "用户反馈", "满意度", "口碑"],
                "related_keys": ["客户", "用户", "满意", "评价", "反馈", "认可"],
                "content_sections": ["客户评价", "用户反馈"],
                "description": "过往客户的评价和反馈",
            },
        ],
    },
    {
        "name": "团队资质",
        "weight": 10,
        "sub_items": [
            {
                "name": "企业资质",
                "max_score": 4,
                "check_keys": ["资质", "资质证书", "企业", "营业执照"],
                "related_keys": ["资质", "证书", "执照", "等级", "许可"],
                "content_sections": ["企业资质", "资质"],
                "description": "企业的资质等级和完整性",
            },
            {
                "name": "核心人员资质",
                "max_score": 3,
                "check_keys": ["人员资质", "证书", "认证", "资格"],
                "related_keys": ["人员", "资质", "证书", "资格", "认证", "专业"],
                "content_sections": ["人员资质", "核心人员"],
                "description": "核心团队成员的专业资质",
            },
            {
                "name": "管理体系认证",
                "max_score": 3,
                "check_keys": ["ISO", "管理体系", "认证", "质量"],
                "related_keys": ["ISO", "管理", "体系", "认证", "标准", "规范"],
                "content_sections": ["管理体系", "认证"],
                "description": "ISO等管理体系认证情况",
            },
        ],
    },
    {
        "name": "质量保证",
        "weight": 10,
        "sub_items": [
            {
                "name": "质量保障体系",
                "max_score": 4,
                "check_keys": ["质量保证", "质量保障", "质量控制", "质量管理"],
                "related_keys": ["质量", "保障", "控制", "管理", "检验", "标准"],
                "content_sections": ["performance_guarantee", "质量保证", "质量保障"],
                "description": "质量保障体系的完整性",
            },
            {
                "name": "售后服务",
                "max_score": 3,
                "check_keys": ["售后", "服务承诺", "维保", "运维"],
                "related_keys": ["售后", "服务", "维保", "运维", "支持", "响应"],
                "content_sections": ["service_commitment", "售后服务", "服务承诺"],
                "description": "售后服务方案的完善程度",
            },
            {
                "name": "培训方案",
                "max_score": 3,
                "check_keys": ["培训", "培训计划", "知识转移"],
                "related_keys": ["培训", "计划", "知识", "转移", "学习", "教学"],
                "content_sections": ["service_commitment", "培训方案"],
                "description": "用户培训方案的可行性",
            },
        ],
    },
    {
        "name": "价格",
        "weight": 20,
        "sub_items": [
            {
                "name": "报价合理性",
                "max_score": 10,
                "check_keys": ["报价", "投标报价", "价格"],
                "related_keys": ["报价", "价格", "金额", "费用", "预算", "成本"],
                "content_sections": ["报价", "价格"],
                "description": "报价是否在合理范围内",
            },
            {
                "name": "成本透明度",
                "max_score": 5,
                "check_keys": ["明细", "成本", "报价明细", "费用构成"],
                "related_keys": ["明细", "成本", "费用", "构成", "透明", "分解"],
                "content_sections": ["成本明细", "费用"],
                "description": "报价明细的透明度和合理性",
            },
            {
                "name": "性价比",
                "max_score": 5,
                "check_keys": ["性价比", "价值", "优惠", "综合性价比"],
                "related_keys": ["性价比", "价值", "优势", "合理", "经济", "优惠"],
                "content_sections": ["性价比", "价值"],
                "description": "整体方案的性价比",
            },
        ],
    },
]


def generate_scoring_report(project_id: int, get_db_connection=None) -> dict:
    """
    生成评分覆盖率报告

    Args:
        project_id: 标书项目 ID
        get_db_connection: 数据库连接获取函数

    Returns:
        {
            "total_score": float,          # 预估总得分 (0-100)
            "max_score": float,            # 满分 (100)
            "coverage": float,             # 覆盖率 (0-100%)
            "breakdown": [                 # 各维度得分
                {
                    "name": str,
                    "weight": int,
                    "score": float,
                    "max_score": int,
                    "coverage": float,
                    "sub_items": [...]
                }
            ],
            "suggestions": [str],          # 改进建议
            "generated_at": str,
        }
    """
    if get_db_connection is None:
        raise ValueError("get_db_connection 参数不能为空")

    # 获取项目数据
    project_data = _get_project_data(project_id, get_db_connection)
    if project_data is None:
        return {
            "total_score": 0,
            "max_score": 100,
            "coverage": 0,
            "breakdown": [],
            "suggestions": [f"项目 ID {project_id} 不存在，无法生成评分报告"],
            "generated_at": datetime.now().isoformat(),
        }

    company_data = _get_company_data(project_id, get_db_connection)
    parsed = project_data.get("parsed_data", {})

    breakdown = []
    all_suggestions = []
    total_score = 0.0

    for criterion in SCORING_CRITERIA:
        sub_results = []
        criterion_score = 0.0
        criterion_max = sum(s["max_score"] for s in criterion["sub_items"])

        for sub_item in criterion["sub_items"]:
            score, detail = _evaluate_sub_item(sub_item, parsed, company_data, project_data)
            sub_results.append({
                "name": sub_item["name"],
                "max_score": sub_item["max_score"],
                "score": score,
                "description": detail["description"],
                "evidence": detail.get("evidence", ""),
                "missing": detail.get("missing", []),
            })
            criterion_score += score

            # 收集改进建议
            if detail.get("missing"):
                for m in detail["missing"]:
                    all_suggestions.append(f"[{criterion['name']}/{sub_item['name']}] 缺少: {m}")

        criterion_coverage = (criterion_score / criterion_max * 100) if criterion_max > 0 else 0
        # 加权得分
        weighted_score = criterion_score * criterion["weight"] / criterion_max

        breakdown.append({
            "name": criterion["name"],
            "weight": criterion["weight"],
            "score": round(criterion_score, 1),
            "max_score": criterion_max,
            "coverage": round(criterion_coverage, 1),
            "weighted_score": round(weighted_score, 1),
            "sub_items": sub_results,
        })

        total_score += weighted_score

    overall_coverage = (total_score / 100 * 100)  # total_score is already weighted to 100

    # 生成通用建议
    general_suggestions = _generate_general_suggestions(breakdown, parsed, company_data)
    all_suggestions.extend(general_suggestions)

    return {
        "total_score": round(total_score, 1),
        "max_score": 100,
        "coverage": round(overall_coverage, 1),
        "breakdown": breakdown,
        "suggestions": all_suggestions,
        "generated_at": datetime.now().isoformat(),
    }


# ==================== 内部评估函数 ====================

def _evaluate_sub_item(sub_item: dict, parsed: dict, company_data: Optional[dict],
                       project_data: dict) -> tuple:
    """评估单个子评分项，返回 (score, detail)

    评分策略（多层匹配）：
    1. 精确关键词匹配 — 在解析数据中搜索 check_keys
    2. 相关关键词匹配 — 在解析数据中搜索 related_keys（权重降低）
    3. 生成内容识别 — 如果 parsed_data 中有对应 AI 生成内容，给基础分
    4. 公司资料加分 — 从 company_data 中提取额外证据
    """
    score = 0.0
    evidence = []
    missing = []

    # 搜索匹配的关键词
    flat_text = _flatten_parsed(parsed)

    # ---- 层1: 精确关键词匹配 ----
    matched_keys = []
    for key in sub_item["check_keys"]:
        if key in flat_text:
            matched_keys.append(key)

    # ---- 层2: 相关关键词匹配（降权） ----
    related_keys = sub_item.get("related_keys", [])
    matched_related = []
    for key in related_keys:
        if key in flat_text and key not in matched_keys:
            matched_related.append(key)

    # ---- 层3: AI 生成内容识别 ----
    has_generated_content = _check_generated_content(parsed, sub_item)

    # ---- 层4: 公司资料加分 ----
    if company_data:
        extra_text = _flatten_company(company_data)
        for key in sub_item["check_keys"]:
            if key in extra_text and key not in matched_keys:
                matched_keys.append(key)
        for key in related_keys:
            if key in extra_text and key not in matched_keys and key not in matched_related:
                matched_related.append(key)

    # ---- 综合评分 ----
    total_keys = len(sub_item["check_keys"])
    exact_ratio = len(matched_keys) / total_keys if total_keys > 0 else 0
    related_ratio = len(matched_related) / len(related_keys) if related_keys else 0

    # 综合覆盖率 = 精确匹配（100%权重）+ 相关匹配（40%权重）
    coverage_ratio = exact_ratio * 1.0 + related_ratio * 0.4
    # 归一化到 0-1
    max_possible = 1.0 + 0.4  # 精确100% + 相关100%
    normalized_ratio = min(coverage_ratio / max_possible, 1.0) if max_possible > 0 else 0

    # 有 AI 生成内容但关键词未匹配时，给基础分 25%
    if has_generated_content and normalized_ratio < 0.25:
        normalized_ratio = max(normalized_ratio, 0.25)
        evidence.append(f"已生成{sub_item['name']}相关内容（关键词待补充）")

    # 根据覆盖率估算得分
    if normalized_ratio >= 0.75:
        score = sub_item["max_score"] * 0.85
        evidence.append(f"找到 {len(matched_keys)}/{total_keys} 个关键内容")
        if matched_related:
            evidence.append(f"关联内容 {len(matched_related)} 项")
    elif normalized_ratio >= 0.5:
        score = sub_item["max_score"] * 0.6
        evidence.append(f"部分覆盖 ({len(matched_keys)}/{total_keys} 个关键内容)")
        missing = [k for k in sub_item["check_keys"] if k not in matched_keys]
    elif normalized_ratio >= 0.25:
        score = sub_item["max_score"] * 0.4
        evidence.append(f"基础覆盖 ({len(matched_keys)}/{total_keys} 个关键内容)")
        missing = [k for k in sub_item["check_keys"] if k not in matched_keys][:2]
    else:
        score = sub_item["max_score"] * 0.15
        evidence.append(f"覆盖不足 ({len(matched_keys)}/{total_keys} 个关键内容)")
        missing = sub_item["check_keys"]

    # 特殊检查：价格相关
    if "价格" in sub_item.get("name", "") or sub_item.get("name") == "报价合理性":
        score = _evaluate_price(parsed, company_data, score, sub_item["max_score"], evidence, missing)

    # 特殊检查：资质相关
    if "资质" in sub_item.get("name", "") and company_data:
        score = _evaluate_qualifications(company_data, score, sub_item["max_score"], evidence, missing)

    return round(score, 1), {
        "description": sub_item["description"],
        "evidence": "；".join(evidence) if evidence else "未找到相关内容",
        "missing": missing,
    }


def _check_generated_content(parsed: dict, sub_item: dict) -> bool:
    """检查是否有 AI 生成的相关内容"""
    content_sections = sub_item.get("content_sections", [])
    if not content_sections or not parsed:
        return False

    # 检查 parsed_data 中是否有对应键的内容
    for section in content_sections:
        if section in parsed:
            val = parsed[section]
            if isinstance(val, str) and len(val) > 100:
                return True
            if isinstance(val, dict) and len(str(val)) > 100:
                return True

    # 检查 key_info 中是否有相关内容
    key_info = parsed.get("key_info", {})
    if isinstance(key_info, dict):
        for section in content_sections:
            if section in key_info:
                val = key_info[section]
                if isinstance(val, str) and len(val) > 50:
                    return True

    return False


def _evaluate_price(parsed: dict, company_data: Optional[dict],
                    current_score: float, max_score: float,
                    evidence: list, missing: list) -> float:
    """评估价格项"""
    key_info = parsed.get("key_info", {}) if isinstance(parsed, dict) else {}
    all_data = {**key_info, **parsed}

    budget = None
    bid_amount = None

    for src in [key_info, all_data]:
        if not budget:
            budget = src.get("budget") or src.get("project_budget") or src.get("control_price")
        if not bid_amount:
            bid_amount = src.get("bid_amount") or src.get("报价")

    if budget and bid_amount:
        try:
            budget = float(budget)
            bid_amount = float(bid_amount)
        except (ValueError, TypeError):
            return current_score

        if budget > 0:
            ratio = bid_amount / budget
            if 0.6 <= ratio <= 0.85:
                # 报价在合理区间，给高分
                current_score = max_score * 0.9
                evidence.append(f"报价合理（占预算 {ratio*100:.1f}%）")
            elif 0.85 < ratio <= 1.0:
                current_score = max_score * 0.7
                evidence.append(f"报价偏高（占预算 {ratio*100:.1f}%）")
            elif ratio > 1.0:
                current_score = max_score * 0.2
                evidence.append(f"报价超预算（占预算 {ratio*100:.1f}%）— 废标风险")
                missing.append("报价超出预算")
            else:
                current_score = max_score * 0.5
                evidence.append(f"报价偏低（占预算 {ratio*100:.1f}%）— 可能影响评标")
    elif budget:
        missing.append("未填写投标报价")

    return current_score


def _evaluate_qualifications(company_data: Optional[dict],
                             current_score: float, max_score: float,
                             evidence: list, missing: list) -> float:
    """评估资质项"""
    if company_data is None:
        missing.append("公司资料未关联")
        return current_score * 0.3

    quals = company_data.get("qualifications", [])
    credit_code = company_data.get("credit_code")
    legal_rep = company_data.get("legal_representative")

    score_boost = 0
    if credit_code:
        score_boost += 0.2
        evidence.append("信用代码已填写")
    else:
        missing.append("统一社会信用代码")

    if legal_rep:
        score_boost += 0.1
        evidence.append("法定代表人已填写")
    else:
        missing.append("法定代表人")

    if quals:
        score_boost += min(0.3, len(quals) * 0.1)
        evidence.append(f"资质证书 {len(quals)} 项")
    else:
        missing.append("资质证书")

    new_score = max_score * score_boost
    return max(current_score, new_score)


def _generate_general_suggestions(breakdown: list, parsed: dict,
                                  company_data: Optional[dict]) -> list:
    """生成通用改进建议"""
    suggestions = []

    for item in breakdown:
        if item["coverage"] < 50:
            suggestions.append(
                f"⚠️ 【{item['name']}】覆盖率仅 {item['coverage']}%，"
                f"建议重点补充相关内容，这是高权重评分项（{item['weight']}%）"
            )
        elif item["coverage"] < 70:
            suggestions.append(
                f"📋 【{item['name']}】覆盖率 {item['coverage']}%，"
                f"仍有提升空间（权重 {item['weight']}%）"
            )

    # 检查整体缺失
    if company_data is None:
        suggestions.append("🔴 未关联公司资料，建议立即录入公司基本信息和资质")

    if not parsed or not parsed.get("key_info"):
        suggestions.append("📝 招标文件解析数据不完整，建议重新上传招标文件")

    return suggestions


def _flatten_parsed(parsed: dict) -> str:
    """将解析数据展平为字符串，方便搜索"""
    if not parsed:
        return ""

    result = json.dumps(parsed, ensure_ascii=False, default=str)
    # 也合并所有 key_info 的值
    key_info = parsed.get("key_info", {})
    if isinstance(key_info, dict):
        result += " " + " ".join(str(v) for v in key_info.values())
    return result


def _flatten_company(company_data: Optional[dict]) -> str:
    """将公司资料展平为字符串"""
    if not company_data:
        return ""
    parts = []
    for k, v in company_data.items():
        if isinstance(v, list):
            parts.extend(str(item) for item in v)
        elif isinstance(v, dict):
            parts.extend(str(val) for val in v.values())
        elif v:
            parts.append(str(v))
    return " ".join(parts)


def _get_project_data(project_id: int, get_db_connection) -> Optional[dict]:
    """获取项目数据"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, parsed_data FROM bid_projects WHERE id = %s",
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
        }
    except Exception as e:
        logger.error(f"获取项目数据失败: {e}")
        return None


def _get_company_data(project_id: int, get_db_connection) -> Optional[dict]:
    """获取关联的公司资料"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
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
