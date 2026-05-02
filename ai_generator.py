"""
Day 3: AI 内容生成引擎
=====================
5 个 AI 内容生成方法，对接大模型 API。
若大模型 API 不可用，自动使用素材库模板兜底。

功能:
  - generate_technical_solution: 技术方案（技术路线 + 实施方案 + 设备选型）
  - generate_project_understanding: 项目理解（背景分析 + 理解阐述）
  - generate_work_plan: 工作规划（详细计划 + 时间节点）
  - generate_performance_guarantee: 履约保障（质量 + 安全 + 进度）
  - generate_service_commitment: 服务承诺（定制化承诺）

素材来源:
  /root/.openclaw/workspace-knowledge-manager/bid-materials/
  - technical-paragraphs/  — 30 个技术段落
  - ai-prompts/           — 5 个 AI Prompt 模板
  - commitment-templates/  — 5 个承诺模板
"""

import os
import re
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

# 素材库路径
BID_MATERIALS_DIR = Path("/root/.openclaw/workspace-knowledge-manager/bid-materials")
TECHNICAL_PARAGRAPHS_DIR = BID_MATERIALS_DIR / "technical-paragraphs"
AI_PROMPTS_DIR = BID_MATERIALS_DIR / "ai-prompts"
COMMITMENT_TEMPLATES_DIR = BID_MATERIALS_DIR / "commitment-templates"

# LLM API 配置（OpenAI 兼容接口）
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
LLM_RETRY_COUNT = int(os.environ.get("LLM_RETRY_COUNT", "2"))
LLM_RETRY_DELAY = int(os.environ.get("LLM_RETRY_DELAY", "3"))
LLM_FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "")  # 主模型失败时尝试的备选模型

# ==================== 全局 HTTP 连接池 ====================

_http_session: Optional[requests.Session] = None


def get_http_session() -> requests.Session:
    """获取全局 HTTP 连接池（复用 TCP 连接）"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=1,
            pool_block=False,
        )
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


# ==================== 素材加载 ====================

def load_technical_paragraphs() -> Dict[str, str]:
    """加载所有技术段落，返回 {文件名: 内容} 字典"""
    paragraphs = {}
    if not TECHNICAL_PARAGRAPHS_DIR.exists():
        logger.warning(f"技术段落目录不存在: {TECHNICAL_PARAGRAPHS_DIR}")
        return paragraphs
    for f in sorted(TECHNICAL_PARAGRAPHS_DIR.glob("*.md")):
        try:
            paragraphs[f.name] = f.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取技术段落失败 {f.name}: {e}")
    return paragraphs


def load_ai_prompt(prompt_name: str) -> str:
    """加载指定的 AI Prompt 模板"""
    prompt_file = AI_PROMPTS_DIR / f"{prompt_name}.md"
    if not prompt_file.exists():
        logger.warning(f"Prompt 模板不存在: {prompt_file}")
        return ""
    try:
        return prompt_file.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"读取 Prompt 失败: {e}")
        return ""


def load_commitment_template(template_name: str) -> str:
    """加载承诺模板"""
    tpl_file = COMMITMENT_TEMPLATES_DIR / f"{template_name}.md"
    if not tpl_file.exists():
        logger.warning(f"承诺模板不存在: {tpl_file}")
        return ""
    try:
        return tpl_file.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"读取承诺模板失败: {e}")
        return ""


def load_all_commitment_templates() -> Dict[str, str]:
    """加载所有承诺模板"""
    templates = {}
    if not COMMITMENT_TEMPLATES_DIR.exists():
        return templates
    for f in sorted(COMMITMENT_TEMPLATES_DIR.glob("*.md")):
        try:
            templates[f.name] = f.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取承诺模板失败 {f.name}: {e}")
    return templates


# ==================== 技术段落分类检索 ====================

# 技术段落分类映射：生成类型 -> 相关段落关键词
TECH_PARAGRAPH_CATEGORIES = {
    "technical_solution": [
        "技术架构", "通信", "视频监控", "系统集成", "网络部署",
        "数据采集", "安全防护", "数据备份", "灾备恢复",
    ],
    "work_plan": [
        "组织架构", "进度管理", "风险管理", "沟通协调",
        "变更管理", "文档管理", "测试验收", "培训",
    ],
    "performance_guarantee": [
        "质量管理", "质量控制", "质量检验", "质量改进",
        "安全管理体系", "安全防护措施", "应急预案",
        "安全生产", "职业健康",
    ],
    "service_commitment": [
        "运维服务", "售后服务",
    ],
}


def find_relevant_paragraphs(category: str, paragraphs: Dict[str, str], max_count: int = 5) -> List[str]:
    """根据分类查找相关技术段落"""
    keywords = TECH_PARAGRAPH_CATEGORIES.get(category, [])
    scored = []
    for name, content in paragraphs.items():
        score = sum(1 for kw in keywords if kw in name or kw in content[:200])
        if score > 0:
            scored.append((score, name, content))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, _, c in scored[:max_count]]


# ==================== LLM 调用 ====================

def call_llm_api(system_prompt: str, user_prompt: str, model: Optional[str] = None) -> Optional[str]:
    """
    调用大模型 API（OpenAI 兼容接口）。
    使用全局 HTTP 连接池，带重试机制和备选模型降级。

    Returns:
        生成的文本，或 None（API 不可用时）
    """
    if not LLM_API_KEY:
        logger.info("LLM_API_KEY 未配置，使用素材库兜底")
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }

    # 构建模型列表：主模型 → 备选模型
    models_to_try = [model or LLM_MODEL]
    if LLM_FALLBACK_MODEL and LLM_FALLBACK_MODEL not in models_to_try:
        models_to_try.append(LLM_FALLBACK_MODEL)

    for attempt_model in models_to_try:
        payload = {
            "model": attempt_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": LLM_MAX_TOKENS,
        }

        for attempt in range(1 + LLM_RETRY_COUNT):
            try:
                session = get_http_session()
                resp = session.post(LLM_API_URL, json=payload, headers=headers, timeout=LLM_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()

                # 兼容多种返回格式
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    if content:
                        model_label = attempt_model
                        if attempt_model != (model or LLM_MODEL):
                            model_label += " (备选)"
                        logger.info(f"LLM API 调用成功 [{model_label}]，返回 {len(content)} 字符")
                        return content

                logger.warning(f"LLM API 返回为空: {data}")

            except requests.exceptions.Timeout:
                logger.warning(f"LLM API 超时（>{LLM_TIMEOUT}s），模型={attempt_model}，第{attempt+1}次尝试")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"LLM API 连接失败: {e}，模型={attempt_model}")
                # 连接错误不重试，直接跳出
                break
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                error_text = e.response.text[:200]
                logger.warning(f"LLM API HTTP {status_code}: {error_text}，模型={attempt_model}")
                # 4xx 错误（除 429）不重试
                if 400 <= status_code < 500 and status_code != 429:
                    break
            except Exception as e:
                logger.warning(f"LLM API 异常: {e}，模型={attempt_model}")

            # 重试延迟（指数退避）
            if attempt < LLM_RETRY_COUNT:
                delay = LLM_RETRY_DELAY * (2 ** attempt)
                logger.info(f"等待 {delay}s 后重试...")
                time.sleep(delay)

        # 主模型失败，如果有备选模型则继续尝试
        if attempt_model == (model or LLM_MODEL) and LLM_FALLBACK_MODEL:
            logger.info(f"主模型 {model or LLM_MODEL} 失败，尝试备选模型 {LLM_FALLBACK_MODEL}")

    logger.warning("LLM API 所有尝试均失败，使用素材库兜底")
    return None


# ==================== 兜底模板生成 ====================

def _build_fallback_technical_solution(requirements: dict, paragraphs: Dict[str, str]) -> str:
    """使用素材库生成技术方案（兜底）"""
    project_name = requirements.get("project_name", "本项目")
    tech_reqs = requirements.get("technical_requirements", "")

    relevant = find_relevant_paragraphs("technical_solution", paragraphs, max_count=5)

    sections = []
    sections.append(f"# 技术方案 — {project_name}\n")
    sections.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    sections.append(f"生成方式：素材库模板（LLM API 不可用时的兜底方案）\n")

    sections.append("## 一、技术路线设计\n")
    if relevant:
        # 使用第一个相关段落作为基础
        sections.append(relevant[0].split("\n\n")[0] + "\n")
        sections.append(f"\n针对本项目「{project_name}」，技术路线设计如下：\n")
        if tech_reqs:
            sections.append(f"招标技术要求：{tech_reqs}\n")
    else:
        sections.append("本项目采用成熟、可靠的技术架构，确保系统稳定运行。\n")

    sections.append("## 二、技术实施方案\n")
    sections.append("### 2.1 实施阶段划分\n")
    sections.append("1. **需求分析与方案设计阶段**：深入理解招标需求，完成技术方案设计\n")
    sections.append("2. **设备采购与生产阶段**：按技术方案采购设备，严格把控质量\n")
    sections.append("3. **系统部署与集成阶段**：现场安装调试，完成系统集成\n")
    sections.append("4. **测试验收与交付阶段**：全面测试验证，完成项目验收\n")

    if len(relevant) > 1:
        sections.append("\n### 2.2 关键技术措施\n")
        for p in relevant[1:3]:
            # 取段落的第一小节
            first_section = p.split("\n\n")[1] if "\n\n" in p else p[:300]
            sections.append(first_section + "\n")

    sections.append("## 三、设备选型方案\n")
    sections.append("设备选型遵循以下原则：\n")
    sections.append("1. 技术先进性：选用业界成熟、先进的技术设备\n")
    sections.append("2. 安全可靠性：满足国家相关安全标准，具备冗余设计\n")
    sections.append("3. 经济合理性：在满足技术要求的前提下控制成本\n")
    sections.append("4. 可扩展性：预留扩展空间，支持后续功能升级\n")
    sections.append("5. 兼容性：与现有系统良好兼容，减少对接成本\n")

    if len(relevant) > 2:
        sections.append("\n### 3.1 主要设备参考\n")
        # 从相关段落中提取设备信息
        for p in relevant[2:]:
            if "设备" in p[:100] or "参数" in p[:100]:
                lines = p.split("\n")
                for line in lines[:5]:
                    if line.strip():
                        sections.append(line + "\n")

    sections.append("## 四、技术保障措施\n")
    sections.append("1. **技术团队保障**：由资深技术专家牵头，组建专业技术团队\n")
    sections.append("2. **技术评审机制**：关键节点组织技术评审，确保方案可行性\n")
    sections.append("3. **技术支持响应**：提供7×24小时技术支持\n")
    sections.append("4. **技术培训**：为用户提供系统操作和维护培训\n")

    return "\n".join(sections)


def _build_fallback_project_understanding(project_desc: dict, paragraphs: Dict[str, str]) -> str:
    """使用素材库生成项目理解（兜底）"""
    project_name = project_desc.get("project_name", "本项目")
    description = project_desc.get("description", "")
    category = project_desc.get("category", "")

    sections = []
    sections.append(f"# 项目理解与分析 — {project_name}\n")
    sections.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    sections.append(f"生成方式：素材库模板（LLM API 不可用时的兜底方案）\n")

    sections.append("## 一、项目背景分析\n")
    sections.append(f"### 1.1 政策背景\n")
    sections.append("本项目符合国家数字化转型和产业升级的政策导向，顺应行业发展趋势。\n")
    sections.append("近年来，国家相继出台相关政策支持信息化建设，为本项目的实施提供了政策保障。\n")

    if category:
        sections.append(f"### 1.2 行业背景\n")
        sections.append(f"本项目属于「{category}」领域，该领域正处于快速发展阶段，市场需求旺盛。\n")

    sections.append("## 二、项目建设目标\n")
    sections.append("### 2.1 总体目标\n")
    sections.append(f"通过本项目的实施，建设一套技术先进、功能完善、安全可靠的系统，满足业务需求。\n")
    sections.append("### 2.2 分项目标\n")
    sections.append("1. 完成系统基础设施建设\n")
    sections.append("2. 实现核心业务功能\n")
    sections.append("3. 建立完善的管理和运维体系\n")
    sections.append("4. 确保系统安全稳定运行\n")

    sections.append("## 三、项目需求分析\n")
    if description:
        sections.append(f"### 3.1 项目概况\n")
        sections.append(f"{description}\n")

    sections.append("### 3.2 功能需求\n")
    sections.append("1. 核心业务功能：满足招标文件中的功能性要求\n")
    sections.append("2. 管理功能：提供完善的项目管理和数据统计功能\n")
    sections.append("3. 接口功能：支持与现有系统的对接\n")

    sections.append("### 3.3 技术需求\n")
    sections.append("1. 性能要求：满足高并发、大数据量的业务场景\n")
    sections.append("2. 安全要求：符合国家信息安全等级保护要求\n")
    sections.append("3. 可靠性要求：系统可用性不低于 99.9%\n")

    sections.append("## 四、项目难点与挑战\n")
    sections.append("1. **技术复杂性**：涉及多种技术栈的集成和对接\n")
    sections.append("2. **工期紧迫**：需要在有限时间内完成大量工作\n")
    sections.append("3. **质量要求高**：需要满足严格的行业标准和规范\n")
    sections.append("4. **协调难度大**：涉及多部门、多角色协同配合\n")

    sections.append("## 五、项目理解阐述\n")
    sections.append(f"通过对「{project_name}」的深入分析，我方充分理解项目的核心需求和建设目标。\n")
    sections.append("我方凭借丰富的行业经验和专业的技术实力，有信心高质量完成本项目。\n")

    sections.append("## 六、合理化建议\n")
    sections.append("1. **建议采用分阶段实施策略**：先完成核心功能，再逐步完善\n")
    sections.append("2. **建议建立定期沟通机制**：确保信息对称和问题及时解决\n")
    sections.append("3. **建议预留扩展空间**：为后续功能升级预留接口和资源\n")
    sections.append("4. **建议引入第三方检测**：确保系统质量和性能达标\n")

    return "\n".join(sections)


def _build_fallback_work_plan(milestones: list, duration: str, paragraphs: Dict[str, str]) -> str:
    """使用素材库生成工作规划（兜底）"""
    sections = []
    sections.append("# 工作规划与进度安排\n")
    sections.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    sections.append(f"生成方式：素材库模板（LLM API 不可用时的兜底方案）\n")

    sections.append(f"## 一、项目总体进度计划\n")
    sections.append(f"项目总工期：{duration}\n")

    if milestones:
        sections.append("\n### 1.1 里程碑节点\n")
        sections.append("| 序号 | 里程碑 | 计划完成时间 | 交付物 |\n")
        sections.append("|------|--------|-------------|--------|\n")
        for i, ms in enumerate(milestones, 1):
            name = ms if isinstance(ms, str) else ms.get("name", f"里程碑{i}")
            time = ms.get("time", "") if isinstance(ms, dict) else ""
            deliverable = ms.get("deliverable", "") if isinstance(ms, dict) else ""
            sections.append(f"| {i} | {name} | {time} | {deliverable} |\n")

    sections.append("\n## 二、工作分解结构（WBS）\n")
    phases = [
        ("第一阶段：需求分析与方案设计", "项目启动后第1-2周", "需求分析报告、技术方案"),
        ("第二阶段：设备采购与生产", "第3-5周", "设备采购合同、出厂检测报告"),
        ("第三阶段：系统部署与集成", "第5-8周", "部署报告、集成测试报告"),
        ("第四阶段：系统联调与优化", "第8-10周", "联调报告、性能测试报告"),
        ("第五阶段：培训与验收", "第10-12周", "培训记录、验收报告"),
    ]
    for phase, time, deliverable in phases:
        sections.append(f"### {phase}\n")
        sections.append(f"时间安排：{time}\n")
        sections.append(f"主要交付物：{deliverable}\n")

    sections.append("\n## 三、关键路径分析\n")
    sections.append("本项目的关键路径为：需求分析 → 设备采购 → 系统部署 → 联调测试 → 验收交付\n")
    sections.append("关键路径上的任何延误都会直接影响项目总体进度，须重点管控。\n")

    sections.append("\n## 四、资源配置计划\n")
    sections.append("### 4.1 人力资源\n")
    sections.append("| 角色 | 人数 | 投入阶段 |\n")
    sections.append("|------|------|----------|\n")
    sections.append("| 项目经理 | 1 | 全过程 |\n")
    sections.append("| 技术负责人 | 1 | 全过程 |\n")
    sections.append("| 实施工程师 | 2-4 | 第三、四阶段 |\n")
    sections.append("| 测试工程师 | 1 | 第四、五阶段 |\n")
    sections.append("| 售后工程师 | 1 | 第五阶段及后续 |\n")

    sections.append("\n## 五、进度保障措施\n")
    sections.append("1. **建立进度预警机制**：每周对比实际进度与计划进度，偏差超过5%时触发预警\n")
    sections.append("2. **制定纠偏预案**：当出现进度偏差时，立即启动纠偏措施（增加资源、加班赶工等）\n")
    sections.append("3. **定期进度报告**：每周提交项目进度报告，每月召开进度评审会\n")
    sections.append("4. **风险管理**：提前识别可能影响进度的风险因素，制定应对预案\n")

    return "\n".join(sections)


def _build_fallback_performance_guarantee(reqs: dict, paragraphs: Dict[str, str]) -> str:
    """使用素材库生成履约保障（兜底）"""
    relevant = find_relevant_paragraphs("performance_guarantee", paragraphs, max_count=5)

    sections = []
    sections.append("# 履约保障方案\n")
    sections.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    sections.append(f"生成方式：素材库模板（LLM API 不可用时的兜底方案）\n")

    # 质量保障
    sections.append("## 一、质量保障方案\n")
    sections.append("### 1.1 质量管理体系\n")
    sections.append("本项目建立以 ISO 9001:2015 质量管理体系标准为基础的质量管理体系，覆盖项目全过程。\n")

    if relevant:
        # 嵌入相关技术段落
        quality_paras = [p for p in relevant if "质量" in p[:50]]
        if quality_paras:
            sections.append(quality_paras[0].split("\n\n")[0] + "\n")

    sections.append("### 1.2 质量控制流程\n")
    sections.append("1. 严格执行“自检->互检->专检”三级检验制度\n")
    sections.append("2. 每道工序完成后必须经检验合格方可进入下道工序\n")
    sections.append("3. 关键节点邀请第三方检测机构参与验收\n")
    sections.append('4. 建立质量追溯制度，实行"谁施工、谁负责"\n')

    sections.append("\n### 1.3 质量检验标准\n")
    sections.append("所有设备材料均符合国家现行质量标准和行业标准，产品合格率100%。\n")
    sections.append("隐蔽工程施工完成后，主动通知监理和建设单位验收。\n")

    # 安全保障
    sections.append("\n## 二、安全保障方案\n")
    sections.append("### 2.1 安全管理体系\n")

    safety_paras = [p for p in relevant if "安全" in p[:50]] if relevant else []
    if safety_paras:
        sections.append(safety_paras[0].split("\n\n")[0] + "\n")

    sections.append("### 2.2 安全防护措施\n")
    sections.append("1. 建立健全安全生产责任制，项目经理为安全生产第一责任人\n")
    sections.append("2. 定期开展安全教育培训和应急演练\n")
    sections.append("3. 严格执行安全操作规程，杜绝违章指挥和违章作业\n")
    sections.append("4. 配备齐全的安全防护设施和劳动保护用品\n")

    sections.append("\n### 2.3 应急预案\n")
    sections.append("1. 编制项目专项应急预案，涵盖火灾、触电、高处坠落等常见事故\n")
    sections.append("2. 建立应急救援队伍，配备必要的救援物资和设备\n")
    sections.append("3. 定期组织应急演练，提高应急处置能力\n")

    # 进度保障
    sections.append("\n## 三、进度保障方案\n")
    sections.append("### 3.1 进度计划管理\n")
    sections.append("1. 制定详细的施工进度计划，明确关键路径\n")
    sections.append("2. 每周对比实际进度与计划进度，及时纠偏\n")
    sections.append("3. 关键节点设立进度里程碑，严格把控\n")

    sections.append("\n### 3.2 进度纠偏措施\n")
    sections.append("1. 当进度偏差超过5%时，立即启动纠偏预案\n")
    sections.append("2. 增加人力、物力资源投入，确保按期完成\n")
    sections.append("3. 优化施工组织方案，提高施工效率\n")

    # 资金与人员保障
    sections.append("\n## 四、资金保障方案\n")
    sections.append("1. 设立项目专项资金账户，确保资金专款专用\n")
    sections.append("2. 编制详细的资金使用计划，定期审核资金使用情况\n")
    sections.append("3. 建立资金使用审批制度，大额支出须项目经理审批\n")

    sections.append("\n## 五、人员保障方案\n")
    sections.append("1. 核心团队成员须全职投入本项目，不得兼任其他项目\n")
    sections.append("2. 建立人员替补机制，关键岗位须有后备人选\n")
    sections.append("3. 定期组织团队建设和技能培训，提高团队凝聚力\n")

    # 设备材料保障
    sections.append("\n## 六、设备材料保障方案\n")
    sections.append("1. 建立供应商评估和准入制度，选择优质供应商\n")
    sections.append("2. 关键设备材料须有备选供应商，避免供应中断\n")
    sections.append("3. 建立备品备件库，确保设备故障时能及时更换\n")

    # 履约承诺
    sections.append("\n## 七、履约承诺\n")
    sections.append("本公司郑重承诺：严格按照合同约定履行全部责任和义务，确保项目质量、安全、进度达到招标文件要求。\n")
    sections.append("如因本公司原因造成项目延误或质量不达标，本公司愿承担相应的违约责任和赔偿。\n")

    return "\n".join(sections)


def _build_fallback_service_commitment(reqs: dict, paragraphs: Dict[str, str]) -> str:
    """使用素材库生成服务承诺（兜底）"""
    commitment_tpls = load_all_commitment_templates()
    relevant = find_relevant_paragraphs("service_commitment", paragraphs, max_count=3)

    sections = []
    sections.append("# 服务承诺方案\n")
    sections.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    sections.append(f"生成方式：素材库模板（LLM API 不可用时的兜底方案）\n")

    # 售后服务承诺
    sections.append("## 一、售后服务承诺\n")
    if "05-after-sales-service-commitment.md" in commitment_tpls:
        tpl = commitment_tpls["05-after-sales-service-commitment.md"]
        # 取关键段落
        for line in tpl.split("\n"):
            if line.strip() and not line.startswith("#") and len(line.strip()) > 10:
                sections.append(line + "\n")
    else:
        sections.append("1. 质保期：自验收合格之日起 **12 个月**\n")
        sections.append("2. 响应时间：7×24小时响应，**2小时内远程响应**，**24小时内现场到达**\n")
        sections.append("3. 故障处理：一般故障 **4 小时内解决**，重大故障 **24 小时内提供备用方案**\n")
        sections.append("4. 定期巡检：每季度一次现场巡检，提交巡检报告\n")
        sections.append("5. 技术培训：免费技术培训 **2 次/年**，不定期技术交流\n")

    # 技术支持承诺
    sections.append("\n## 二、技术支持承诺\n")
    sections.append("1. 提供免费技术咨询服务，用户可通过电话、邮件、在线工单等方式随时联系\n")
    sections.append("2. 系统软件终身免费升级（同一大版本内）\n")
    sections.append("3. 重大技术问题，派遣高级技术专家现场支持\n")
    sections.append("4. 建立专属技术支持群，实现快速响应和沟通\n")

    # 质量保证承诺
    sections.append("\n## 三、质量保证承诺\n")
    if "01-quality-assurance-commitment.md" in commitment_tpls:
        tpl = commitment_tpls["01-quality-assurance-commitment.md"]
        sections.append(tpl[:1000] + "\n")
    else:
        sections.append("1. 所供全部设备、材料和服务均符合国家现行质量标准和行业标准\n")
        sections.append("2. 严格执行 ISO 9001:2015 质量管理体系\n")
        sections.append("3. 设备材料进场后配合开箱检验和见证取样复试\n")
        sections.append("4. 隐蔽工程施工完成后主动通知监理和建设单位验收\n")

    # 应急响应承诺
    sections.append("\n## 四、应急响应承诺\n")
    sections.append("1. 建立 7×24 小时应急响应机制\n")
    sections.append("2. 设立应急响应专线，确保第一时间接报\n")
    sections.append("3. 配备专职应急响应团队，随时待命\n")
    sections.append("4. 储备应急物资和备品备件，确保快速替换\n")
    sections.append("5. 重大故障 **2 小时内到达现场**，**8 小时内恢复系统运行**\n")

    # 持续服务承诺
    sections.append("\n## 五、持续服务承诺\n")
    sections.append("1. 质保期满后，提供优惠的续保服务方案\n")
    sections.append("2. 系统升级和功能扩展优先服务\n")
    sections.append("3. 定期回访用户，了解系统运行情况和使用需求\n")
    sections.append("4. 建立用户档案，跟踪系统全生命周期\n")

    # 违约赔偿承诺
    sections.append("\n## 六、违约赔偿承诺\n")
    sections.append("1. 如未能在承诺时间内响应，每延迟 1 小时，按合同金额的 **0.1%** 支付违约金\n")
    sections.append("2. 如因我方原因造成设备损坏或数据丢失，承担全部赔偿责任\n")
    sections.append("3. 质保期内因产品质量问题导致的损失，由我方全额赔偿\n")
    sections.append("4. 违约赔偿不影响我方继续履行合同义务\n")

    return "\n".join(sections)


# ==================== 主接口：5 个 AI 生成方法 ====================


def generate_technical_solution(requirements: dict) -> Dict[str, Any]:
    """
    生成技术方案：技术路线 + 实施方案 + 设备选型

    Args:
        requirements: {
            "project_name": str,       # 项目名称
            "technical_requirements": str,  # 技术要求
            "category": str,           # 项目类别
            "budget": float,           # 预算
            "custom_fields": dict,     # 自定义字段
        }

    Returns:
        {"status": "success", "content": str, "source": "llm"|"fallback"}
    """
    prompt_tpl = load_ai_prompt("01-技术方案生成")
    paragraphs = load_technical_paragraphs()

    # 提取 system prompt（从模板的 ``` 代码块中）
    system_match = re.search(r"```([\s\S]+?)```", prompt_tpl)
    system_prompt = system_match.group(1).strip() if system_match else (
        prompt_tpl[:500] if prompt_tpl else "你是一位拥有20年招投标经验的资深技术方案专家。"
    )

    # 构建 user prompt
    user_prompt = f"请为以下项目生成技术方案：\n\n"
    user_prompt += f"项目名称：{requirements.get('project_name', '未知项目')}\n"
    user_prompt += f"项目类别：{requirements.get('category', '')}\n"
    if requirements.get('technical_requirements'):
        user_prompt += f"技术要求：{requirements['technical_requirements']}\n"
    if requirements.get('budget'):
        user_prompt += f"项目预算：{requirements['budget']}\n"

    # 附加相关素材
    relevant = find_relevant_paragraphs("technical_solution", paragraphs, max_count=3)
    if relevant:
        user_prompt += "\n---\n参考素材：\n"
        for p in relevant:
            user_prompt += p[:500] + "\n---\n"

    # 尝试 LLM
    content = call_llm_api(system_prompt, user_prompt)
    if content:
        return {"status": "success", "content": content, "source": "llm"}

    # 兜底
    logger.info("技术方案生成：使用素材库兜底")
    fallback = _build_fallback_technical_solution(requirements, paragraphs)
    return {"status": "success", "content": fallback, "source": "fallback"}


def generate_project_understanding(project_desc: dict) -> Dict[str, Any]:
    """
    生成项目理解：背景分析 + 理解阐述

    Args:
        project_desc: {
            "project_name": str,
            "description": str,
            "category": str,
            "region": str,
        }

    Returns:
        {"status": "success", "content": str, "source": "llm"|"fallback"}
    """
    prompt_tpl = load_ai_prompt("02-项目理解生成")
    paragraphs = load_technical_paragraphs()

    system_match = re.search(r"```([\s\S]+?)```", prompt_tpl)
    system_prompt = system_match.group(1).strip() if system_match else (
        prompt_tpl[:500] if prompt_tpl else "你是一位资深招投标项目分析师。"
    )

    user_prompt = f"请为以下项目生成项目理解分析：\n\n"
    user_prompt += f"项目名称：{project_desc.get('project_name', '未知项目')}\n"
    if project_desc.get('description'):
        user_prompt += f"项目描述：{project_desc['description']}\n"
    if project_desc.get('category'):
        user_prompt += f"项目类别：{project_desc['category']}\n"
    if project_desc.get('region'):
        user_prompt += f"项目地点：{project_desc['region']}\n"

    content = call_llm_api(system_prompt, user_prompt)
    if content:
        return {"status": "success", "content": content, "source": "llm"}

    logger.info("项目理解生成：使用素材库兜底")
    fallback = _build_fallback_project_understanding(project_desc, paragraphs)
    return {"status": "success", "content": fallback, "source": "fallback"}


def generate_work_plan(milestones: list, duration: str) -> Dict[str, Any]:
    """
    生成工作规划：详细计划 + 时间节点

    Args:
        milestones: [{"name": str, "time": str, "deliverable": str}, ...]
        duration: str — 总工期（如 "12周"）

    Returns:
        {"status": "success", "content": str, "source": "llm"|"fallback"}
    """
    prompt_tpl = load_ai_prompt("03-工作规划生成")
    paragraphs = load_technical_paragraphs()

    system_match = re.search(r"```([\s\S]+?)```", prompt_tpl)
    system_prompt = system_match.group(1).strip() if system_match else (
        prompt_tpl[:500] if prompt_tpl else "你是一位拥有丰富项目管理经验的投标方案专家。"
    )

    user_prompt = f"请生成以下项目的工作规划：\n\n"
    user_prompt += f"项目总工期：{duration}\n"
    if milestones:
        user_prompt += f"\n里程碑节点：\n"
        for i, ms in enumerate(milestones, 1):
            name = ms if isinstance(ms, str) else ms.get("name", f"里程碑{i}")
            time = ms.get("time", "") if isinstance(ms, dict) else ""
            deliverable = ms.get("deliverable", "") if isinstance(ms, dict) else ""
            user_prompt += f"{i}. {name}（{time}）— {deliverable}\n"

    content = call_llm_api(system_prompt, user_prompt)
    if content:
        return {"status": "success", "content": content, "source": "llm"}

    logger.info("工作规划生成：使用素材库兜底")
    fallback = _build_fallback_work_plan(milestones, duration, paragraphs)
    return {"status": "success", "content": fallback, "source": "fallback"}


def generate_performance_guarantee(reqs: dict) -> Dict[str, Any]:
    """
    生成履约保障：质量 + 安全 + 进度

    Args:
        reqs: {
            "project_name": str,
            "quality_requirements": str,
            "safety_requirements": str,
            "schedule_requirements": str,
        }

    Returns:
        {"status": "success", "content": str, "source": "llm"|"fallback"}
    """
    prompt_tpl = load_ai_prompt("04-履约保障生成")
    paragraphs = load_technical_paragraphs()

    system_match = re.search(r"```([\s\S]+?)```", prompt_tpl)
    system_prompt = system_match.group(1).strip() if system_match else (
        prompt_tpl[:500] if prompt_tpl else "你是一位拥有丰富项目履约管理经验的投标方案专家。"
    )

    user_prompt = f"请为以下项目生成履约保障方案：\n\n"
    user_prompt += f"项目名称：{reqs.get('project_name', '未知项目')}\n"
    if reqs.get('quality_requirements'):
        user_prompt += f"质量要求：{reqs['quality_requirements']}\n"
    if reqs.get('safety_requirements'):
        user_prompt += f"安全要求：{reqs['safety_requirements']}\n"
    if reqs.get('schedule_requirements'):
        user_prompt += f"进度要求：{reqs['schedule_requirements']}\n"

    content = call_llm_api(system_prompt, user_prompt)
    if content:
        return {"status": "success", "content": content, "source": "llm"}

    logger.info("履约保障生成：使用素材库兜底")
    fallback = _build_fallback_performance_guarantee(reqs, paragraphs)
    return {"status": "success", "content": fallback, "source": "fallback"}


def generate_service_commitment(reqs: dict) -> Dict[str, Any]:
    """
    生成服务承诺：定制化承诺

    Args:
        reqs: {
            "project_name": str,
            "service_requirements": str,
            "warranty_period": str,
            "response_time": str,
        }

    Returns:
        {"status": "success", "content": str, "source": "llm"|"fallback"}
    """
    prompt_tpl = load_ai_prompt("05-服务承诺生成")
    paragraphs = load_technical_paragraphs()

    system_match = re.search(r"```([\s\S]+?)```", prompt_tpl)
    system_prompt = system_match.group(1).strip() if system_match else (
        prompt_tpl[:500] if prompt_tpl else "你是一位经验丰富的招投标服务方案专家。"
    )

    user_prompt = f"请为以下项目生成服务承诺方案：\n\n"
    user_prompt += f"项目名称：{reqs.get('project_name', '未知项目')}\n"
    if reqs.get('service_requirements'):
        user_prompt += f"服务要求：{reqs['service_requirements']}\n"
    if reqs.get('warranty_period'):
        user_prompt += f"质保期要求：{reqs['warranty_period']}\n"
    if reqs.get('response_time'):
        user_prompt += f"响应时间要求：{reqs['response_time']}\n"

    content = call_llm_api(system_prompt, user_prompt)
    if content:
        return {"status": "success", "content": content, "source": "llm"}

    logger.info("服务承诺生成：使用素材库兜底")
    fallback = _build_fallback_service_commitment(reqs, paragraphs)
    return {"status": "success", "content": fallback, "source": "fallback"}


# ==================== 全量批量生成 ====================

def generate_all(project_id: int, parsed_data: dict, get_db_connection,
                 modules: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    为指定项目触发 AI 生成（支持指定模块或全量生成）。

    Args:
        project_id: 项目 ID
        parsed_data: 项目解析数据（来自 bid_projects.parsed_data）
        get_db_connection: 数据库连接上下文管理器
        modules: 指定要生成的模块列表，None 则全量生成

    Returns:
        生成结果汇总
    """
    key_info = parsed_data.get("key_info", {})
    project_name = key_info.get("project_name", "") or parsed_data.get("title", "")

    all_module_names = [
        "technical_solution",
        "project_understanding",
        "work_plan",
        "performance_guarantee",
        "service_commitment",
    ]
    # 如果没有指定模块，则生成全部
    target_modules = modules if modules else all_module_names
    # 过滤无效模块
    target_modules = [m for m in target_modules if m in all_module_names]

    results = {}
    start_time = datetime.now()

    module_generators = {
        "technical_solution": lambda: generate_technical_solution({
            "project_name": project_name,
            "technical_requirements": key_info.get("technical_requirements", ""),
            "category": key_info.get("category", ""),
            "budget": key_info.get("budget"),
        }),
        "project_understanding": lambda: generate_project_understanding({
            "project_name": project_name,
            "description": key_info.get("description", ""),
            "category": key_info.get("category", ""),
            "region": key_info.get("region", ""),
        }),
        "work_plan": lambda: generate_work_plan(
            key_info.get("milestones", []),
            key_info.get("duration", "12周"),
        ),
        "performance_guarantee": lambda: generate_performance_guarantee({
            "project_name": project_name,
            "quality_requirements": key_info.get("quality_requirements", ""),
            "safety_requirements": key_info.get("safety_requirements", ""),
            "schedule_requirements": key_info.get("schedule_requirements", ""),
        }),
        "service_commitment": lambda: generate_service_commitment({
            "project_name": project_name,
            "service_requirements": key_info.get("service_requirements", ""),
            "warranty_period": key_info.get("warranty_period", ""),
            "response_time": key_info.get("response_time", ""),
        }),
    }

    for mod_name in target_modules:
        try:
            generator = module_generators.get(mod_name)
            if generator:
                results[mod_name] = generator()
            else:
                results[mod_name] = {"status": "error", "error": f"未知的生成模块: {mod_name}"}
        except Exception as e:
            results[mod_name] = {"status": "error", "error": str(e)}

    elapsed = (datetime.now() - start_time).total_seconds()

    # 统计
    success_count = sum(1 for v in results.values() if v.get("status") == "success")
    llm_count = sum(1 for v in results.values() if v.get("source") == "llm")
    fallback_count = sum(1 for v in results.values() if v.get("source") == "fallback")

    # 保存生成结果到数据库
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE bid_projects SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                ("ai_generated", project_id),
            )
            conn.commit()
            cursor.close()
    except Exception as e:
        logger.warning(f"更新项目状态失败: {e}")

    return {
        "project_id": project_id,
        "project_name": project_name,
        "status": "completed",
        "elapsed_seconds": round(elapsed, 2),
        "total_modules": len(results),
        "success_count": success_count,
        "llm_generated": llm_count,
        "fallback_generated": fallback_count,
        "results": {k: {"status": v["status"], "source": v.get("source"), "content_length": len(v.get("content", ""))} for k, v in results.items()},
    }


# ==================== 生成状态管理 ====================

# 内存存储生成状态（生产环境应使用 Redis/数据库）
_generation_states: Dict[str, Dict[str, Any]] = {}


def record_generation_start(project_id: int, modules: List[str]) -> str:
    """记录生成任务开始"""
    task_id = f"gen_{project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    _generation_states[task_id] = {
        "task_id": task_id,
        "project_id": project_id,
        "modules": modules,
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "results": {},
    }
    return task_id


def record_generation_complete(task_id: str, results: Dict[str, Any]):
    """记录生成任务完成"""
    if task_id in _generation_states:
        _generation_states[task_id].update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "results": results.get("results", {}),
            "elapsed_seconds": results.get("elapsed_seconds"),
        })


def get_generation_status(task_id: str) -> Optional[Dict[str, Any]]:
    """查询生成任务状态"""
    return _generation_states.get(task_id)


def list_generations(project_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """列出生成任务（可按项目 ID 过滤）"""
    tasks = list(_generation_states.values())
    if project_id is not None:
        tasks = [t for t in tasks if t.get("project_id") == project_id]
    tasks.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return tasks
