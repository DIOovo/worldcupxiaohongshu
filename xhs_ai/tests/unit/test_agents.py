import asyncio
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agents.cover_agent import CoverResult
from src.agents.hot_agent import HotAgent, TopicCandidate
from src.agents.rewriter_agent import RewriterAgent
from src.agents.review_agent import ReviewAgent
from src.agents.topic_agent import TopicAgent, TopicDecision
from src.agents.workflow_agent import ContentWorkflowAgent, HotspotWorkflowRequest
from src.agents.writer_agent import GeneratedCopy, WriterAgent


@dataclass(frozen=True)
class FakeHotspotItem:
    source: str
    rank: int
    title: str
    hot: int
    url: str


class FakeHotspotClient:
    def fetch(self, source, limit=50):
        return [
            FakeHotspotItem(source=source, rank=1, title="第一个热点", hot=100, url="https://example.com/1"),
            FakeHotspotItem(source=source, rank=2, title="第二个热点AI工具", hot=80, url="https://example.com/2"),
        ]

    def fetch_baidu_search_snippets(self, query, limit=3, timeout=10):
        return [{"snippet": f"{query} 的背景摘要"}]


class FakeOpsService:
    def score_topic(self, item, user_id=None, persist=True):
        title = item["title"]
        fit = 91 if "工具" in title else 62
        risk = 18 if "工具" in title else 30
        return {
            "source": item["source"],
            "title": title,
            "url": item.get("url", ""),
            "rank": item.get("rank"),
            "hot_value": item.get("hot"),
            "heat_score": 88,
            "risk_score": risk,
            "xhs_fit_score": fit,
            "total_score": fit - risk * 0.2,
            "risk_level": "low",
            "recommendation": "优先选题",
            "reasons": ["适合生活技巧类内容，讨论度高，风险较低"],
        }

    def review_risk(self, title, content=""):
        risk_score = 40 if "稳赚" in title or "保证" in content else 0
        return {
            "decision": "建议修改" if risk_score else "可发布",
            "risk_score": risk_score,
            "risk_level": "medium" if risk_score else "low",
            "hits": {},
            "suggestions": [],
        }


def test_hot_agent_selects_ranked_topic_with_context():
    agent = HotAgent(hotspot_client=FakeHotspotClient())

    topic = agent.select_topic("weibo", rank=2, use_context=True)

    assert topic.title == "第二个热点AI工具"
    assert topic.rank == 2
    assert topic.context_text == "第二个热点AI工具 的背景摘要"


def test_topic_agent_scores_and_selects_best_topic():
    agent = TopicAgent(
        hot_agent=HotAgent(hotspot_client=FakeHotspotClient(), ops_service=FakeOpsService()),
        ops_service=FakeOpsService(),
    )

    decision = agent.select_best_topic(["weibo"], use_context=False)

    assert decision.topic == "第二个热点AI工具"
    assert decision.platform_fit_score == 91
    assert decision.reason == "适合生活技巧类内容，讨论度高，风险较低"


def test_writer_agent_fallback_returns_publishable_copy():
    result = WriterAgent.fallback_generate_xhs_content("AI效率工具")

    assert result["title"]
    assert "AI效率工具" in result["content"]


class FakeHotAgent:
    name = "hot_agent"

    def select_topic(self, source, rank, use_context=True):
        return TopicCandidate(
            source=source,
            title="AI效率工具爆火",
            url="https://example.com/hot",
            rank=rank,
            hot=1000,
            context_text="搜索摘要",
        )


class FakeTopicAgent:
    name = "topic_agent"

    def select_topic_by_rank(self, source, rank, use_context=True, user_id=None, persist_score=False):
        return TopicDecision(
            topic="AI效率工具爆火",
            source=source,
            url="https://example.com/hot",
            rank=rank,
            hot_score=90,
            risk_score=10,
            platform_fit_score=92,
            total_score=88,
            reason="适合生活技巧类内容，讨论度高，风险较低",
            context_text="搜索摘要",
            raw_score={},
        )


class FakeWriterAgent:
    name = "writer_agent"

    def generate_xiaohongshu_content(
        self,
        topic,
        header_title="",
        author="",
        allow_fallback=True,
        fallback_topic="",
    ):
        assert "搜索摘要" in topic
        assert fallback_topic == "AI效率工具爆火"
        return GeneratedCopy(title="AI效率工具怎么选", content="先看场景，再看成本。", source="llm")


class FakeReviewAgent:
    name = "review_agent"

    def __init__(self):
        self.calls = 0

    def review(self, title, content="", min_score=85):
        self.calls += 1
        passed = self.calls > 1
        return {
            "decision": "可发布",
            "risk_score": 0,
            "risk_level": "low",
            "can_publish": True,
            "quality_score": 92 if passed else 70,
            "quality_level": "ready" if passed else "needs_polish",
            "passed": passed,
            "rewrite_suggestions": [] if passed else ["补充结构"],
        }


class FakeRewriterAgent:
    name = "rewriter_agent"

    def rewrite(self, title, content, review, topic=""):
        return type(
            "FakeRewrite",
            (),
            {
                "title": title,
                "content": content + "\n\n1. 先看场景\n2. 再看成本\n\n#AI工具 #效率",
                "to_dict": lambda self: {
                    "title": title,
                    "content": content,
                    "changed": True,
                    "reasons": ["补充结构"],
                },
            },
        )()


class FakeCoverAgent:
    name = "cover_agent"

    def generate_for_post(self, title, content, topic="", cover_template_id="", page_count=3):
        assert title == "AI效率工具怎么选"
        return CoverResult(images=["/tmp/cover.jpg", "/tmp/page.jpg"], source="fake")


def test_content_workflow_agent_builds_hotspot_payload():
    workflow = ContentWorkflowAgent(
        topic_agent=FakeTopicAgent(),
        writer_agent=FakeWriterAgent(),
        review_agent=FakeReviewAgent(),
        rewriter_agent=FakeRewriterAgent(),
        cover_agent=FakeCoverAgent(),
    )

    payload = workflow.build_hotspot_payload(
        HotspotWorkflowRequest(source="weibo", rank=1, use_context=True, cover_template_id="tpl", page_count=2)
    )

    assert payload["title"] == "AI效率工具怎么选"
    assert "#AI工具" in payload["content"]
    assert payload["images"] == ["/tmp/cover.jpg", "/tmp/page.jpg"]
    assert payload["hotspot_title"] == "AI效率工具爆火"
    assert payload["review"]["passed"] is True
    assert payload["rewrite_rounds"] == 1
    assert [step["agent"] for step in payload["agent_steps"]] == [
        "content_workflow_agent",
        "topic_agent",
        "writer_agent",
        "review_agent",
        "rewriter_agent",
        "review_agent",
        "cover_agent",
    ]


def test_review_and_rewriter_loop_improves_content():
    review_agent = ReviewAgent(ops_service=FakeOpsService())
    review = review_agent.review("股票内幕保证稳赚", "作为一个AI，本文将说明这个方法保证有效。", min_score=85)
    rewritten = RewriterAgent().rewrite("股票内幕保证稳赚", "作为一个AI，本文将说明这个方法保证有效。", review, topic="投资避坑")

    assert review["quality_score"] < 85
    assert "保证" not in rewritten.title
    assert "作为一个AI" not in rewritten.content
    assert "#" in rewritten.content


class FakePublishAgent:
    name = "publish_agent"

    def __init__(self):
        self.calls = []

    async def publish(self, poster, title, content, images, auto_publish=True):
        self.calls.append((poster, title, content, images, auto_publish))
        return True


class FakeAnalyticsAgent:
    name = "analytics_agent"

    def __init__(self):
        self.records = []

    def record_post(self, user_id, data):
        self.records.append((user_id, data))
        return {"id": 7, **data}


def test_workflow_publish_payload_records_analytics():
    async def run():
        publish_agent = FakePublishAgent()
        analytics_agent = FakeAnalyticsAgent()
        workflow = ContentWorkflowAgent(publish_agent=publish_agent, analytics_agent=analytics_agent)

        result = await workflow.publish_payload(
            object(),
            {
                "schema": "xhs_ai.publish_payload.v1",
                "platform": "xiaohongshu",
                "user_id": 3,
                "title": "AI效率工具怎么选",
                "content": "先看场景\n\n#AI工具 #效率",
                "images": ["/tmp/cover.jpg"],
                "tags": ["AI工具", "效率"],
                "agent_steps": [],
            },
        )

        assert result["publish_result"] is True
        assert result["post_record"]["id"] == 7
        assert analytics_agent.records[0][0] == 3
        assert publish_agent.calls[0][4] is True

    asyncio.run(run())
