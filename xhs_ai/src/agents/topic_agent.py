"""
选题 Agent。

职责：把热榜候选转成可决策的内容选题，包含热度、风险和小红书适配评分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from src.agents.hot_agent import HotAgent, TopicCandidate


@dataclass(frozen=True)
class TopicDecision:
    topic: str
    source: str
    url: str = ""
    rank: int = 1
    hot_value: Optional[int] = None
    hot_score: int = 0
    risk_score: int = 0
    platform_fit_score: int = 0
    total_score: float = 0
    reason: str = ""
    context_text: str = ""
    raw_score: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "source": self.source,
            "url": self.url,
            "rank": self.rank,
            "hot_value": self.hot_value,
            "hot_score": self.hot_score,
            "risk_score": self.risk_score,
            "platform_fit_score": self.platform_fit_score,
            "total_score": self.total_score,
            "reason": self.reason,
            "context_text": self.context_text,
            "raw_score": dict(self.raw_score or {}),
        }


class TopicAgent:
    """负责抓取、评分并选择最值得写的小红书选题。"""

    name = "topic_agent"

    def __init__(self, hot_agent: Any = None, ops_service: Any = None):
        self.hot_agent = hot_agent or HotAgent(ops_service=ops_service)
        self.ops_service = ops_service

    def select_best_topic(
        self,
        sources: Sequence[str] | str = "weibo",
        *,
        limit: int = 20,
        use_context: bool = True,
        user_id: Optional[int] = None,
        persist_score: bool = False,
    ) -> TopicDecision:
        decisions = self.rank_topics(
            sources,
            limit=limit,
            use_context=use_context,
            user_id=user_id,
            persist_score=persist_score,
        )
        if not decisions:
            raise RuntimeError("选题失败：没有可用热点候选")
        return decisions[0]

    def select_topic_by_rank(
        self,
        source: str = "weibo",
        rank: int = 1,
        *,
        use_context: bool = True,
        user_id: Optional[int] = None,
        persist_score: bool = False,
    ) -> TopicDecision:
        candidate = self.hot_agent.select_topic(source=source, rank=rank, use_context=use_context)
        return self.score_candidate(candidate, user_id=user_id, persist_score=persist_score)

    def rank_topics(
        self,
        sources: Sequence[str] | str = "weibo",
        *,
        limit: int = 20,
        use_context: bool = True,
        user_id: Optional[int] = None,
        persist_score: bool = False,
    ) -> List[TopicDecision]:
        if isinstance(sources, str):
            source_list = [sources]
        else:
            source_list = [str(source or "").strip() for source in sources if str(source or "").strip()]
        if not source_list:
            source_list = ["weibo"]

        decisions: List[TopicDecision] = []
        for source in source_list:
            try:
                items = self.hot_agent.hotspot_client.fetch(source, limit=max(1, int(limit or 20)))
            except Exception:
                continue
            for item in items or []:
                title = str(getattr(item, "title", "") or "").strip()
                if not title:
                    continue
                context_text = self.hot_agent._fetch_context(title, use_context=use_context)
                candidate = TopicCandidate(
                    source=str(getattr(item, "source", "") or source),
                    title=title,
                    url=str(getattr(item, "url", "") or ""),
                    rank=int(getattr(item, "rank", 0) or 1),
                    hot=getattr(item, "hot", None),
                    context_text=context_text,
                )
                decisions.append(self.score_candidate(candidate, user_id=user_id, persist_score=persist_score))

        return sorted(decisions, key=lambda item: item.total_score, reverse=True)

    def score_candidate(
        self,
        candidate: TopicCandidate,
        *,
        user_id: Optional[int] = None,
        persist_score: bool = False,
    ) -> TopicDecision:
        ops_service = self._get_ops_service()
        raw_score = ops_service.score_topic(
            {
                "source": candidate.source,
                "title": candidate.title,
                "url": candidate.url,
                "rank": candidate.rank,
                "hot": candidate.hot,
            },
            user_id=user_id,
            persist=persist_score,
        )

        hot_score = int(raw_score.get("heat_score") or 0)
        risk_score = int(raw_score.get("risk_score") or 0)
        platform_fit_score = int(raw_score.get("xhs_fit_score") or 0)
        total_score = float(raw_score.get("total_score") or 0)
        reason = self._build_reason(raw_score)

        return TopicDecision(
            topic=candidate.title,
            source=candidate.source,
            url=candidate.url,
            rank=candidate.rank,
            hot_value=candidate.hot,
            hot_score=hot_score,
            risk_score=risk_score,
            platform_fit_score=platform_fit_score,
            total_score=total_score,
            reason=reason,
            context_text=candidate.context_text,
            raw_score=raw_score,
        )

    def _get_ops_service(self):
        if self.ops_service is None:
            from src.core.services.content_ops_service import content_ops_service

            self.ops_service = content_ops_service
        return self.ops_service

    @staticmethod
    def _build_reason(score: Dict[str, Any]) -> str:
        reasons = score.get("reasons") or []
        if isinstance(reasons, list) and reasons:
            return str(reasons[0])
        recommendation = str(score.get("recommendation") or "").strip()
        risk = str(score.get("risk_level") or "").strip()
        if recommendation:
            return f"{recommendation}，风险等级：{risk or 'unknown'}"
        return "根据热度、风险和小红书适配度综合评分。"
