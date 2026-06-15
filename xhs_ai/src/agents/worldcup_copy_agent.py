"""世界杯赛前分析的中文口语化改写。"""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.core.services.llm_service import LLMService


class WorldCupCopyAgent:
    """只改写分析表达，不接触比分和概率等受保护事实。"""

    name = "worldcup_copy_agent"
    system_prompt = (
        "把自己当成一个小编。你负责把足球赛前分析改写成自然、有人味的中文短文，"
        "语气像认真看球后和朋友分享观点，不要写成报告。"
    )

    def __init__(self, llm_service: Any = None):
        self.llm_service = llm_service or LLMService()

    def rewrite_analysis(
        self,
        home_team: str,
        away_team: str,
        findings: Iterable[str],
    ) -> str:
        source = "\n".join(
            f"{index}. {str(item).strip()}"
            for index, item in enumerate(findings, 1)
            if str(item).strip()
        )
        user_prompt = f"""
请把下面关于“{home_team}对阵{away_team}”的赛前分析重新写成一段中文。

原始分析：
{source or "暂无详细分析，请基于信息不足这一点自然表达。"}

要求：
1. 全部使用中文，写成一到两段，语气自然，不要太死板。
2. 不要出现“AI”“模型”“算法”“机器人”“生成”等字样。
3. 不要提及写作指令，也不要说明内容由谁生成。
4. 不得编造伤停、首发、排名、赔率或其他原文没有的信息。
5. 不得写“必胜”“稳赢”等确定性结论，不要给出投注建议。
6. 只返回改写后的正文，不要标题、序号、标签或解释。
""".strip()
        result = self.llm_service.generate_text(self.system_prompt, user_prompt)
        return self._clean_result(result)

    @staticmethod
    def _clean_result(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        return text
