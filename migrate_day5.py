#!/usr/bin/env python3
"""
Day 5 数据库迁移脚本
====================
1. 为 bid_projects 表添加索引（project_name, source, publish_date）
2. 为 tender_data / bid_notices 表添加索引
3. 添加 bid_analysis_logs 表（分析日志追踪）
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


def index_exists(cursor, index_name):
    """检查索引是否已存在"""
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = %s)",
        (index_name,),
    )
    return cursor.fetchone()[0]


def column_exists(cursor, table_name, column_name):
    """检查列是否已存在"""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
        """,
        (table_name, column_name),
    )
    return cursor.fetchone()[0]


def migrate():
    """执行迁移"""
    logger.info("连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ==================== 1. bid_projects 表索引 ====================
        logger.info("--- 检查 bid_projects 表索引 ---")

        # 检查 bid_projects 表是否存在
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            ("bid_projects",),
        )
        if not cursor.fetchone()[0]:
            logger.warning("bid_projects 表不存在，跳过索引创建")
        else:
            # project_name 索引（从 parsed_data JSON 中提取）
            idx_name = "idx_bid_projects_title"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_projects(title)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_projects(title)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # status 索引
            idx_name = "idx_bid_projects_status"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_projects(status)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_projects(status)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # created_at 索引
            idx_name = "idx_bid_projects_created_at"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_projects(created_at DESC)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_projects(created_at DESC)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # parsed_data 中 project_name 的表达式索引（PostgreSQL JSONB/GIN）
            idx_name = "idx_bid_projects_parsed_project_name"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建 GIN 索引: {idx_name} ON bid_projects(parsed_data)")
                cursor.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} "
                    f"ON bid_projects USING GIN (parsed_data jsonb_path_ops)"
                )
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

        # ==================== 2. bid_notices / tender_data 表索引 ====================
        logger.info("--- 检查 bid_notices 表索引 ---")

        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            ("bid_notices",),
        )
        if not cursor.fetchone()[0]:
            logger.warning("bid_notices 表不存在，跳过索引创建")
        else:
            # source_site 索引
            idx_name = "idx_bid_notices_source_site"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_notices(source_site)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_notices(source_site)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # publish_date 索引
            idx_name = "idx_bid_notices_publish_date"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_notices(publish_date DESC)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_notices(publish_date DESC)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # region 索引
            idx_name = "idx_bid_notices_region"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_notices(region)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_notices(region)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # crawl_time 索引
            idx_name = "idx_bid_notices_crawl_time"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建索引: {idx_name} ON bid_notices(crawl_time DESC)")
                cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON bid_notices(crawl_time DESC)")
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

            # 复合索引：source_site + publish_date（常用于按来源和时间的查询）
            idx_name = "idx_bid_notices_source_date"
            if not index_exists(cursor, idx_name):
                logger.info(f"创建复合索引: {idx_name} ON bid_notices(source_site, publish_date DESC)")
                cursor.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} "
                    f"ON bid_notices(source_site, publish_date DESC)"
                )
                conn.commit()
                logger.info(f"✅ {idx_name} 创建成功")
            else:
                logger.info(f"⏭️  {idx_name} 已存在")

        # ==================== 3. 创建 bid_analysis_logs 表 ====================
        logger.info("--- 检查 bid_analysis_logs 表 ---")

        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            ("bid_analysis_logs",),
        )
        if cursor.fetchone()[0]:
            logger.info("⏭️  bid_analysis_logs 表已存在")
        else:
            logger.info("创建 bid_analysis_logs 表...")
            cursor.execute("""
                CREATE TABLE bid_analysis_logs (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    analysis_type VARCHAR(50) NOT NULL,  -- disqualification_check, scoring_report, ai_generate
                    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- running, completed, failed
                    input_data JSONB,
                    output_data JSONB,
                    error_message TEXT,
                    duration_seconds FLOAT,
                    created_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logger.info("✅ bid_analysis_logs 表创建成功")

            # 为 bid_analysis_logs 添加索引
            idx_name = "idx_analysis_logs_project_id"
            cursor.execute(f"CREATE INDEX {idx_name} ON bid_analysis_logs(project_id)")
            conn.commit()
            logger.info(f"✅ {idx_name} 创建成功")

            idx_name = "idx_analysis_logs_type"
            cursor.execute(f"CREATE INDEX {idx_name} ON bid_analysis_logs(analysis_type)")
            conn.commit()
            logger.info(f"✅ {idx_name} 创建成功")

            idx_name = "idx_analysis_logs_created_at"
            cursor.execute(f"CREATE INDEX {idx_name} ON bid_analysis_logs(created_at DESC)")
            conn.commit()
            logger.info(f"✅ {idx_name} 创建成功")

        # ==================== 4. 添加缺失列到已有表 ====================
        logger.info("--- 检查已有表的缺失列 ---")

        # 检查 bid_projects 是否有 source 列
        if column_exists(cursor, "bid_projects", "source"):
            logger.info("⏭️  bid_projects.source 列已存在")
        else:
            logger.info("为 bid_projects 添加 source 列...")
            cursor.execute("ALTER TABLE bid_projects ADD COLUMN source VARCHAR(100) DEFAULT 'manual'")
            conn.commit()
            logger.info("✅ bid_projects.source 列添加成功")

        # 检查 bid_projects 是否有 publish_date 列
        if column_exists(cursor, "bid_projects", "publish_date"):
            logger.info("⏭️  bid_projects.publish_date 列已存在")
        else:
            logger.info("为 bid_projects 添加 publish_date 列...")
            cursor.execute("ALTER TABLE bid_projects ADD COLUMN publish_date TIMESTAMP")
            conn.commit()
            logger.info("✅ bid_projects.publish_date 列添加成功")

        logger.info("=" * 50)
        logger.info("✅ Day 5 数据库迁移完成")
        logger.info("=" * 50)

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 迁移失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    migrate()
