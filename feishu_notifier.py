"""
飞书推送通知引擎 — Day 4

标书生成完成后自动推送飞书消息，包含：
- 项目名称
- 完成时间
- 废标项检查结果（通过/不通过）
- 预估得分
- 下载链接

Webhook URL 默认从环境变量 FEISHU_WEBHOOK_URL 读取
"""

import logging
import json
import os
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def notify_completion(project_id: int, webhook_url: str = None,
                      get_db_connection=None, base_url: str = None) -> bool:
    """
    推送标书完成通知到飞书

    Args:
        project_id: 标书项目 ID
        webhook_url: 飞书 Webhook URL（默认从环境变量 FEISHU_WEBHOOK_URL 读取）
        get_db_connection: 数据库连接获取函数
        base_url: 基础 URL（用于生成下载链接）

    Returns:
        bool: 是否推送成功
    """
    if get_db_connection is None:
        raise ValueError("get_db_connection 参数不能为空")

    # 获取 webhook URL
    if not webhook_url:
        webhook_url = os.environ.get("FEISHU_WEBHOOK_URL")
        if not webhook_url:
            logger.warning("飞书 Webhook URL 未配置，跳过通知")
            return False

    # 获取项目信息
    project_info = _get_project_info(project_id, get_db_connection)
    if project_info is None:
        logger.error(f"无法获取项目 ID {project_id} 的信息，无法发送通知")
        return False

    # 获取废标检查结果
    dq_passed = None
    dq_failed_count = 0
    try:
        from disqualification_checker import check_disqualification
        dq_result = check_disqualification(project_id, get_db_connection=get_db_connection)
        dq_passed = dq_result.get("passed", False)
        dq_failed_count = dq_result.get("failed_count", 0)
    except Exception as e:
        logger.warning(f"废标检查失败，通知中将标记为未知: {e}")
        dq_passed = None

    # 获取评分报告
    total_score = None
    try:
        from scoring_report import generate_scoring_report
        scoring = generate_scoring_report(project_id, get_db_connection=get_db_connection)
        total_score = scoring.get("total_score")
    except Exception as e:
        logger.warning(f"评分报告生成失败: {e}")
        total_score = None

    # 构建消息
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    download_link = f"{base_url or ''}/bid#project={project_id}"

    card_content = _build_notification_card(
        project_name=project_info.get("title", "未知项目"),
        completed_at=now_str,
        dq_passed=dq_passed,
        dq_failed_count=dq_failed_count,
        total_score=total_score,
        download_link=download_link,
        project_id=project_id,
    )

    return _send_webhook(webhook_url, card_content)


def _get_project_info(project_id: int, get_db_connection) -> Optional[dict]:
    """获取项目基本信息"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, status, updated_at FROM bid_projects WHERE id = %s",
                (project_id,),
            )
            row = cursor.fetchone()
            cursor.close()

        if not row:
            return None

        return {
            "id": row[0],
            "title": row[1],
            "status": row[2],
            "updated_at": str(row[3]) if row[3] else "",
        }
    except Exception as e:
        logger.error(f"获取项目信息失败: {e}")
        return None


def _build_notification_card(project_name: str, completed_at: str,
                              dq_passed: Optional[bool], dq_failed_count: int,
                              total_score: Optional[float], download_link: str,
                              project_id: int) -> dict:
    """构建飞书卡片消息"""

    # 废标状态文本
    if dq_passed is True:
        dq_status = "✅ 通过"
        dq_color = "green"
    elif dq_passed is False:
        dq_status = f"❌ 不通过（{dq_failed_count} 项不合格）"
        dq_color = "red"
    else:
        dq_status = "⚠️ 未检测"
        dq_color = "orange"

    # 评分文本
    if total_score is not None:
        if total_score >= 80:
            score_color = "green"
            score_emoji = "🏆"
        elif total_score >= 60:
            score_color = "orange"
            score_emoji = "📊"
        else:
            score_color = "red"
            score_emoji = "⚠️"
        score_text = f"{score_emoji} {total_score} / 100 分"
    else:
        score_text = "📊 未生成"
        score_color = "gray"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "📄 标书生成完成通知",
                },
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**项目名称**\n{project_name}"
                        ),
                    },
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**完成时间**\n{completed_at}",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**项目 ID**\n#{project_id}",
                            },
                        },
                    ],
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**废标校验**\n<font color='{dq_color}'>{dq_status}</font>",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**预估得分**\n<font color='{score_color}'>{score_text}</font>",
                            },
                        },
                    ],
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "🔗 查看项目",
                            },
                            "type": "primary",
                            "url": download_link,
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "📋 废标检查",
                            },
                            "type": "default",
                            "url": f"{download_link}&tab=disqualification",
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "📊 评分报告",
                            },
                            "type": "default",
                            "url": f"{download_link}&tab=scoring",
                        },
                    ],
                },
            ],
        },
    }


def _send_webhook(webhook_url: str, payload: dict) -> bool:
    """发送飞书 Webhook 请求"""
    try:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        resp = requests.post(webhook_url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()

        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info("飞书通知发送成功")
            return True
        else:
            logger.error(f"飞书通知发送失败: {result}")
            return False

    except requests.exceptions.Timeout:
        logger.error("飞书通知发送超时")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"飞书通知发送异常: {e}")
        return False
    except Exception as e:
        logger.error(f"飞书通知发送异常: {e}")
        return False
