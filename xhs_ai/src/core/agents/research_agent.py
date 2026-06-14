"""资料检索 Agent：负责为选题补充上下文摘要。"""

from __future__ import annotations

from typing import Any, Dict, List


class ResearchAgent:
    name = "research_agent"

    def __init__(self, hotspot_client: Any = None):
        if hotspot_client is None:
            from src.core.services.hotspot_service import hotspot_service

            hotspot_client = hotspot_service
        self.hotspot_client = hotspot_client

    def search_snippets(self, query: str, *, limit: int = 3) -> List[Dict[str, str]]:
        query = str(query or "").strip()
        if not query:
            return []
        try:
            return self.hotspot_client.fetch_baidu_search_snippets(query, limit=limit, timeout=10)
        except Exception:
            return []


__all__ = ["ResearchAgent"]
