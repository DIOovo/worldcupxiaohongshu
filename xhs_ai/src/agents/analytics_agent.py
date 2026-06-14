"""
数据复盘 Agent。

职责：记录发布结果、互动指标，并输出账号内容复盘。
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AnalyticsAgent:
    """负责内容数据记录与复盘。"""

    name = "analytics_agent"

    def __init__(self, ops_service: Any = None):
        if ops_service is None:
            from src.core.services.content_ops_service import content_ops_service

            ops_service = content_ops_service
        self.ops_service = ops_service

    def record_post(self, user_id: Optional[int], data: Dict[str, Any]) -> Dict[str, Any]:
        return self.ops_service.create_post(user_id, data)

    def record_metric(self, post_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.ops_service.record_post_metric(post_id, data)

    def analyze(self, user_id: Optional[int] = None, limit: int = 100) -> Dict[str, Any]:
        return self.ops_service.analyze_posts(user_id=user_id, limit=limit)
