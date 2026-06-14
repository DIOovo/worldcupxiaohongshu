"""
文案生成 Agent。

职责：根据话题和上下文生成小红书标题/正文；模型不可用时提供本地兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import re
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class GeneratedCopy:
    title: str
    content: str
    source: str = "llm"
    raw_text: str = ""
    raw_json: Optional[Dict[str, Any]] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "raw_text": self.raw_text,
            "raw_json": self.raw_json,
            "error": self.error,
        }


class WriterAgent:
    """负责把选题转成可发布文案。"""

    name = "writer_agent"

    def __init__(self, llm_client: Any = None):
        if llm_client is None:
            from src.core.services.llm_service import llm_service

            llm_client = llm_service
        self.llm_client = llm_client

    def generate_xiaohongshu_content(
        self,
        topic: str,
        *,
        header_title: str = "",
        author: str = "",
        allow_fallback: bool = True,
        fallback_topic: str = "",
    ) -> GeneratedCopy:
        try:
            response = self.llm_client.generate_xiaohongshu_content(
                topic=topic,
                header_title=header_title,
                author=author,
            )
            title = str(getattr(response, "title", "") or "").strip()
            content = str(getattr(response, "content", "") or "").strip()
            if not title and not content:
                raise RuntimeError("模型返回标题/正文为空")
            return GeneratedCopy(
                title=title,
                content=content,
                source="llm",
                raw_text=str(getattr(response, "raw_text", "") or ""),
                raw_json=getattr(response, "raw_json", None),
            )
        except Exception as exc:
            if not allow_fallback:
                raise
            fallback = self.fallback_generate_xhs_content(fallback_topic or topic)
            return GeneratedCopy(
                title=str(fallback.get("title") or "").strip(),
                content=str(fallback.get("content") or "").strip(),
                source="fallback",
                error=str(exc),
            )

    @staticmethod
    def fallback_generate_xhs_content(topic: str) -> Dict[str, str]:
        topic = str(topic or "").strip() or "这个话题"
        base = re.sub(r"\s+", "", topic)[:10] or "这个话题"

        title_templates = [
            f"{base}真的有用吗 先看这3点",
            f"{base}别再踩坑 这份清单够用",
            f"{base}新手必看 3步就能上手",
            f"{base}想提升 先把这件事做对",
            f"{base}怎么做更稳 关键在这里",
        ]
        title = random.choice(title_templates)[:20]
        if len(title) < 15:
            title = (title + "实用版").strip()[:20]

        tips = [
            f"先把结论说清楚：你为什么要关注「{topic}」",
            "不要一上来堆信息，先抓住最关键的 1-2 个点",
            "把能坚持的动作做成日常，比一次性爆发更有效",
        ]
        actions = [
            "今天就开始：写下你的现状和一个可执行的小目标",
            "用 7 天做一次复盘：哪里有效，哪里需要调整",
            "只保留最有效的 2 个习惯，其它先放一放",
        ]

        tags = [topic, "热点", "干货", "实用", "方法"]
        seen = set()
        uniq = []
        for tag in tags:
            tag = re.sub(r"\s+", "", str(tag))
            if not tag or tag in seen:
                continue
            seen.add(tag)
            uniq.append(tag)
        uniq = uniq[:10]

        content = "\n\n".join(
            [
                f"今天刷到「{topic}」，我快速整理了一个更好上手的思路：",
                "先看重点：\n" + "\n".join([f"{i + 1}. {x}" for i, x in enumerate(tips)]),
                "你可以这样做：\n" + "\n".join([f"{i + 1}. {x}" for i, x in enumerate(actions)]),
                "话题标签：" + " ".join(uniq),
            ]
        ).strip()

        return {"title": title, "content": content}
