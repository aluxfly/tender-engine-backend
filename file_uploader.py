"""
文件上传模块 - 多格式补充资料上传
Day 3: 文件上传 + OCR 识别引擎

支持图片/PDF/Word/Excel 上传，文件类型白名单验证，大小限制 10MB。
存储到 /tmp/bid-uploads/{project_id}/，24 小时自动清理。

API 路由：
  POST   /api/bid/material/{project_id}      — 上传补充资料
  GET    /api/bid/materials/{project_id}      — 获取已上传资料列表
  DELETE /api/bid/material/{material_id}      — 删除资料
"""

import os
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

UPLOAD_BASE_DIR = Path("/tmp/bid-uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 文件类型白名单（扩展名 → MIME 类型）
ALLOWED_EXTENSIONS = {
    # 图片
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    # PDF
    ".pdf": "application/pdf",
    # Word
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Excel
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}

ALLOWED_EXT_LIST = list(ALLOWED_EXTENSIONS.keys())

# ==================== 路由 ====================

router = APIRouter(prefix="/api/bid", tags=["material"])


# ==================== 工具函数 ====================

def _get_project_dir(project_id: int) -> Path:
    """获取项目上传目录"""
    return UPLOAD_BASE_DIR / str(project_id)


def _validate_file(filename: str) -> tuple[str, str]:
    """
    验证文件类型，返回 (扩展名, MIME 类型)
    失败时抛出 HTTPException
    """
    if not filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，仅支持 {', '.join(ALLOWED_EXT_LIST)}"
        )
    return ext, ALLOWED_EXTENSIONS[ext]


def _check_file_size(content: bytes) -> None:
    """检查文件大小"""
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大 ({len(content) / 1024 / 1024:.1f}MB)，限制 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        )


def _save_file(content: bytes, project_id: int, original_name: str) -> tuple[Path, int]:
    """
    保存文件到 /tmp/bid-uploads/{project_id}/
    返回 (文件路径, 文件大小)
    """
    project_dir = _get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    # 使用时间戳 + 原始文件名确保唯一性
    timestamp = int(time.time() * 1000)
    ext = Path(original_name).suffix.lower()
    safe_name = f"{timestamp}_{Path(original_name).stem}{ext}"
    file_path = project_dir / safe_name

    file_path.write_bytes(content)
    return file_path, len(content)


# ==================== API 端点 ====================

@router.post("/material/{project_id}")
async def upload_material(
    project_id: int,
    file: UploadFile = File(...),
    material_type: Optional[str] = None,
    x_api_key: Optional[str] = None,
):
    """
    上传补充资料到指定项目。

    - 支持图片/PDF/Word/Excel
    - 文件大小限制 10MB
    - 存储到 /tmp/bid-uploads/{project_id}/
    """
    # 延迟导入（避免循环依赖）
    from main import verify_api_key, get_db_connection, db_pool, error_response

    # 验证 API Key
    verify_api_key(x_api_key)

    if not db_pool:
        return error_response(503, "数据库未连接", "DATABASE_URL 未设置")

    # 验证文件类型
    filename = file.filename or "unknown"
    ext, mime_type = _validate_file(filename)

    # 读取文件内容并检查大小
    content = await file.read()
    _check_file_size(content)

    try:
        # 保存文件
        file_path, file_size = _save_file(content, project_id, filename)
        logger.info(f"文件已保存: {file_path} ({file_size} bytes)")

        # 写入数据库
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bid_materials
                    (project_id, material_type, file_path, file_name, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, project_id, material_type, file_path, file_name,
                          status, created_at
                """,
                (
                    project_id,
                    material_type or ext.lstrip("."),
                    str(file_path),
                    filename,
                    "uploaded",
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            cursor.close()

        return {
            "status": "success",
            "message": "资料上传成功",
            "data": {
                "material_id": row[0],
                "project_id": row[1],
                "material_type": row[2],
                "file_path": row[3],
                "file_name": row[4],
                "file_size": file_size,
                "mime_type": mime_type,
                "status": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        return error_response(500, "文件上传失败", str(e))


@router.get("/materials/{project_id}")
def list_materials(
    project_id: int,
    x_api_key: Optional[str] = None,
):
    """
    获取指定项目的所有已上传资料列表。
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
                SELECT id, project_id, material_type, file_path, file_name,
                       extracted_data, status, created_at
                FROM bid_materials
                WHERE project_id = %s
                ORDER BY created_at DESC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
            cursor.close()

        materials = []
        for row in rows:
            material = dict(row)
            if material.get("created_at"):
                material["created_at"] = material["created_at"].isoformat()
            materials.append(material)

        return {
            "status": "success",
            "count": len(materials),
            "data": materials,
        }

    except Exception as e:
        logger.error(f"获取资料列表失败: {e}")
        return error_response(500, "获取资料列表失败", str(e))


@router.delete("/material/{material_id}")
def delete_material(
    material_id: int,
    x_api_key: Optional[str] = None,
):
    """
    删除指定资料（同时删除物理文件）。
    """
    from main import verify_api_key, get_db_connection, db_pool, error_response
    import psycopg2.extras

    verify_api_key(x_api_key)

    if not db_pool:
        return error_response(503, "数据库未连接", "DATABASE_URL 未设置")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # 查询资料信息
            cursor.execute(
                "SELECT id, file_path FROM bid_materials WHERE id = %s",
                (material_id,),
            )
            row = cursor.fetchone()

            if not row:
                cursor.close()
                return error_response(404, "资料不存在", f"资料 ID {material_id} 不存在")

            file_path = row["file_path"]

            # 删除数据库记录
            cursor.execute("DELETE FROM bid_materials WHERE id = %s", (material_id,))
            conn.commit()
            cursor.close()

        # 删除物理文件
        if file_path and Path(file_path).exists():
            Path(file_path).unlink()
            logger.info(f"已删除文件: {file_path}")

        return {
            "status": "success",
            "message": "资料删除成功",
            "data": {
                "material_id": material_id,
                "file_path": file_path,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除资料失败: {e}")
        return error_response(500, "删除资料失败", str(e))
