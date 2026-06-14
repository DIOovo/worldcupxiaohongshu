"""
内容工作流编排 Agent。

职责：把 hot/writer/review/cover 等单一 Agent 串成一次可执行的多步任务。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.agents.analytics_agent import AnalyticsAgent
from src.agents.base import AgentStep
from src.agents.cover_agent import CoverAgent
from src.agents.publish_agent import PublishAgent
from src.agents.rewriter_agent import RewriterAgent
from src.agents.review_agent import ReviewAgent
from src.agents.topic_agent import TopicAgent
from src.agents.writer_agent import WriterAgent


@dataclass(frozen=True)
class HotspotWorkflowRequest:
    source: str = "weibo"
    rank: int = 1
    sources: Optional[Sequence[str]] = None
    auto_select: bool = False
    use_context: bool = True
    cover_template_id: str = ""
    page_count: int = 3
    header_title: str = ""
    author: str = ""
    block_on_reject: bool = False
    min_review_score: int = 85
    max_rewrite_rounds: int = 2
    user_id: Optional[int] = None
    platform: str = "xiaohongshu"
    publish_json_path: str = ""


class ContentWorkflowAgent:
    """小红书内容生产工作流 Agent。"""

    name = "content_workflow_agent"

    def __init__(
        self,
        *,
        topic_agent: Any = None,
        hot_agent: Any = None,
        writer_agent: Any = None,
        review_agent: Any = None,
        rewriter_agent: Any = None,
        cover_agent: Any = None,
        publish_agent: Any = None,
        analytics_agent: Any = None,
    ):
        self.topic_agent = topic_agent or TopicAgent(hot_agent=hot_agent)
        self.writer_agent = writer_agent or WriterAgent()
        self.review_agent = review_agent or ReviewAgent()
        self.rewriter_agent = rewriter_agent or RewriterAgent()
        self.cover_agent = cover_agent or CoverAgent()
        self.publish_agent = publish_agent or PublishAgent()
        self.analytics_agent = analytics_agent or AnalyticsAgent()

    def build_hotspot_payload(self, request: HotspotWorkflowRequest) -> Dict[str, Any]:
        """根据热点自动完成选题、写作、审核改写、配图，返回 publish.json 结构。"""

        steps: List[AgentStep] = [
            AgentStep(self.name, "plan", "completed", "规划内容运营任务", {"workflow": "content_ops_publish"}),
        ]

        if request.auto_select:
            topic = self.topic_agent.select_best_topic(
                request.sources or [request.source],
                limit=max(20, int(request.rank or 1)),
                use_context=request.use_context,
                user_id=request.user_id,
                persist_score=False,
            )
            selection_detail = f"自动选择选题：{topic.topic}"
        else:
            topic = self.topic_agent.select_topic_by_rank(
                source=request.source,
                rank=request.rank,
                use_context=request.use_context,
                user_id=request.user_id,
                persist_score=False,
            )
            selection_detail = f"按榜单位置选择选题：{topic.topic}"

        steps.append(
            AgentStep(
                self.topic_agent.name,
                "select_topic",
                "completed",
                selection_detail,
                {
                    "source": topic.source,
                    "rank": topic.rank,
                    "url": topic.url,
                    "hot_score": topic.hot_score,
                    "risk_score": topic.risk_score,
                    "platform_fit_score": topic.platform_fit_score,
                    "total_score": topic.total_score,
                    "reason": topic.reason,
                },
            )
        )

        llm_topic = topic.topic
        if topic.context_text:
            llm_topic = f"{topic.topic}\n\n参考信息（百度搜索摘要）：\n{topic.context_text}".strip()

        generated = self.writer_agent.generate_xiaohongshu_content(
            llm_topic,
            header_title=request.header_title,
            author=request.author,
            allow_fallback=True,
            fallback_topic=topic.topic,
        )
        title = str(generated.title or "").strip()
        content = str(generated.content or "").strip()
        steps.append(
            AgentStep(
                self.writer_agent.name,
                "write",
                "completed",
                "生成标题与正文",
                {"source": generated.source, "fallback_error": generated.error},
            )
        )

        if not title and not content:
            raise RuntimeError("生成失败：标题/内容为空")

        review = self._review_and_rewrite(
            title=title,
            content=content,
            topic=topic.topic,
            steps=steps,
            min_score=request.min_review_score,
            max_rounds=request.max_rewrite_rounds,
        )
        title = str(review["title"] or "").strip()
        content = str(review["content"] or "").strip()
        review_result = review["review"]

        if request.block_on_reject and not bool(review_result.get("can_publish", True)):
            raise RuntimeError("审核失败：内容被判定为禁止发布")
        if request.block_on_reject and int(review_result.get("quality_score") or 0) < int(request.min_review_score or 85):
            raise RuntimeError("审核失败：内容质量未达到发布阈值")

        cover = self.cover_agent.generate_for_post(
            title=title,
            content=content,
            topic=topic.topic,
            cover_template_id=request.cover_template_id,
            page_count=request.page_count,
        )
        if cover.title_override:
            title = cover.title_override
        if cover.content_override:
            content = cover.content_override
        images = list(cover.images or [])
        steps.append(
            AgentStep(
                self.cover_agent.name,
                "generate_images",
                "completed",
                f"生成 {len(images)} 张图片",
                {"source": cover.source},
            )
        )

        if not images:
            raise RuntimeError("生成失败：图片为空")

        payload = self._build_publish_payload(
            title=title,
            content=content,
            images=images,
            topic=topic.to_dict(),
            review=review_result,
            rewrite_rounds=review["rewrite_rounds"],
            steps=steps,
            platform=request.platform,
            user_id=request.user_id,
        )

        if request.publish_json_path:
            self.write_publish_json(payload, request.publish_json_path)
            steps.append(
                AgentStep(
                    self.name,
                    "write_publish_json",
                    "completed",
                    f"输出 publish.json：{request.publish_json_path}",
                )
            )
            payload["agent_steps"] = [step.to_dict() for step in steps]

        return payload

    async def publish_payload(
        self,
        poster: Any,
        payload: Dict[str, Any],
        *,
        auto_publish: bool = True,
        record_analytics: bool = True,
    ) -> Dict[str, Any]:
        """调用发布工具执行已经生成的 publish.json payload。"""

        payload = dict(payload or {})
        title = str(payload.get("title") or "").strip()
        content = str(payload.get("content") or "").strip()
        images = list(payload.get("images") or [])
        if not title and not content:
            raise RuntimeError("发布失败：标题/正文为空")
        if not images:
            raise RuntimeError("发布失败：缺少图片")

        result = await self.publish_agent.publish(poster, title, content, images, auto_publish=auto_publish)
        steps = self._steps_from_payload(payload)
        steps.append(
            AgentStep(
                self.publish_agent.name,
                "publish",
                "completed",
                "已调用发布工具",
                {"auto_publish": auto_publish, "result": bool(result)},
            )
        )
        payload["publish_result"] = bool(result)

        post_record = None
        analytics_error = ""
        if bool(result) and auto_publish and record_analytics:
            try:
                post_record = self.analytics_agent.record_post(
                    payload.get("user_id"),
                    {
                        "title": title,
                        "content": content,
                        "tags": payload.get("tags") or self._extract_tags(content),
                        "platform": payload.get("platform") or "xiaohongshu",
                        "status": "published",
                    },
                )
                steps.append(
                    AgentStep(
                        self.analytics_agent.name,
                        "record_post",
                        "completed",
                        "已记录发布内容",
                        {"post_id": (post_record or {}).get("id")},
                    )
                )
            except Exception as exc:
                analytics_error = str(exc)
                steps.append(
                    AgentStep(
                        self.analytics_agent.name,
                        "record_post",
                        "failed",
                        analytics_error,
                    )
                )

        payload["post_record"] = post_record
        payload["analytics_error"] = analytics_error
        payload["agent_steps"] = [step.to_dict() for step in steps]
        return payload

    @staticmethod
    def request_from_action(action: Dict[str, Any]) -> HotspotWorkflowRequest:
        source = str(action.get("hotspot_source") or "weibo").strip().lower() or "weibo"
        try:
            rank = int(action.get("hotspot_rank") or 1)
        except Exception:
            rank = 1
        try:
            page_count = int(action.get("page_count") or 3)
        except Exception:
            page_count = 3

        header_title, author = ContentWorkflowAgent._load_title_config()
        return HotspotWorkflowRequest(
            source=source,
            rank=max(1, rank),
            auto_select=bool(action.get("auto_select_topic", False)),
            use_context=bool(action.get("use_hotspot_context", True)),
            cover_template_id=str(action.get("cover_template_id") or "").strip(),
            page_count=max(1, page_count),
            header_title=header_title,
            author=author,
            user_id=action.get("user_id"),
            platform=str(action.get("platform") or "xiaohongshu").strip() or "xiaohongshu",
        )

    @staticmethod
    def _load_title_config():
        try:
            from src.config.config import Config

            title_cfg = Config().get_title_config()
        except Exception:
            title_cfg = {}
        header_title = str((title_cfg or {}).get("title") or "").strip()
        author = str((title_cfg or {}).get("author") or "").strip()
        return header_title, author

    def _review_and_rewrite(
        self,
        *,
        title: str,
        content: str,
        topic: str,
        steps: List[AgentStep],
        min_score: int,
        max_rounds: int,
    ) -> Dict[str, Any]:
        min_score = int(min_score or 85)
        max_rounds = max(0, int(max_rounds or 0))
        rewrite_rounds = 0

        review = self.review_agent.review(title, content, min_score=min_score)
        steps.append(self._review_step(review, round_index=0))

        while bool(review.get("can_publish", True)) and not bool(review.get("passed", False)) and rewrite_rounds < max_rounds:
            rewrite_rounds += 1
            rewritten = self.rewriter_agent.rewrite(title, content, review, topic=topic)
            title = rewritten.title
            content = rewritten.content
            steps.append(
                AgentStep(
                    self.rewriter_agent.name,
                    "rewrite",
                    "completed",
                    f"第 {rewrite_rounds} 轮自动改写",
                    rewritten.to_dict(),
                )
            )
            review = self.review_agent.review(title, content, min_score=min_score)
            steps.append(self._review_step(review, round_index=rewrite_rounds))

        return {
            "title": title,
            "content": content,
            "review": review,
            "rewrite_rounds": rewrite_rounds,
        }

    def _review_step(self, review: Dict[str, Any], *, round_index: int) -> AgentStep:
        return AgentStep(
            self.review_agent.name,
            "review",
            "completed",
            f"第 {round_index} 轮审核：{review.get('quality_score')} 分",
            {
                "decision": review.get("decision"),
                "risk_score": review.get("risk_score"),
                "risk_level": review.get("risk_level"),
                "quality_score": review.get("quality_score"),
                "quality_level": review.get("quality_level"),
                "passed": review.get("passed"),
                "rewrite_suggestions": review.get("rewrite_suggestions") or [],
            },
        )

    @staticmethod
    def _build_publish_payload(
        *,
        title: str,
        content: str,
        images: List[str],
        topic: Dict[str, Any],
        review: Dict[str, Any],
        rewrite_rounds: int,
        steps: List[AgentStep],
        platform: str,
        user_id: Optional[int],
    ) -> Dict[str, Any]:
        return {
            "schema": "xhs_ai.publish_payload.v1",
            "platform": platform or "xiaohongshu",
            "user_id": user_id,
            "title": title,
            "content": content,
            "images": list(images or []),
            "tags": ContentWorkflowAgent._extract_tags(content),
            "topic": dict(topic or {}),
            "hotspot_title": (topic or {}).get("topic"),
            "hotspot_source": (topic or {}).get("source"),
            "hotspot_rank": (topic or {}).get("rank"),
            "hotspot_url": (topic or {}).get("url"),
            "review": dict(review or {}),
            "rewrite_rounds": rewrite_rounds,
            "agent_steps": [step.to_dict() for step in steps],
        }

    @staticmethod
    def write_publish_json(payload: Dict[str, Any], path: str) -> str:
        output_path = Path(path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(output_path)

    @staticmethod
    def _extract_tags(content: str) -> List[str]:
        tags: List[str] = []
        for part in str(content or "").replace("\n", " ").split():
            if not part.startswith("#"):
                continue
            tag = part.lstrip("#").strip()
            if tag and tag not in tags:
                tags.append(tag)
        return tags[:12]

    @staticmethod
    def _steps_from_payload(payload: Dict[str, Any]) -> List[AgentStep]:
        steps: List[AgentStep] = []
        for item in payload.get("agent_steps") or []:
            if not isinstance(item, dict):
                continue
            steps.append(
                AgentStep(
                    agent=str(item.get("agent") or ""),
                    action=str(item.get("action") or ""),
                    status=str(item.get("status") or ""),
                    detail=str(item.get("detail") or ""),
                    data=dict(item.get("data") or {}),
                )
            )
        return steps
