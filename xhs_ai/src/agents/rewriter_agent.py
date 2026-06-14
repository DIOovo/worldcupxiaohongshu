"""
自动改写 Agent。

职责：根据 Review Agent 的反馈做本地确定性改写，形成可重复的审核-改写闭环。
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List


@dataclass(frozen=True)
class RewriteResult:
    title: str
    content: str
    changed: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "changed": self.changed,
            "reasons": list(self.reasons or []),
        }


class RewriterAgent:
    """负责按审核意见自动降低风险、增强结构和小红书表达。"""

    name = "rewriter_agent"

    risky_words = {
        "保证": "尽量",
        "稳赚": "更稳妥",
        "唯一": "常见",
        "全网最": "比较实用",
        "内幕": "公开信息",
        "绝了": "值得看",
        "封神": "表现不错",
        "必看": "建议收藏",
    }
    ai_taste_patterns = [
        (r"作为(一个)?AI[^，。！？\n]*[，。！？]?", ""),
        (r"本文将(会)?", "这篇直接"),
        (r"综上所述[，,]?", "简单总结："),
        (r"首先[，,]?\s*其次[，,]?\s*最后[，,]?", ""),
    ]

    def rewrite(self, title: str, content: str, review: Dict[str, Any], *, topic: str = "") -> RewriteResult:
        original_title = str(title or "").strip()
        original_content = str(content or "").strip()
        title = original_title
        content = original_content
        reasons: List[str] = []

        title = self._rewrite_title(title, topic=topic)
        if title != original_title:
            reasons.append("优化标题长度和高风险表达。")

        cleaned = self._replace_risky_words(content)
        cleaned = self._remove_ai_taste(cleaned)
        cleaned = self._deduplicate_lines(cleaned)
        if cleaned != content:
            reasons.append("降低风险词、AI味和重复表达。")
            content = cleaned

        if len(content) < 160:
            content = self._expand_content(content, topic=topic or title)
            reasons.append("补充内容结构和行动建议。")

        if "\n\n" not in content:
            content = self._paragraphize(content)
            reasons.append("按小红书阅读节奏重新分段。")

        if "#" not in content:
            content = self._append_tags(content, topic=topic or title)
            reasons.append("补充基础话题标签。")

        return RewriteResult(
            title=title,
            content=content,
            changed=(title != original_title or content != original_content),
            reasons=reasons or ["审核反馈无需明显改写。"],
        )

    def _rewrite_title(self, title: str, *, topic: str = "") -> str:
        title = self._replace_risky_words(str(title or "").strip())
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            title = f"{str(topic or '这个话题').strip()[:10]}怎么做更稳"
        if len(title) > 20:
            title = title[:20].rstrip()
        if len(title) < 8 and topic:
            title = f"{str(topic).strip()[:10]}实用指南"[:20]
        return title

    def _replace_risky_words(self, text: str) -> str:
        out = str(text or "")
        for word, replacement in self.risky_words.items():
            out = out.replace(word, replacement)
        return out

    def _remove_ai_taste(self, text: str) -> str:
        out = str(text or "")
        for pattern, replacement in self.ai_taste_patterns:
            out = re.sub(pattern, replacement, out)
        return out.strip()

    @staticmethod
    def _deduplicate_lines(text: str) -> str:
        lines = [line.rstrip() for line in str(text or "").splitlines()]
        seen = set()
        out = []
        for line in lines:
            key = line.strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(line)
        return "\n".join(out).strip()

    @staticmethod
    def _paragraphize(text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return ""
        parts = re.split(r"(?<=[。！？；])", text)
        chunks = []
        current = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if current and len(current) + len(part) > 56:
                chunks.append(current)
                current = part
            else:
                current = (current + part).strip()
        if current:
            chunks.append(current)
        return "\n\n".join(chunks or [text]).strip()

    @staticmethod
    def _expand_content(content: str, *, topic: str) -> str:
        topic = str(topic or "这个话题").strip()
        base = str(content or "").strip()
        sections = [
            base or f"今天看到「{topic}」，我更建议从实际使用场景来判断。",
            "先看3个重点：\n1. 这件事和你当前需求是否真的相关\n2. 有没有可验证的信息来源\n3. 能不能转成今天就能执行的小动作",
            "我的建议：先低成本尝试，再根据结果复盘，不要因为热度高就立刻跟风。",
        ]
        return "\n\n".join([item for item in sections if item]).strip()

    @staticmethod
    def _append_tags(content: str, *, topic: str) -> str:
        raw_topic = re.sub(r"\s+", "", str(topic or "小红书运营"))[:12] or "小红书运营"
        tags = [raw_topic, "经验分享", "实用干货"]
        return (str(content or "").rstrip() + "\n\n" + " ".join([f"#{tag}" for tag in tags])).strip()
