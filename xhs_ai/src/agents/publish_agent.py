"""
发布执行 Agent。

职责：封装浏览器发布动作，让 BrowserThread 只负责线程和信号调度。
"""

from __future__ import annotations

from typing import List


class PublishAgent:
    """负责调用浏览器执行实际发布/预览动作。"""

    name = "publish_agent"

    async def publish(self, poster, title: str, content: str, images: List[str], *, auto_publish: bool = True):
        if not poster:
            raise RuntimeError("发布失败：浏览器发布器未初始化")
        return await poster.post_article(title, content, images, auto_publish=auto_publish)

    async def preview(self, poster, title: str, content: str, images: List[str]):
        return await self.publish(poster, title, content, images, auto_publish=False)
