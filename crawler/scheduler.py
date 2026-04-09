#!/usr/bin/env python3
"""
爬虫定时任务调度器
每天自动执行爬虫任务
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from pathlib import Path
from datetime import datetime
import sys

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.gov_crawler import crawl_all

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_crawl_job():
    """执行爬虫任务"""
    logger.info(f"\n{'='*60}")
    logger.info(f"定时任务触发 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'='*60}\n")
    
    try:
        results = crawl_all()
        
        logger.info(f"\n任务执行结果:")
        logger.info(f"  - 政府采购网：{results['ccgp']} 条")
        logger.info(f"  - 国家电网：{results['sgcc']} 条")
        logger.info(f"  - 新增记录：{results['total_new']} 条")
        logger.info(f"  - 执行时间：{results['timestamp']}")
        
    except Exception as e:
        logger.error(f"爬虫任务执行失败：{e}", exc_info=True)
    
    logger.info(f"\n{'='*60}\n")


def main():
    """启动调度器"""
    logger.info("启动爬虫调度器...")
    logger.info(" scheduled: 每天 06:00 自动执行")
    
    scheduler = BlockingScheduler()
    
    # 每天早晨 6 点执行
    scheduler.add_job(
        run_crawl_job,
        CronTrigger(hour=6, minute=0),
        id='daily_crawl',
        name='每日招标公告抓取'
    )
    
    # 启动时立即执行一次
    logger.info("执行首次抓取...")
    run_crawl_job()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器停止")


if __name__ == '__main__':
    main()
