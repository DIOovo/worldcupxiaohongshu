from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agents.cover_agent import CoverResult
from src.agents.worldcup_workflow_agent import WorldCupWorkflowAgent
from src.integrations.worldcup_report_adapter import WorldCupReportAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "worldcup_report.json"


class FakeReviewAgent:
    name = "review_agent"

    def __init__(self, scores=(90,)):
        self.scores = list(scores)
        self.calls = 0

    def review(self, title, content="", min_score=85):
        index = min(self.calls, len(self.scores) - 1)
        score = self.scores[index]
        self.calls += 1
        return {
            "decision": "可发布",
            "can_publish": True,
            "quality_score": score,
            "passed": score >= min_score,
            "rewrite_suggestions": [] if score >= min_score else ["优化表达"],
        }


class FakeRewriterAgent:
    name = "rewriter_agent"

    def __init__(self, transform=None):
        self.calls = 0
        self.transform = transform or (lambda content: content + "\n\n表达更简洁。")

    def rewrite(self, title, content, review, topic=""):
        self.calls += 1
        new_content = self.transform(content)
        return type(
            "Rewrite",
            (),
            {
                "title": title,
                "content": new_content,
                "changed": new_content != content,
                "to_dict": lambda self: {
                    "title": title,
                    "content": new_content,
                    "changed": new_content != content,
                },
            },
        )()


class FakeCopyAgent:
    name = "worldcup_copy_agent"

    def __init__(self, result="这场球先看中场节奏，墨西哥状态稍稳，南非的反击也不能忽视。", error=None):
        self.result = result
        self.error = error
        self.calls = []

    def rewrite_analysis(self, home_team, away_team, findings):
        self.calls.append((home_team, away_team, list(findings)))
        if self.error:
            raise self.error
        return self.result


class FakeCoverAgent:
    name = "cover_agent"

    def __init__(self, images=None):
        self.images = (
            ["/tmp/cover.jpg", "/tmp/result.jpg", "/tmp/probability.jpg", "/tmp/reasons.jpg"]
            if images is None
            else images
        )
        self.calls = []

    def generate_for_post(self, **kwargs):
        self.calls.append(kwargs)
        images = self.images[:1] if kwargs.get("cover_only") else self.images
        return CoverResult(images=images, source="fake")


class FakePublishAgent:
    name = "publish_agent"

    def __init__(self):
        self.calls = []

    async def publish(self, poster, title, content, images, auto_publish=True):
        self.calls.append(
            {
                "poster": poster,
                "title": title,
                "content": content,
                "images": images,
                "auto_publish": auto_publish,
            }
        )
        return True


class FakeAnalyticsAgent:
    name = "analytics_agent"

    def __init__(self):
        self.records = []

    def record_post(self, user_id, data):
        self.records.append((user_id, data))
        return {"id": 9}


def build_workflow(**overrides):
    return WorldCupWorkflowAgent(
        report_adapter=overrides.get("report_adapter", WorldCupReportAdapter()),
        review_agent=overrides.get("review_agent", FakeReviewAgent()),
        rewriter_agent=overrides.get("rewriter_agent", FakeRewriterAgent()),
        copy_agent=overrides.get("copy_agent", FakeCopyAgent()),
        cover_agent=overrides.get("cover_agent", FakeCoverAgent()),
        publish_agent=overrides.get("publish_agent", FakePublishAgent()),
        analytics_agent=overrides.get("analytics_agent", FakeAnalyticsAgent()),
    )


def test_review_passes_without_rewrite():
    rewriter = FakeRewriterAgent()
    payload = build_workflow(rewriter_agent=rewriter).build_publish_payload(FIXTURE)
    assert payload["review"]["passed"] is True
    assert payload["rewrite_rounds"] == 0
    assert rewriter.calls == 0


def test_analysis_is_humanized_once():
    copy_agent = FakeCopyAgent()
    payload = build_workflow(copy_agent=copy_agent).build_publish_payload(FIXTURE)
    assert len(copy_agent.calls) == 1
    assert "先看中场节奏" in payload["content"]
    assert "AI" not in payload["content"]
    assert "模型" not in payload["content"]
    assert "个人预测请勿当真。" in payload["content"]


def test_analysis_falls_back_when_humanizing_fails():
    copy_agent = FakeCopyAgent(error=RuntimeError("服务暂不可用"))
    payload = build_workflow(copy_agent=copy_agent).build_publish_payload(FIXTURE)
    assert "墨西哥近期状态更稳定" in payload["content"]
    assert any(
        step["action"] == "rewrite_analysis" and step["status"] == "fallback"
        for step in payload["agent_steps"]
    )


def test_low_score_is_rewritten_and_reviewed_again():
    review = FakeReviewAgent(scores=(70, 92))
    rewriter = FakeRewriterAgent()
    payload = build_workflow(
        review_agent=review,
        rewriter_agent=rewriter,
    ).build_publish_payload(FIXTURE)
    assert payload["rewrite_rounds"] == 1
    assert payload["review"]["passed"] is True
    assert "表达更简洁" in payload["content"]


@pytest.mark.parametrize(
    "transform",
    [
        lambda content: content.replace("墨西哥 2-1 南非", "墨西哥 3-1 南非"),
        lambda content: content.replace("主胜概率：55.0%", "主胜概率：65.0%"),
    ],
)
def test_changed_protected_fact_falls_back_to_original(transform):
    rewriter = FakeRewriterAgent(transform=transform)
    payload = build_workflow(
        review_agent=FakeReviewAgent(scores=(70, 70)),
        rewriter_agent=rewriter,
    ).build_publish_payload(FIXTURE)
    assert "墨西哥 2-1 南非" in payload["content"]
    assert "主胜概率：55.0%" in payload["content"]
    assert any(step["status"] == "reverted" for step in payload["agent_steps"])


def test_empty_cover_images_raise_error():
    with pytest.raises(RuntimeError, match="图片为空"):
        build_workflow(cover_agent=FakeCoverAgent(images=[])).build_publish_payload(
            FIXTURE
        )


def test_publish_payload_defaults_to_one_cover_image():
    cover = FakeCoverAgent()
    payload = build_workflow(cover_agent=cover).build_publish_payload(FIXTURE)
    assert payload["schema"] == "xhs_ai.publish_payload.v1"
    assert payload["platform"] == "xiaohongshu"
    assert payload["source_type"] == "worldcup_forecast"
    assert payload["worldcup_metadata"]["home_win_probability"] == 0.55
    assert len(payload["images"]) == 1
    assert cover.calls[0]["content_pages"] == []
    assert cover.calls[0]["page_count"] == 1
    assert cover.calls[0]["cover_only"] is True
    assert "【赛前看法】" in payload["content"]
    assert "【风险提示】" in payload["content"]


def test_page_count_four_still_builds_three_content_pages():
    cover = FakeCoverAgent()
    build_workflow(cover_agent=cover).build_publish_payload(FIXTURE, page_count=4)
    assert len(cover.calls[0]["content_pages"]) == 3
    assert cover.calls[0]["page_count"] == 3
    assert cover.calls[0]["cover_only"] is False


def test_ai_image_options_are_forwarded_to_cover_agent():
    cover = FakeCoverAgent()
    payload = build_workflow(cover_agent=cover).build_publish_payload(
        FIXTURE,
        image_mode="ai",
        image_provider="qwen",
        image_model="wanx-v1",
        image_size="1024*1024",
        image_endpoint="https://example.com/v1",
    )
    assert cover.calls[0]["image_mode"] == "ai"
    assert cover.calls[0]["image_provider"] == "qwen"
    assert cover.calls[0]["image_model"] == "wanx-v1"
    assert cover.calls[0]["image_size"] == "1024*1024"
    assert cover.calls[0]["image_endpoint"] == "https://example.com/v1"
    assert payload["image_source"] == "fake"


def test_writes_utf8_publish_json(tmp_path):
    output = tmp_path / "世界杯" / "publish.json"
    payload = build_workflow().build_publish_payload(FIXTURE, output_path=output)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["title"] == payload["title"]
    assert "墨西哥" in loaded["content"]


def test_build_does_not_trigger_publish():
    publish_agent = FakePublishAgent()
    build_workflow(publish_agent=publish_agent).build_publish_payload(FIXTURE)
    assert publish_agent.calls == []


@pytest.mark.parametrize(
    ("auto_publish", "expected_action"),
    [(False, "preview"), (True, "publish")],
)
def test_publish_with_poster_uses_explicit_auto_publish(
    auto_publish,
    expected_action,
):
    publish_agent = FakePublishAgent()
    analytics = FakeAnalyticsAgent()
    workflow = build_workflow(
        publish_agent=publish_agent,
        analytics_agent=analytics,
    )
    payload = workflow.build_publish_payload(FIXTURE)
    result = asyncio.run(
        workflow.publish_with_poster(
            object(),
            payload,
            auto_publish=auto_publish,
        )
    )
    assert publish_agent.calls[0]["auto_publish"] is auto_publish
    assert result["agent_steps"][-1 if not auto_publish else -2]["action"] == expected_action
    assert bool(analytics.records) is auto_publish
