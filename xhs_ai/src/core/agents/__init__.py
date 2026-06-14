"""
核心 Agent 入口。

底层实现位于 `src.agents`，这里提供面向 core 目录的稳定导入路径。
"""

from src.agents import (
    AnalyticsAgent,
    ContentWorkflowAgent,
    CoverAgent,
    HotAgent,
    HotspotWorkflowRequest,
    PublishAgent,
    RewriterAgent,
    ReviewAgent,
    TopicAgent,
    TopicDecision,
    WriterAgent,
)

PlannerAgent = ContentWorkflowAgent
PublisherAgent = PublishAgent

__all__ = [
    "AnalyticsAgent",
    "ContentWorkflowAgent",
    "CoverAgent",
    "HotAgent",
    "HotspotWorkflowRequest",
    "PlannerAgent",
    "PublishAgent",
    "PublisherAgent",
    "RewriterAgent",
    "ReviewAgent",
    "TopicAgent",
    "TopicDecision",
    "WriterAgent",
]
