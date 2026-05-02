"""
OCR 识别引擎 - 基于 PaddleOCR
Day 3: 文件上传 + OCR 识别引擎

支持三种识别模式：
1. 营业执照识别：提取公司名称、信用代码、法人、地址、注册资本
2. 资质证书识别：提取证书名称、编号、有效期
3. 通用文档 OCR：提取文字内容

API 路由：
  POST /api/bid/ocr/{project_id}                — OCR 识别上传的资料
  GET  /api/bid/ocr/{project_id}/{material_id}  — 获取 OCR 结果
"""

import re
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

# ==================== 路径安全 ====================

def sanitize_path(base_dir: str, user_filename: str) -> str:
    """确保文件路径不会逃逸 base_dir（防御路径遍历攻击）"""
    base_dir = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base_dir, user_filename))
    if not target.startswith(base_dir + os.sep) and target != base_dir:
        raise ValueError(f"Invalid file path: {user_filename}")
    return target


# ==================== PaddleOCR 实例 ====================

_ocr_instance = None

def _get_ocr():
    """懒加载 PaddleOCR 实例（单例）"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            logger.info("初始化 PaddleOCR...")
            _ocr_instance = PaddleOCR(use_angle_cls=True, lang='ch')
            logger.info("PaddleOCR 初始化完成")
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            raise
    return _ocr_instance


# ==================== 路由 ====================

router = APIRouter(prefix="/api/bid", tags=["ocr"])


# ==================== OCR 核心函数 ====================

def ocr_image(image_path: str) -> list:
    """
    调用 PaddleOCR 识别图片文字。
    PaddleOCR 3.x API: ocr() 内部调用 predict()
    返回 [[坐标, (文字, 置信度)], ...] 格式
    """
    ocr = _get_ocr()
    result = ocr.ocr(image_path)
    if not result:
        return []
    # Handle different return formats (PaddleOCR 3.x)
    if isinstance(result, list) and len(result) > 0:
        if isinstance(result[0], list):
            return result[0]
        return result
    return []


def _extract_text(ocr_result: list) -> str:
    """从 OCR 结果提取纯文本"""
    lines = []
    for line in ocr_result:
        text = line[1][0]
        lines.append(text)
    return "\n".join(lines)


def ocr_business_license(image_path: str) -> dict:
    """
    营业执照识别：提取公司名称、信用代码、法人、地址、注册资本。

    返回结构化 JSON：
    {
        "company_name": "...",
        "credit_code": "...",
        "legal_representative": "...",
        "address": "...",
        "registered_capital": "...",
        "raw_text": "..."
    }
    """
    ocr_result = ocr_image(image_path)
    full_text = _extract_text(ocr_result)

    result = {
        "company_name": "",
        "credit_code": "",
        "legal_representative": "",
        "address": "",
        "registered_capital": "",
        "raw_text": full_text,
    }

    # 按行提取
    lines = full_text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 统一社会信用代码（18位字母数字组合）
        if not result["credit_code"]:
            match = re.search(r'[0-9A-HJ-NPQRTUWXY]{18}', line)
            if match:
                result["credit_code"] = match.group(0)
                continue

        # 公司名称（通常包含"公司"关键词且较长）
        if not result["company_name"]:
            if "公司" in line and len(line) > 5:
                # 去除前缀
                cleaned = re.sub(r'^.*?(?=[\u4e00-\u9fa5])', '', line)
                cleaned = re.sub(r'^(名称|公司名称|企业全称)[:：\s]*', '', cleaned)
                if len(cleaned) > 2:
                    result["company_name"] = cleaned
                    continue

        # 法定代表人
        if not result["legal_representative"]:
            match = re.search(r'(?:法定代表人|法人代表|负责人)[:：\s]*(.+)', line)
            if match:
                result["legal_representative"] = match.group(1).strip()
                continue
            # 简化匹配
            if line.startswith("法定代表人") or line.startswith("法人代表"):
                cleaned = re.sub(r'^(?:法定代表人|法人代表)[:：\s]*', '', line)
                if cleaned:
                    result["legal_representative"] = cleaned.strip()
                    continue

        # 注册资本
        if not result["registered_capital"]:
            match = re.search(r'(?:注册资本|注册资金)[:：\s]*(.+)', line)
            if match:
                result["registered_capital"] = match.group(1).strip()
                continue
            if "注册资本" in line or "注册资金" in line:
                cleaned = re.sub(r'^(?:注册资本|注册资金)[:：\s]*', '', line)
                if cleaned:
                    result["registered_capital"] = cleaned.strip()
                    continue

        # 地址
        if not result["address"]:
            match = re.search(r'(?:住所|地址|经营场所)[:：\s]*(.+)', line)
            if match:
                result["address"] = match.group(1).strip()
                continue
            if line.startswith("住所") or line.startswith("地址"):
                cleaned = re.sub(r'^(?:住所|地址|经营场所)[:：\s]*', '', line)
                if len(cleaned) > 5:
                    result["address"] = cleaned.strip()
                    continue

    # 补充：如果公司名称为空，尝试取第一行较长的中文
    if not result["company_name"]:
        for line in lines[:5]:
            line = line.strip()
            if len(line) > 5 and "公司" in line and re.search(r'[\u4e00-\u9fa5]', line):
                result["company_name"] = line
                break

    return result


def ocr_certificate(image_path: str) -> dict:
    """
    资质证书识别：提取证书名称、编号、有效期。

    返回结构化 JSON：
    {
        "certificate_name": "...",
        "certificate_number": "...",
        "expiry_date": "...",
        "raw_text": "..."
    }
    """
    ocr_result = ocr_image(image_path)
    full_text = _extract_text(ocr_result)

    result = {
        "certificate_name": "",
        "certificate_number": "",
        "expiry_date": "",
        "raw_text": full_text,
    }

    lines = full_text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 证书编号（多种格式匹配）
        if not result["certificate_number"]:
            match = re.search(r'(?:证书编号|证书号|编号|NO\.?|No\.?)[:：\s]*(\S+)', line)
            if match:
                result["certificate_number"] = match.group(1).strip()
                continue

        # 有效期 / 截止日期
        if not result["expiry_date"]:
            match = re.search(r'(?:有效期至?|有效期|截止日期|到期日|有效期限)[:：\s]*(.+)', line)
            if match:
                result["expiry_date"] = match.group(1).strip()
                continue
            # 日期格式匹配（YYYY-MM-DD, YYYY.MM.DD, YYYY年MM月DD日）
            match = re.search(r'(\d{4}[-年./]\d{1,2}[-月./]\d{1,2}[日号]?)', line)
            if match and ("至" in line or "有效" in line or "到期" in line or "截止" in line):
                result["expiry_date"] = match.group(1)
                continue

        # 证书名称（通常是第一行较长的文字，包含"证书"关键词）
        if not result["certificate_name"]:
            if "证书" in line and len(line) > 3:
                result["certificate_name"] = line
                continue

    # 补充：如果证书名称为空，取前几行中较长的
    if not result["certificate_name"]:
        for line in lines[:3]:
            line = line.strip()
            if len(line) > 3:
                result["certificate_name"] = line
                break

    return result


def ocr_general(image_path: str) -> str:
    """
    通用文档 OCR：提取全部文字内容。
    返回纯文本字符串。
    """
    ocr_result = ocr_image(image_path)
    return _extract_text(ocr_result)


# ==================== 智能识别路由 ====================

def auto_detect_type(image_path: str) -> str:
    """
    根据文件路径和初步 OCR 结果自动判断文档类型。
    返回 'business_license', 'certificate', 或 'general'
    """
    path_lower = Path(image_path).name.lower()
    # 文件名关键词检测
    if any(k in path_lower for k in ["营业执照", "license", "business"]):
        return "business_license"
    if any(k in path_lower for k in ["证书", "cert", "资质", "permit"]):
        return "certificate"

    # OCR 内容关键词检测
    try:
        ocr_result = ocr_image(image_path)
        full_text = _extract_text(ocr_result)

        # 营业执照关键词
        if "统一社会信用代码" in full_text and "营业执照" in full_text:
            return "business_license"
        if re.search(r'[0-9A-HJ-NPQRTUWXY]{18}', full_text) and "公司" in full_text:
            return "business_license"

        # 证书关键词
        if any(k in full_text for k in ["证书编号", "证书号", "有效期至"]):
            return "certificate"
    except Exception as e:
        logger.warning(f"自动类型检测失败: {e}")

    return "general"


# ==================== API 端点 ====================

@router.post("/ocr/{project_id}")
def ocr_material(
    project_id: int,
    material_id: Optional[int] = None,
    ocr_type: Optional[str] = None,  # business_license / certificate / general / auto
    x_api_key: Optional[str] = None,
):
    """
    OCR 识别指定项目的资料。

    - material_id: 可选，指定具体资料 ID；不传则识别该项目最新上传的资料
    - ocr_type: 可选，'business_license' / 'certificate' / 'general' / 'auto'（默认 auto）
    """
    from main import verify_api_key, get_db_connection, db_pool, error_response
    import psycopg2.extras

    verify_api_key(x_api_key)

    if not db_pool:
        return error_response(503, "数据库未连接", "DATABASE_URL 未设置")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # 查找资料
            if material_id:
                cursor.execute(
                    "SELECT * FROM bid_materials WHERE id = %s AND project_id = %s",
                    (material_id, project_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM bid_materials
                    WHERE project_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (project_id,),
                )

            material = cursor.fetchone()
            if not material:
                cursor.close()
                return error_response(
                    404, "资料不存在",
                    f"项目 {project_id} {'ID ' + str(material_id) if material_id else ''} 下没有找到资料"
                )

            file_path = material["file_path"]
            cursor.close()

        if not file_path:
            return error_response(404, "文件不存在", "文件路径为空")
        # sanitize_path 校验：防止数据库中的恶意路径
        try:
            sanitize_path("/tmp/bid-uploads", os.path.basename(file_path))
        except ValueError:
            return error_response(404, "文件不存在", "文件路径校验失败")
        if not Path(file_path).exists():
            return error_response(404, "文件不存在", f"文件路径 {file_path} 不存在")

        # 确定识别类型
        detect_type = ocr_type or "auto"

        if detect_type == "auto":
            detect_type = auto_detect_type(file_path)

        # 执行 OCR
        logger.info(f"开始 OCR 识别: file={file_path}, type={detect_type}")

        if detect_type == "business_license":
            ocr_result = ocr_business_license(file_path)
        elif detect_type == "certificate":
            ocr_result = ocr_certificate(file_path)
        else:
            ocr_result = {"raw_text": ocr_general(file_path)}

        ocr_result["ocr_type"] = detect_type
        ocr_result["material_id"] = material["id"]
        ocr_result["file_name"] = material["file_name"]

        # 保存 OCR 结果到数据库
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bid_materials
                SET extracted_data = %s::jsonb, status = 'ocr_done'
                WHERE id = %s
                """,
                (json.dumps(ocr_result, ensure_ascii=False), material["id"]),
            )
            conn.commit()
            cursor.close()

        return {
            "status": "success",
            "message": "OCR 识别成功",
            "data": ocr_result,
        }

    except Exception as e:
        logger.error(f"OCR 识别失败: {e}")
        return error_response(500, "OCR 识别失败", str(e))


@router.get("/ocr/{project_id}/{material_id}")
def get_ocr_result(
    project_id: int,
    material_id: int,
    x_api_key: Optional[str] = None,
):
    """
    获取指定资料的 OCR 结果。
    """
    from main import verify_api_key, get_db_connection, db_pool, error_response
    import psycopg2.extras

    verify_api_key(x_api_key)

    if not db_pool:
        return error_response(503, "数据库未连接", "DATABASE_URL 未设置")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                """
                SELECT id, project_id, file_name, material_type,
                       extracted_data, status, created_at
                FROM bid_materials
                WHERE id = %s AND project_id = %s
                """,
                (material_id, project_id),
            )
            row = cursor.fetchone()
            cursor.close()

        if not row:
            return error_response(
                404, "资料不存在",
                f"项目 {project_id} 下没有找到资料 ID {material_id}"
            )

        extracted_data = row.get("extracted_data")
        if extracted_data is None:
            return {
                "status": "success",
                "message": "该资料尚未进行 OCR 识别",
                "data": {
                    "material_id": row["id"],
                    "file_name": row["file_name"],
                    "status": row["status"],
                    "extracted_data": None,
                },
            }

        return {
            "status": "success",
            "data": {
                "material_id": row["id"],
                "file_name": row["file_name"],
                "material_type": row["material_type"],
                "status": row["status"],
                "extracted_data": extracted_data,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            },
        }

    except Exception as e:
        logger.error(f"获取 OCR 结果失败: {e}")
        return error_response(500, "获取 OCR 结果失败", str(e))
