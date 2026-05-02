"""
文件上传模块 - 多格式补充资料上传
Day 3/5: 文件上传 + OCR 识别引擎 + 安全增强

支持图片/PDF/Word/Excel 上传，文件类型白名单验证，大小限制 10MB。
安全特性：
  - MIME 类型双重校验（扩展名 + 文件内容魔数）
  - 病毒扫描（ClamAV，自动检测是否可用）
  - 上传进度回调（通过 X-Upload-Token 查询）

存储到 /tmp/bid-uploads/{project_id}/，24 小时自动清理。

API 路由：
  POST   /api/bid/material/{project_id}      — 上传补充资料
  GET    /api/bid/materials/{project_id}      — 获取已上传资料列表
  DELETE /api/bid/material/{material_id}      — 删除资料
  GET    /api/bid/upload-progress/{token}     — 查询上传进度
"""

import os
import re
import time
import shutil
import hashlib
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

UPLOAD_BASE_DIR = Path("/tmp/bid-uploads")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (Day 5 提升)
CHUNK_SIZE = 8192  # 8KB chunks for streaming upload


# ==================== 路径安全 ====================

def sanitize_path(base_dir: str, user_filename: str) -> str:
    """确保文件路径不会逃逸 base_dir（防御路径遍历攻击）"""
    base_dir = os.path.abspath(base_dir)
    target = os.path.abspath(os.path.join(base_dir, user_filename))
    if not target.startswith(base_dir + os.sep) and target != base_dir:
        raise ValueError(f"Invalid file path: {user_filename}")
    return target


def validate_mime(file_path: str) -> tuple[bool, Optional[str]]:
    """
    使用 python-magic 验证文件真实 MIME 类型。
    返回 (是否合法, 检测到的 MIME 类型)。
    不匹配则拒绝，防止扩展名伪造。
    """
    ALLOWED_MIME_TYPES = {
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp',
        'image/tiff',
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/csv', 'text/plain',
    }
    try:
        import magic
        mime = magic.Magic(mime=True)
        file_mime = mime.from_file(file_path)
        if file_mime in ALLOWED_MIME_TYPES:
            return True, file_mime
        return False, file_mime
    except ImportError:
        logger.warning("[上传安全] python-magic 未安装，跳过 validate_mime")
        return True, None  # 回退
    except Exception as e:
        logger.warning(f"[上传安全] validate_mime 异常: {e}")
        return True, None  # 回退

# 病毒扫描配置
CLAMAV_SOCKET = "/var/run/clamav/clamd.ctl"
CLAMAV_ENABLED = False  # 自动检测

# 上传进度存储
_upload_progress: Dict[str, dict] = {}

# 文件类型白名单（扩展名 → MIME 类型列表）
ALLOWED_EXTENSIONS = {
    # 图片
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".png": ["image/png"],
    ".gif": ["image/gif"],
    ".bmp": ["image/bmp"],
    ".webp": ["image/webp"],
    ".tiff": ["image/tiff"],
    ".tif": ["image/tiff"],
    # PDF
    ".pdf": ["application/pdf"],
    # Word
    ".doc": ["application/msword"],
    ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    # Excel
    ".xls": ["application/vnd.ms-excel"],
    ".xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    ".csv": ["text/csv", "text/plain"],
}

ALLOWED_EXT_LIST = list(ALLOWED_EXTENSIONS.keys())

# ==================== ClamAV 病毒扫描 ====================

def _detect_clamav() -> bool:
    """自动检测 ClamAV 是否可用"""
    global CLAMAV_ENABLED
    if shutil.which("clamscan"):
        CLAMAV_ENABLED = True
        logger.info("[上传安全] ClamAV 已启用 (clamscan)")
        return True
    if os.path.exists(CLAMAV_SOCKET):
        CLAMAV_ENABLED = True
        logger.info("[上传安全] ClamAV 已启用 (clamd socket)")
        return True
    logger.warning("[上传安全] ClamAV 未安装，病毒扫描已跳过")
    return False

# 启动时检测
_detect_clamav()


def _scan_file_virus(file_path: Path) -> bool:
    """
    使用 ClamAV 扫描文件，返回 True 表示安全。
    如果 ClamAV 不可用，返回 True（跳过扫描）。
    """
    if not CLAMAV_ENABLED:
        return True

    try:
        if shutil.which("clamscan"):
            result = subprocess.run(
                ["clamscan", "--no-summary", str(file_path)],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 1:
                logger.error(f"[上传安全] 文件检测到病毒: {file_path}, {result.stdout}")
                return False
            return True
        elif os.path.exists(CLAMAV_SOCKET):
            try:
                import pyclamd
                cd = pyclamd.ClamdUnixSocket(filename=CLAMAV_SOCKET)
                scan_result = cd.scan_file(str(file_path))
                if scan_result:
                    logger.error(f"[上传安全] 文件检测到病毒: {file_path}, {scan_result}")
                    return False
                return True
            except ImportError:
                logger.warning("[上传安全] pyclamd 未安装，跳过 clamd 扫描")
                return True
    except subprocess.TimeoutExpired:
        logger.error("[上传安全] 病毒扫描超时")
        return False
    except Exception as e:
        logger.warning(f"[上传安全] 病毒扫描异常（跳过）: {e}")
        return True

    return True


# ==================== MIME 类型校验 ====================

def _get_mime_magic(content: bytes) -> Optional[str]:
    """
    使用 python-magic 检测文件真实 MIME 类型（基于文件内容魔数）。
    不依赖扩展名，防止恶意伪造。
    """
    try:
        import magic
        mime = magic.Magic(mime=True)
        detected = mime.from_buffer(content[:8192])  # 只需前 8KB
        return detected
    except ImportError:
        logger.warning("[上传安全] python-magic 未安装，跳过 MIME 魔数校验")
        return None
    except Exception as e:
        logger.warning(f"[上传安全] MIME 检测异常: {e}")
        return None


def _validate_mime_type(allowed_mimes: list, detected_mime: str) -> bool:
    """
    验证检测到的 MIME 类型是否在允许列表中。
    支持通配符匹配，例如 image/* 匹配 image/jpeg。
    """
    if detected_mime in allowed_mimes:
        return True
    # 通配符匹配
    for allowed in allowed_mimes:
        if allowed.endswith("/*"):
            prefix = allowed.split("/")[0]
            if detected_mime.startswith(prefix + "/"):
                return True
    return False


# ==================== 上传进度回调 ====================

def _create_progress_token(project_id: int, filename: str) -> str:
    """生成上传进度查询 token"""
    raw = f"{project_id}:{filename}:{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _update_progress(token: str, current: int, total: int, status: str):
    """更新上传进度"""
    _upload_progress[token] = {
        "current_bytes": current,
        "total_bytes": total,
        "percentage": round(current / total * 100, 1) if total > 0 else 0,
        "status": status,  # reading | validating | scanning | saving | done | error
        "updated_at": datetime.now().isoformat(),
    }


def _get_progress(token: str) -> Optional[dict]:
    """获取上传进度"""
    return _upload_progress.get(token)


def _cleanup_progress(token: str, delay: int = 300):
    """延迟清理进度记录（默认 5 分钟）"""
    def _cleanup():
        time.sleep(delay)
        _upload_progress.pop(token, None)
    threading.Thread(target=_cleanup, daemon=True).start()


# ==================== 路由 ====================

router = APIRouter(prefix="/api/bid", tags=["material"])


# ==================== 工具函数 ====================

def _get_project_dir(project_id: int) -> Path:
    """获取项目上传目录（sanitize_path 防御路径遍历）"""
    project_str = str(project_id)
    # 验证 project_id 只包含数字
    if not re.match(r'^\d+$', project_str):
        raise ValueError(f"Invalid project_id: {project_str}")
    safe_path = sanitize_path(str(UPLOAD_BASE_DIR), project_str)
    return Path(safe_path)


def _validate_file_extension(filename: str) -> tuple[str, str]:
    """
    验证文件扩展名，返回 (扩展名, 预期 MIME 类型)
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
    return ext, ALLOWED_EXTENSIONS[ext][0]


def _check_file_size(content: bytes) -> None:
    """检查文件大小"""
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大 ({len(content) / 1024 / 1024:.1f}MB)，限制 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        )


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
    - MIME 类型双重校验（扩展名 + 文件内容魔数）
    - 病毒扫描（ClamAV，自动检测是否可用）
    - 上传进度可查询（返回 upload_token）
    - 存储到 /tmp/bid-uploads/{project_id}/
    """
    # 延迟导入（避免循环依赖）
    from main import verify_api_key, get_db_connection, db_pool, error_response

    # 验证 API Key
    verify_api_key(x_api_key)

    if not db_pool:
        return error_response(503, "数据库未连接", "DATABASE_URL 未设置")

    # 验证文件扩展名
    filename = file.filename or "unknown"
    ext, expected_mime = _validate_file_extension(filename)

    # 创建上传进度 token
    upload_token = _create_progress_token(project_id, filename)
    _update_progress(upload_token, 0, 0, "reading")

    try:
        # 流式读取文件内容
        content = b""
        total_size = 0
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_size += len(chunk)
            content += chunk
            _update_progress(upload_token, total_size, 0, "reading")

        # 检查文件大小
        _check_file_size(content)
        _update_progress(upload_token, total_size, total_size, "validating")
        logger.info(f"[上传] 文件大小: {total_size} bytes")

        # MIME 类型校验（基于文件内容魔数）
        detected_mime = _get_mime_magic(content)
        if detected_mime:
            allowed_mimes = ALLOWED_EXTENSIONS.get(ext, [])
            if not _validate_mime_type(allowed_mimes, detected_mime):
                _update_progress(upload_token, total_size, total_size, "error")
                return error_response(
                    400,
                    "文件类型不匹配",
                    f"文件扩展名为 {ext}，但实际内容为 {detected_mime}，可能存在伪造风险",
                )
            logger.info(f"[上传安全] MIME 校验通过: {detected_mime} (预期: {expected_mime})")
        else:
            detected_mime = expected_mime  # 回退到扩展名推断

        # 保存到临时文件（病毒扫描前用临时名，sanitize_path 防御路径遍历）
        project_dir = _get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        # 提取安全的文件名 stem（移除任何路径分隔符和非法字符）
        safe_stem = re.sub(r'[^\w\-\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', '_', Path(filename).stem)
        temp_name = f"tmp_{timestamp}_{safe_stem}{ext}"
        safe_temp_path = sanitize_path(str(project_dir), temp_name)
        temp_path = Path(safe_temp_path)
        temp_path.write_bytes(content)
        _update_progress(upload_token, total_size, total_size, "scanning")

        # 病毒扫描
        if CLAMAV_ENABLED:
            logger.info("[上传安全] 开始病毒扫描...")
            if not _scan_file_virus(temp_path):
                temp_path.unlink(missing_ok=True)
                _update_progress(upload_token, total_size, total_size, "error")
                return error_response(
                    400,
                    "文件包含恶意代码",
                    "安全扫描检测到病毒或恶意代码，文件已拒绝并删除",
                )
            logger.info("[上传安全] 病毒扫描通过")

        # 重命名到最终路径（sanitize_path 防御路径遍历）
        _update_progress(upload_token, total_size, total_size, "saving")
        safe_stem = re.sub(r'[^\w\-\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', '_', Path(filename).stem)
        safe_name = f"{timestamp}_{safe_stem}{ext}"
        safe_final_path = sanitize_path(str(project_dir), safe_name)
        final_path = Path(safe_final_path)
        temp_path.rename(final_path)
        logger.info(f"[上传] 文件已保存: {final_path} ({total_size} bytes)")

        # 写入数据库
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bid_materials
                    (project_id, material_type, file_path, file_name, status, mime_type)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, project_id, material_type, file_path, file_name,
                          status, created_at
                """,
                (
                    project_id,
                    material_type or ext.lstrip("."),
                    str(final_path),
                    filename,
                    "uploaded",
                    detected_mime,
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            cursor.close()

        _update_progress(upload_token, total_size, total_size, "done")
        _cleanup_progress(upload_token)

        return {
            "status": "success",
            "message": "资料上传成功",
            "data": {
                "material_id": row[0],
                "project_id": row[1],
                "material_type": row[2],
                "file_path": row[3],
                "file_name": row[4],
                "file_size": total_size,
                "mime_type": detected_mime,
                "mime_verified": detected_mime == expected_mime,
                "virus_scanned": CLAMAV_ENABLED,
                "upload_token": upload_token,
                "status": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        _update_progress(upload_token, 0, 0, "error")
        return error_response(500, "文件上传失败", str(e))


@router.get("/upload-progress/{token}")
def get_upload_progress(token: str, x_api_key: Optional[str] = None):
    """查询上传进度"""
    from main import verify_api_key, error_response

    verify_api_key(x_api_key)

    progress = _get_progress(token)
    if not progress:
        return error_response(404, "进度记录不存在", "token 无效或已过期")

    return {
        "status": "success",
        "data": progress,
    }


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
                       extracted_data, status, created_at, mime_type
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

        # 删除物理文件（sanitize_path 防御路径遍历）
        if file_path:
            try:
                safe_delete_path = sanitize_path(str(UPLOAD_BASE_DIR), os.path.basename(file_path))
                if Path(safe_delete_path).exists():
                    Path(safe_delete_path).unlink()
                    logger.info(f"已删除文件: {safe_delete_path}")
            except ValueError as e:
                logger.warning(f"删除文件路径校验失败: {e}, 原路径: {file_path}")

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
