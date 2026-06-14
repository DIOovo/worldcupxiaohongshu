"""发布 Agent：把发布动作封装为工具调用。"""

from __future__ import annotations

from typing import List

from src.agents.publish_agent import PublishAgent


class PublisherAgent(PublishAgent):
    """兼容命名：PublisherAgent -> PublishAgent。"""


async def publish_note(poster, title: str, content: str, images: List[str], tags=None, account_id=None):
    """发布工具函数，供 Agent 编排层调用。"""

    return await PublisherAgent().publish(poster, title, content, images, auto_publish=True)


__all__ = ["PublisherAgent", "publish_note"]
