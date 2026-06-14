"""世界杯预测报告的小红书专用工作流。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.agents.analytics_agent import AnalyticsAgent
from src.agents.base import AgentStep
from src.agents.cover_agent import CoverAgent
from src.agents.publish_agent import PublishAgent
from src.agents.rewriter_agent import RewriterAgent
from src.agents.review_agent import ReviewAgent
from src.agents.workflow_agent import ContentWorkflowAgent
from src.integrations.worldcup_report_adapter import (
    WorldCupPostDraft,
    WorldCupReportAdapter,
)


class WorldCupWorkflowAgent:
    """编排世界杯报告审核、受保护改写、配图和发布。"""

    name = "worldcup_workflow_agent"

    def __init__(
        self,
        *,
        report_adapter: Any = None,
        review_agent: Any = None,
        rewriter_agent: Any = None,
        cover_agent: Any = None,
        publish_agent: Any = None,
        analytics_agent: Any = None,
    ):
        self.report_adapter = report_adapter or WorldCupReportAdapter()
        self.review_agent = review_agent or ReviewAgent()
        self.rewriter_agent = rewriter_agent or RewriterAgent()
        self.cover_agent = cover_agent or CoverAgent()
        self.publish_agent = publish_agent or PublishAgent()
        self.analytics_agent = analytics_agent or AnalyticsAgent()

    def build_publish_payload(
        self,
        report_path: str | Path,
        *,
        page_count: int = 4,
        min_review_score: int = 85,
        max_rewrite_rounds: int = 1,
        cover_template_id: str = "",
        output_path: str | Path = "",
    ) -> Dict[str, Any]:
        """读取报告并生成兼容 xhs_ai 的 publish payload。"""

        steps: List[AgentStep] = [
            AgentStep(
                self.name,
                "plan",
                "completed",
                "规划世界杯预测图文任务",
                {"source_type": "worldcup_forecast"},
            )
        ]
        report = self.report_adapter.load_report(report_path)
        steps.append(
            AgentStep(
                self.report_adapter.__class__.__name__,
                "load_report",
                "completed",
                f"读取世界杯报告：{Path(report_path).expanduser().resolve()}",
            )
        )
        original_draft = self.report_adapter.build_post_draft(report)
        title = original_draft.title
        content = original_draft.content
        steps.append(
            AgentStep(
                self.report_adapter.__class__.__name__,
                "build_draft",
                "completed",
                "使用确定性模板生成受保护草稿",
                {"match_id": original_draft.protected_facts.get("match_id")},
            )
        )

        min_review_score = int(min_review_score or 85)
        max_rewrite_rounds = max(0, int(max_rewrite_rounds or 0))
        review = self.review_agent.review(
            title,
            content,
            min_score=min_review_score,
        )
        steps.append(self._review_step(review, round_index=0))

        rewrite_rounds = 0
        while (
            bool(review.get("can_publish", True))
            and not bool(review.get("passed", False))
            and rewrite_rounds < max_rewrite_rounds
        ):
            rewrite_rounds += 1
            rewritten = self.rewriter_agent.rewrite(
                title,
                content,
                review,
                topic=original_draft.topic,
            )
            rewritten_title = str(getattr(rewritten, "title", "") or "").strip()
            rewritten_content = str(getattr(rewritten, "content", "") or "").strip()
            is_valid = self.report_adapter.validate_protected_facts(
                original_draft,
                rewritten_title,
                rewritten_content,
            )
            steps.append(
                AgentStep(
                    getattr(self.rewriter_agent, "name", "rewriter_agent"),
                    "rewrite",
                    "completed" if is_valid else "reverted",
                    (
                        f"第 {rewrite_rounds} 轮改写通过事实校验"
                        if is_valid
                        else f"第 {rewrite_rounds} 轮改写修改或无法确认关键事实，已回退"
                    ),
                    {
                        "protected_facts_valid": is_valid,
                        "rewrite": self._rewrite_to_dict(rewritten),
                    },
                )
            )
            if not is_valid:
                title = original_draft.title
                content = original_draft.content
                review = self.review_agent.review(
                    title,
                    content,
                    min_score=min_review_score,
                )
                steps.append(self._review_step(review, round_index=rewrite_rounds))
                break

            title = rewritten_title
            content = rewritten_content
            review = self.review_agent.review(
                title,
                content,
                min_score=min_review_score,
            )
            steps.append(self._review_step(review, round_index=rewrite_rounds))

        total_pages = max(2, int(page_count or 4))
        content_pages = self.report_adapter.build_image_pages(original_draft)
        cover = self.cover_agent.generate_for_post(
            title=title,
            content=content,
            topic=original_draft.topic,
            cover_template_id=str(cover_template_id or "").strip(),
            page_count=max(1, total_pages - 1),
            content_pages=content_pages[: max(1, total_pages - 1)],
        )
        images = list(getattr(cover, "images", None) or [])
        steps.append(
            AgentStep(
                getattr(self.cover_agent, "name", "cover_agent"),
                "generate_images",
                "completed" if images else "failed",
                f"生成 {len(images)} 张世界杯图文图片",
                {"source": str(getattr(cover, "source", "") or "")},
            )
        )
        if not images:
            raise RuntimeError("生成失败：CoverAgent 返回的图片为空")

        payload = ContentWorkflowAgent._build_publish_payload(
            title=title,
            content=content,
            images=images,
            topic={
                "topic": original_draft.topic,
                "source": "worldcup_forecast",
                "match_id": original_draft.protected_facts.get("match_id"),
            },
            review=review,
            rewrite_rounds=rewrite_rounds,
            steps=steps,
            platform="xiaohongshu",
            user_id=None,
        )
        payload.update(
            {
                "source_type": "worldcup_forecast",
                "worldcup_metadata": dict(original_draft.metadata),
            }
        )

        if output_path:
            resolved_output = Path(output_path).expanduser().resolve()
            ContentWorkflowAgent.write_publish_json(payload, str(resolved_output))
            steps.append(
                AgentStep(
                    self.name,
                    "write_publish_json",
                    "completed",
                    f"输出 publish.json：{resolved_output}",
                )
            )
            payload["agent_steps"] = [step.to_dict() for step in steps]
            ContentWorkflowAgent.write_publish_json(payload, str(resolved_output))

        return payload

    async def publish_with_poster(
        self,
        poster: Any,
        payload: Dict[str, Any],
        *,
        auto_publish: bool = False,
    ) -> Dict[str, Any]:
        """复用现有 poster 和 PublishAgent 进行预览或显式发布。"""

        payload = dict(payload or {})
        title = str(payload.get("title") or "").strip()
        content = str(payload.get("content") or "").strip()
        images = list(payload.get("images") or [])
        if not title or not content:
            raise RuntimeError("发布失败：标题或正文为空")
        if not images:
            raise RuntimeError("发布失败：缺少图片")

        result = await self.publish_agent.publish(
            poster,
            title,
            content,
            images,
            auto_publish=bool(auto_publish),
        )
        steps = ContentWorkflowAgent._steps_from_payload(payload)
        steps.append(
            AgentStep(
                getattr(self.publish_agent, "name", "publish_agent"),
                "publish" if auto_publish else "preview",
                "completed",
                "已显式发布" if auto_publish else "已填充发布页面，等待人工确认",
                {"auto_publish": bool(auto_publish), "result": bool(result)},
            )
        )
        payload["publish_result"] = bool(result)

        post_record = None
        analytics_error = ""
        if bool(result) and auto_publish:
            try:
                post_record = self.analytics_agent.record_post(
                    payload.get("user_id"),
                    {
                        "title": title,
                        "content": content,
                        "tags": payload.get("tags")
                        or ContentWorkflowAgent._extract_tags(content),
                        "platform": payload.get("platform") or "xiaohongshu",
                        "status": "published",
                        "source_type": "worldcup_forecast",
                    },
                )
                steps.append(
                    AgentStep(
                        getattr(self.analytics_agent, "name", "analytics_agent"),
                        "record_post",
                        "completed",
                        "已记录世界杯预测发布内容",
                        {"post_id": (post_record or {}).get("id")},
                    )
                )
            except Exception as exc:
                analytics_error = str(exc)
                steps.append(
                    AgentStep(
                        getattr(self.analytics_agent, "name", "analytics_agent"),
                        "record_post",
                        "failed",
                        analytics_error,
                    )
                )
        payload["post_record"] = post_record
        payload["analytics_error"] = analytics_error
        payload["agent_steps"] = [step.to_dict() for step in steps]
        return payload

    def _review_step(self, review: Dict[str, Any], *, round_index: int) -> AgentStep:
        return AgentStep(
            getattr(self.review_agent, "name", "review_agent"),
            "review",
            "completed",
            f"第 {round_index} 轮审核：{review.get('quality_score')} 分",
            {
                "decision": review.get("decision"),
                "can_publish": review.get("can_publish"),
                "passed": review.get("passed"),
                "quality_score": review.get("quality_score"),
                "rewrite_suggestions": review.get("rewrite_suggestions") or [],
            },
        )

    @staticmethod
    def _rewrite_to_dict(rewritten: Any) -> Dict[str, Any]:
        to_dict = getattr(rewritten, "to_dict", None)
        if callable(to_dict):
            return dict(to_dict() or {})
        return {
            "title": str(getattr(rewritten, "title", "") or ""),
            "content": str(getattr(rewritten, "content", "") or ""),
            "changed": bool(getattr(rewritten, "changed", False)),
        }
