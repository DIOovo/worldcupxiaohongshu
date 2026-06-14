"""
热点选题 Agent。

职责：抓取候选热点、选择目标热点，并按需补充搜索摘要上下文。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class TopicCandidate:
    source: str
    title: str
    url: str = ""
    rank: int = 1
    hot: Optional[int] = None
    context_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "rank": self.rank,
            "hot": self.hot,
            "context_text": self.context_text,
        }


class HotAgent:
    """负责从热点源中做选题决策。"""

    name = "hot_agent"

    def __init__(self, hotspot_client: Any = None, ops_service: Any = None):
        if hotspot_client is None:
            from src.core.services.hotspot_service import hotspot_service

            hotspot_client = hotspot_service
        self.hotspot_client = hotspot_client
        self.ops_service = ops_service

    def select_topic(
        self,
        source: str = "weibo",
        rank: int = 1,
        *,
        limit: Optional[int] = None,
        use_context: bool = True,
    ) -> TopicCandidate:
        source = (source or "weibo").strip().lower() or "weibo"
        rank = max(1, int(rank or 1))
        fetch_limit = max(limit or 0, rank, 50)

        items = self.hotspot_client.fetch(source, limit=fetch_limit)
        if not items:
            raise RuntimeError(f"热点抓取失败：{source} 无数据")

        item = items[rank - 1] if len(items) >= rank else items[0]
        title = str(getattr(item, "title", "") or "").strip()
        if not title:
            raise RuntimeError("热点抓取失败：标题为空")

        context_text = self._fetch_context(title, use_context=use_context)
        return TopicCandidate(
            source=str(getattr(item, "source", "") or source),
            title=title,
            url=str(getattr(item, "url", "") or ""),
            rank=int(getattr(item, "rank", 0) or rank),
            hot=getattr(item, "hot", None),
            context_text=context_text,
        )

    def score_topics(
        self,
        sources: Sequence[str],
        *,
        limit: int = 20,
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> List[Dict[str, Any]]:
        ops_service = self.ops_service
        if ops_service is None:
            from src.core.services.content_ops_service import content_ops_service

            ops_service = content_ops_service
        return ops_service.score_hotspots(sources, limit=limit, user_id=user_id, persist=persist)

    def _fetch_context(self, title: str, *, use_context: bool) -> str:
        if not use_context:
            return ""

        try:
            snippets = self.hotspot_client.fetch_baidu_search_snippets(title, limit=3, timeout=10)
        except Exception:
            return ""

        parts = []
        for item in snippets or []:
            snippet = str((item or {}).get("snippet") or "").strip()
            if snippet:
                parts.append(snippet)
        return "\n".join(parts).strip()
