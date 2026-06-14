"""
内容审核 Agent。

职责：在发布前执行风险、标题党、未证实信息等规则审核。
"""

from __future__ import annotations

import re
from typing import Any, Dict


class ReviewAgent:
    """负责发布前内容风险判断。"""

    name = "review_agent"

    def __init__(self, ops_service: Any = None):
        if ops_service is None:
            from src.core.services.content_ops_service import content_ops_service

            ops_service = content_ops_service
        self.ops_service = ops_service

    def review(self, title: str, content: str = "", *, min_score: int = 85) -> Dict[str, Any]:
        result = dict(self.ops_service.review_risk(title, content) or {})
        decision = str((result or {}).get("decision") or "").strip()
        dimensions = self._score_dimensions(title, content, result)
        quality_score = self._weighted_score(dimensions)
        rewrite_suggestions = self._build_rewrite_suggestions(dimensions, result, min_score=min_score)
        can_publish = decision != "禁止发布"
        return {
            **result,
            "dimensions": dimensions,
            "quality_score": quality_score,
            "quality_level": self._quality_level(quality_score),
            "passed": can_publish and quality_score >= int(min_score or 85),
            "can_publish": can_publish,
            "rewrite_suggestions": rewrite_suggestions,
        }

    def _score_dimensions(self, title: str, content: str, risk_review: Dict[str, Any]) -> Dict[str, int]:
        title = str(title or "").strip()
        content = str(content or "").strip()
        risk_score = int((risk_review or {}).get("risk_score") or 0)

        return {
            "title_attraction": self._title_score(title),
            "content_completeness": self._content_completeness_score(content),
            "xiaohongshu_style": self._xhs_style_score(title, content),
            "compliance": max(0, 100 - risk_score),
            "ai_taste": self._ai_taste_score(content),
            "repetition": self._repetition_score(content),
            "tag_match": self._tag_score(title, content),
        }

    @staticmethod
    def _weighted_score(dimensions: Dict[str, int]) -> int:
        weights = {
            "title_attraction": 0.16,
            "content_completeness": 0.20,
            "xiaohongshu_style": 0.18,
            "compliance": 0.20,
            "ai_taste": 0.10,
            "repetition": 0.08,
            "tag_match": 0.08,
        }
        score = 0.0
        for key, weight in weights.items():
            score += int(dimensions.get(key) or 0) * weight
        return int(round(score))

    @staticmethod
    def _title_score(title: str) -> int:
        title = str(title or "").strip()
        if not title:
            return 0
        score = 55
        if 8 <= len(title) <= 20:
            score += 25
        elif len(title) <= 26:
            score += 12
        if any(word in title for word in ["怎么", "如何", "清单", "避坑", "建议", "方法", "指南"]):
            score += 12
        if any(word in title for word in ["保证", "稳赚", "唯一", "全网最", "内幕"]):
            score -= 25
        return max(0, min(100, score))

    @staticmethod
    def _content_completeness_score(content: str) -> int:
        content = str(content or "").strip()
        length = len(content)
        score = 30
        if length >= 120:
            score += 20
        if length >= 220:
            score += 20
        if len([p for p in content.splitlines() if p.strip()]) >= 4:
            score += 15
        if re.search(r"\d+[.、]", content):
            score += 10
        if any(word in content for word in ["建议", "步骤", "方法", "复盘", "注意"]):
            score += 5
        return max(0, min(100, score))

    @staticmethod
    def _xhs_style_score(title: str, content: str) -> int:
        text = f"{title}\n{content}"
        score = 45
        if "\n\n" in content:
            score += 15
        if "#" in content:
            score += 15
        if any(word in text for word in ["收藏", "避坑", "亲测", "新手", "清单", "实用"]):
            score += 15
        if len(str(title or "")) <= 20:
            score += 10
        return max(0, min(100, score))

    @staticmethod
    def _ai_taste_score(content: str) -> int:
        content = str(content or "")
        penalties = 0
        ai_patterns = ["作为一个AI", "本文将", "综上所述", "总而言之", "首先其次最后"]
        for pattern in ai_patterns:
            if pattern in content:
                penalties += 18
        if content.count("。") > 8 and "\n" not in content:
            penalties += 12
        return max(0, 100 - penalties)

    @staticmethod
    def _repetition_score(content: str) -> int:
        lines = [line.strip() for line in str(content or "").splitlines() if line.strip()]
        if len(lines) <= 1:
            return 82
        unique = len(set(lines))
        ratio = unique / max(1, len(lines))
        return int(max(40, min(100, ratio * 100)))

    @staticmethod
    def _tag_score(title: str, content: str) -> int:
        tags = re.findall(r"#([^\s#]{1,24})", str(content or ""))
        if not tags:
            return 45
        score = 60 + min(30, len(set(tags)) * 6)
        title = str(title or "")
        if any(tag and tag in title for tag in tags):
            score += 10
        return max(0, min(100, score))

    @staticmethod
    def _quality_level(score: int) -> str:
        if score >= 90:
            return "excellent"
        if score >= 85:
            return "ready"
        if score >= 70:
            return "needs_polish"
        return "needs_rewrite"

    @staticmethod
    def _build_rewrite_suggestions(
        dimensions: Dict[str, int],
        risk_review: Dict[str, Any],
        *,
        min_score: int,
    ) -> list[str]:
        suggestions = []
        if int((risk_review or {}).get("risk_score") or 0) >= 35:
            suggestions.append("降低敏感、绝对化和未经证实表达。")
        if dimensions.get("title_attraction", 0) < 85:
            suggestions.append("标题控制在 8-20 字，并加入方法、清单、避坑等明确利益点。")
        if dimensions.get("content_completeness", 0) < 85:
            suggestions.append("补充背景、关键判断和可执行步骤。")
        if dimensions.get("xiaohongshu_style", 0) < 85:
            suggestions.append("增加分段、标签和更口语化的小红书表达。")
        if dimensions.get("ai_taste", 0) < 90:
            suggestions.append("去掉“本文将、综上所述”等 AI 味模板句。")
        if dimensions.get("repetition", 0) < 90:
            suggestions.append("合并重复句子，避免同一观点反复出现。")
        if dimensions.get("tag_match", 0) < 80:
            suggestions.append("补充 3-6 个与选题直接相关的话题标签。")
        if not suggestions and ReviewAgent._weighted_score(dimensions) < int(min_score or 85):
            suggestions.append("整体质量未达发布阈值，建议继续强化结构和行动建议。")
        return suggestions
