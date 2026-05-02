"""
定时清理模块 - 自动清理过期上传文件
Day 3: 文件上传 + OCR 识别引擎

功能：
1. 清理 /tmp/bid-uploads/ 中超过 24 小时的文件
2. 在 lifespan 中注册定时任务（每 6 小时执行）

集成方式：
    from cleanup import start_cleanup_scheduler, stop_cleanup_scheduler

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ... 其他初始化 ...
        start_cleanup_scheduler()
        yield
        stop_cleanup_scheduler()
"""

import os
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

UPLOAD_BASE_DIR = Path("/tmp/bid-uploads")
FILE_TTL_SECONDS = 24 * 60 * 60  # 24 小时
CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60  # 每 6 小时执行一次

# APScheduler 实例
_scheduler = None


def cleanup_expired_files() -> dict:
    """
    清理 /tmp/bid-uploads/ 中超过 24 小时的文件。

    返回统计信息：
    {
        "cleaned_files": [...],
        "cleaned_dirs": [...],
        "total_freed_bytes": ...,
        "timestamp": "..."
    }
    """
    if not UPLOAD_BASE_DIR.exists():
        logger.info("上传目录不存在，无需清理")
        return {
            "cleaned_files": [],
            "cleaned_dirs": [],
            "total_freed_bytes": 0,
            "timestamp": datetime.now().isoformat(),
        }

    now = time.time()
    cutoff = now - FILE_TTL_SECONDS

    cleaned_files = []
    cleaned_dirs = []
    total_freed = 0

    # 遍历所有项目目录
    for project_dir in UPLOAD_BASE_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        dir_empty = True
        for file_path in project_dir.iterdir():
            if not file_path.is_file():
                continue

            dir_empty = False
            # 检查文件修改时间
            mtime = file_path.stat().st_mtime
            if mtime < cutoff:
                file_size = file_path.stat().st_size
                try:
                    file_path.unlink()
                    cleaned_files.append(str(file_path))
                    total_freed += file_size
                    logger.info(f"已清理过期文件: {file_path} ({file_size} bytes)")
                except Exception as e:
                    logger.error(f"清理文件失败 {file_path}: {e}")

        # 如果项目目录已空，删除目录
        if dir_empty:
            try:
                project_dir.rmdir()
                cleaned_dirs.append(str(project_dir))
                logger.info(f"已清理空目录: {project_dir}")
            except Exception as e:
                logger.error(f"清理目录失败 {project_dir}: {e}")

    result = {
        "cleaned_files": cleaned_files,
        "cleaned_dirs": cleaned_dirs,
        "total_freed_bytes": total_freed,
        "timestamp": datetime.now().isoformat(),
    }

    logger.info(
        f"清理完成: {len(cleaned_files)} 个文件, "
        f"{len(cleaned_dirs)} 个目录, "
        f"释放 {total_freed / 1024:.1f} KB"
    )

    return result


def cleanup_db_expired_records():
    """
    清理数据库中超过 24 小时的资料记录（同时删除物理文件）。
    """
    try:
        from main import get_db_connection, db_pool
        if not db_pool:
            return

        import psycopg2.extras
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # 查找超过 24 小时的记录
            cursor.execute(
                """
                SELECT id, file_path, created_at
                FROM bid_materials
                WHERE created_at < NOW() - INTERVAL '24 hours'
                """
            )
            rows = cursor.fetchall()

            deleted_count = 0
            for row in rows:
                file_path = row["file_path"]
                # 删除物理文件
                if file_path and Path(file_path).exists():
                    try:
                        Path(file_path).unlink()
                        logger.info(f"已清理过期文件: {file_path}")
                    except Exception as e:
                        logger.error(f"清理物理文件失败 {file_path}: {e}")

                # 删除数据库记录
                cursor.execute("DELETE FROM bid_materials WHERE id = %s", (row["id"],))
                deleted_count += 1

            if deleted_count > 0:
                conn.commit()
                logger.info(f"已清理 {deleted_count} 条过期数据库记录")

            cursor.close()

    except Exception as e:
        logger.error(f"数据库清理失败: {e}")


def start_cleanup_scheduler():
    """启动定时清理任务（每 6 小时执行一次）"""
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

        _scheduler = BackgroundScheduler(daemon=True)

        # 注册文件清理任务
        _scheduler.add_job(
            cleanup_expired_files,
            'interval',
            hours=6,
            id='cleanup_expired_files',
            name='清理过期上传文件',
            max_instances=1,
            replace_existing=True,
        )

        # 注册数据库记录清理任务
        _scheduler.add_job(
            cleanup_db_expired_records,
            'interval',
            hours=6,
            id='cleanup_db_records',
            name='清理过期数据库记录',
            max_instances=1,
            replace_existing=True,
        )

        # 立即执行一次初始清理
        logger.info("执行初始清理...")
        cleanup_expired_files()
        cleanup_db_expired_records()

        _scheduler.start()
        logger.info(f"定时清理任务已启动（间隔 {CLEANUP_INTERVAL_SECONDS // 3600} 小时）")

    except Exception as e:
        logger.error(f"启动清理任务失败: {e}")
        _scheduler = None


def stop_cleanup_scheduler():
    """停止定时清理任务"""
    global _scheduler
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("定时清理任务已停止")
        except Exception as e:
            logger.error(f"停止清理任务失败: {e}")
        _scheduler = None


# ==================== 导出 ====================

__all__ = [
    "cleanup_expired_files",
    "cleanup_db_expired_records",
    "start_cleanup_scheduler",
    "stop_cleanup_scheduler",
]
