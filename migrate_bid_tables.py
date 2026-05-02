#!/usr/bin/env python3
"""
标书 AI 生成系统 — Day 1 数据库迁移脚本
创建 5 张核心表：bid_projects, bid_materials, bid_templates, bid_fill_status, company_profiles
"""

import os
import sys
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


TABLES = [
    {
        "name": "bid_projects",
        "ddl": """
            CREATE TABLE IF NOT EXISTS bid_projects (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                source_file_name TEXT,
                file_path TEXT,
                parsed_data JSONB DEFAULT '{}'::jsonb,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
    },
    {
        "name": "bid_materials",
        "ddl": """
            CREATE TABLE IF NOT EXISTS bid_materials (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES bid_projects(id) ON DELETE CASCADE,
                material_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                extracted_data JSONB DEFAULT '{}'::jsonb,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
    },
    {
        "name": "bid_templates",
        "ddl": """
            CREATE TABLE IF NOT EXISTS bid_templates (
                id SERIAL PRIMARY KEY,
                template_type TEXT NOT NULL,
                template_name TEXT NOT NULL,
                content JSONB NOT NULL,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
    },
    {
        "name": "bid_fill_status",
        "ddl": """
            CREATE TABLE IF NOT EXISTS bid_fill_status (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES bid_projects(id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                fill_status TEXT DEFAULT 'unfilled',
                fill_source TEXT,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
    },
    {
        "name": "company_profiles",
        "ddl": """
            CREATE TABLE IF NOT EXISTS company_profiles (
                id SERIAL PRIMARY KEY,
                company_name TEXT NOT NULL,
                credit_code TEXT UNIQUE,
                legal_representative TEXT,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                bank_info JSONB DEFAULT '{}'::jsonb,
                qualifications JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
    },
]


def migrate():
    """执行迁移"""
    logger.info("连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for table in TABLES:
            name = table["name"]
            ddl = table["ddl"]

            # 检查表是否已存在
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                (name,),
            )
            exists = cursor.fetchone()[0]

            if exists:
                logger.info(f"表 {name} 已存在，跳过")
            else:
                logger.info(f"创建表 {name}...")
                cursor.execute(ddl)
                conn.commit()
                logger.info(f"表 {name} 创建成功")

        # 迁移：为已存在的 company_profiles 添加 UNIQUE(credit_code) 约束
        cursor.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'company_profiles_credit_code_key'"
        )
        if not cursor.fetchone():
            logger.info("为 company_profiles 添加 UNIQUE(credit_code) 约束...")
            cursor.execute(
                "ALTER TABLE company_profiles ADD CONSTRAINT company_profiles_credit_code_key UNIQUE (credit_code)"
            )
            conn.commit()
            logger.info("UNIQUE(credit_code) 约束添加成功")
        else:
            logger.info("company_profiles UNIQUE(credit_code) 约束已存在")

        # 验证：列出所有新建表
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('bid_projects', 'bid_materials', 'bid_templates', 'bid_fill_status', 'company_profiles')
            ORDER BY table_name
            """
        )
        created = [row[0] for row in cursor.fetchall()]
        logger.info(f"✅ 迁移完成，已创建 {len(created)} 张表: {', '.join(created)}")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 迁移失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    migrate()
