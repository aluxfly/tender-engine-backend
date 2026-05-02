#!/usr/bin/env python3
"""
标书 AI 生成系统 — Day 4 数据库迁移脚本
创建 bid_downloads 表（下载链接追踪）
"""

import os
import logging

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def get_db_connection():
    """获取数据库连接"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise RuntimeError("DATABASE_URL 环境变量未设置")
    conn = psycopg2.connect(db_url)
    return conn


def migrate():
    """执行迁移"""
    logger.info("连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查表是否已存在
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            ("bid_downloads",),
        )
        exists = cursor.fetchone()[0]

        if exists:
            logger.info("表 bid_downloads 已存在，跳过")
        else:
            logger.info("创建表 bid_downloads...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bid_downloads (
                    id SERIAL PRIMARY KEY,
                    download_token UUID NOT NULL UNIQUE,
                    project_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL DEFAULT 'docx',  -- docx 或 pdf
                    expires_at TIMESTAMP NOT NULL,
                    download_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_downloaded_at TIMESTAMP
                )
            """)
            conn.commit()
            logger.info("表 bid_downloads 创建成功")

        # 检查并添加缺失的列到已有表
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'bid_downloads'
        """)
        columns = [row[0] for row in cursor.fetchall()]

        add_cols = {
            "file_type": ("TEXT NOT NULL DEFAULT 'docx'", "bid_downloads"),
            "download_count": ("INTEGER DEFAULT 0", "bid_downloads"),
            "last_downloaded_at": ("TIMESTAMP", "bid_downloads"),
        }
        for col_name, (col_def, tbl_name) in add_cols.items():
            if col_name not in columns:
                logger.info(f"为 {tbl_name} 添加 {col_name} 字段...")
                cursor.execute(f"ALTER TABLE {tbl_name} ADD COLUMN {col_name} {col_def}")
                conn.commit()
                logger.info(f"{col_name} 字段添加成功")

        logger.info("✅ Day 4 迁移完成")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 迁移失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    migrate()
