"""将 worldcup 项目的 JSON 日报转换为受保护的小红书草稿。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List


DISCLAIMER = "个人预测请勿当真。"
REQUIRED_TAGS = ["#世界杯", "#世界杯预测", "#足球", "#赛前预测", "#比赛分析"]
FACT_BLOCK_START = "【预测事实】"
FACT_BLOCK_END = "【事实结束】"

TEAM_NAMES = {
    "Mexico": "墨西哥",
    "South Africa": "南非",
    "South Korea": "韩国",
    "Czech Republic": "捷克",
    "Canada": "加拿大",
    "Bosnia and Herzegovina": "波黑",
    "Qatar": "卡塔尔",
    "Switzerland": "瑞士",
    "Brazil": "巴西",
    "Morocco": "摩洛哥",
    "Haiti": "海地",
    "Scotland": "苏格兰",
    "United States": "美国",
    "Paraguay": "巴拉圭",
    "Australia": "澳大利亚",
    "Turkey": "土耳其",
    "Germany": "德国",
    "Curaçao": "库拉索",
    "Curacao": "库拉索",
    "Ivory Coast": "科特迪瓦",
    "Ecuador": "厄瓜多尔",
    "Netherlands": "荷兰",
    "Japan": "日本",
    "Sweden": "瑞典",
    "Tunisia": "突尼斯",
    "Belgium": "比利时",
    "Egypt": "埃及",
    "Iran": "伊朗",
    "New Zealand": "新西兰",
    "Spain": "西班牙",
    "Cape Verde": "佛得角",
    "Saudi Arabia": "沙特阿拉伯",
    "Uruguay": "乌拉圭",
    "France": "法国",
    "Senegal": "塞内加尔",
    "Iraq": "伊拉克",
    "Norway": "挪威",
    "Argentina": "阿根廷",
    "Algeria": "阿尔及利亚",
    "Austria": "奥地利",
    "Jordan": "约旦",
    "Portugal": "葡萄牙",
    "DR Congo": "刚果（金）",
    "Uzbekistan": "乌兹别克斯坦",
    "Colombia": "哥伦比亚",
    "England": "英格兰",
    "Croatia": "克罗地亚",
    "Ghana": "加纳",
    "Panama": "巴拿马",
}

STAGE_NAMES = {
    "Group Stage": "小组赛",
    "Round of 32": "三十二强赛",
    "Round of 16": "十六强赛",
    "Quarter-finals": "四分之一决赛",
    "Quarterfinals": "四分之一决赛",
    "Semi-finals": "半决赛",
    "Semifinals": "半决赛",
    "Third-place play-off": "季军赛",
    "Final": "决赛",
}


@dataclass(frozen=True)
class WorldCupPostDraft:
    """由报告确定性生成的小红书草稿。"""

    title: str
    content: str
    topic: str
    metadata: Dict[str, Any]
    protected_facts: Dict[str, Any]


class WorldCupReportAdapter:
    """读取、校验并转换世界杯预测 JSON。"""

    probability_tolerance = Decimal("0.001")
    prohibited_claim_terms = (
        "球员伤停",
        "受伤",
        "伤缺",
        "停赛",
        "缺阵",
        "世界排名",
        "FIFA排名",
        "实时排名",
        "赔率",
        "首发名单",
        "确认首发",
        "必胜",
        "稳赢",
        "一定会赢",
        "确定获胜",
        "锁定胜局",
    )

    def load_report(self, report_path: str | Path) -> Dict[str, Any]:
        """读取报告并校验根节点。"""

        path = Path(report_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"世界杯报告不存在：{path}")
        if not path.is_file():
            raise ValueError(f"世界杯报告路径不是文件：{path}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"世界杯报告 JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}"
            ) from exc
        except OSError as exc:
            raise OSError(f"读取世界杯报告失败：{path}，{exc}") from exc
        if not isinstance(report, dict):
            raise ValueError("世界杯报告格式错误：JSON 根节点必须是对象")
        report = self.normalize_report(report)
        self.validate_report(report)
        return report

    def normalize_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """将已知的真实报告 schema 转换为统一的 fixture/consensus 结构。"""

        if isinstance(report.get("fixture"), dict) and isinstance(
            report.get("consensus"), dict
        ):
            return report
        if not (
            isinstance(report.get("match"), dict)
            and isinstance(report.get("prediction"), dict)
        ):
            return report

        match = report["match"]
        prediction = report["prediction"]
        model_details = (
            report.get("model_details")
            if isinstance(report.get("model_details"), dict)
            else {}
        )
        kickoff = match.get("kickoff_time")
        if not kickoff:
            prediction_date = str(match.get("prediction_date") or "").strip()
            kickoff = (
                f"{prediction_date}（具体开球时间未提供）"
                if prediction_date
                else "具体开球时间未提供"
            )
        reasons = self._string_list(model_details.get("adjustment_reasons"))
        warnings: List[str] = []
        if not match.get("kickoff_time"):
            warnings.append("报告未提供具体开球时间。")
        if report.get("weather") in (None, "", {}, []):
            warnings.append("报告未提供天气数据。")

        normalized = {
            "fixture": {
                "match_id": match.get("match_id"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "kickoff": kickoff,
                "stage": match.get("stage") or match.get("tournament") or "未知阶段",
                "status": "scheduled",
            },
            "consensus": {
                "generated_at": report.get("generated_at"),
                "match_predictions": [
                    {
                        "match_id": match.get("match_id"),
                        "home_team": match.get("home_team"),
                        "away_team": match.get("away_team"),
                        "home_goals": prediction.get("predicted_home_score"),
                        "away_goals": prediction.get("predicted_away_score"),
                        "home_win_probability": prediction.get(
                            "home_win_probability"
                        ),
                        "draw_probability": prediction.get("draw_probability"),
                        "away_win_probability": prediction.get(
                            "away_win_probability"
                        ),
                        "rationale": "；".join(reasons),
                    }
                ],
                "agreement_score": None,
                "agent_count": 1,
                "warnings": warnings,
            },
            "agents": [
                {
                    "agent_id": str(model_details.get("model") or "prediction_model"),
                    "provider_id": "worldcup_report",
                    "key_findings": reasons,
                }
            ],
            "intelligence": self._normalize_intelligence(report),
            "articles": [],
            "_source_report": {
                "schema_version": report.get("schema_version"),
                "report_type": report.get("report_type"),
            },
        }
        return normalized

    def validate_report(self, report: Dict[str, Any]) -> None:
        """校验 fixture、共识预测、概率和比分。"""

        fixture = self._require_dict(report, "fixture", "报告缺少 fixture")
        for key in ("match_id", "home_team", "away_team", "kickoff", "stage"):
            self._require_value(fixture, key, f"fixture 缺少必要字段：{key}")

        consensus = self._require_dict(report, "consensus", "报告缺少 consensus")
        predictions = consensus.get("match_predictions")
        if not isinstance(predictions, list) or not predictions:
            raise ValueError("consensus 缺少有效的 match_predictions")
        prediction = predictions[0]
        if not isinstance(prediction, dict):
            raise ValueError("consensus.match_predictions[0] 必须是对象")

        for key in (
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
            "home_win_probability",
            "draw_probability",
            "away_win_probability",
        ):
            self._require_value(
                prediction,
                key,
                f"consensus.match_predictions[0] 缺少必要字段：{key}",
                allow_zero=True,
            )

        if str(prediction["home_team"]).strip() != str(fixture["home_team"]).strip():
            raise ValueError("预测主队与 fixture 主队不一致")
        if str(prediction["away_team"]).strip() != str(fixture["away_team"]).strip():
            raise ValueError("预测客队与 fixture 客队不一致")

        self._as_non_negative_int(prediction["home_goals"], "home_goals")
        self._as_non_negative_int(prediction["away_goals"], "away_goals")
        probabilities = [
            self._as_probability(prediction[key], key)
            for key in (
                "home_win_probability",
                "draw_probability",
                "away_win_probability",
            )
        ]
        if abs(sum(probabilities) - Decimal("1")) > self.probability_tolerance:
            raise ValueError("主胜、平局、客胜概率总和明显不合理，必须接近 1")

    def build_post_draft(self, report: Dict[str, Any]) -> WorldCupPostDraft:
        """使用确定性模板生成标题、正文和受保护事实。"""

        self.validate_report(report)
        fixture = report["fixture"]
        consensus = report["consensus"]
        prediction = consensus["match_predictions"][0]

        raw_home = str(fixture["home_team"]).strip()
        raw_away = str(fixture["away_team"]).strip()
        home = self._translate_team(raw_home)
        away = self._translate_team(raw_away)
        home_goals = self._as_non_negative_int(prediction["home_goals"], "home_goals")
        away_goals = self._as_non_negative_int(prediction["away_goals"], "away_goals")
        home_probability = self._as_probability(
            prediction["home_win_probability"], "home_win_probability"
        )
        draw_probability = self._as_probability(
            prediction["draw_probability"], "draw_probability"
        )
        away_probability = self._as_probability(
            prediction["away_win_probability"], "away_win_probability"
        )
        predicted_result = self._predicted_result(
            home,
            away,
            home_probability,
            draw_probability,
            away_probability,
        )
        agreement_score = self._optional_probability(
            consensus.get("agreement_score"), "agreement_score"
        )
        agent_count = self._optional_non_negative_int(
            consensus.get("agent_count"), "agent_count"
        )
        findings = [
            self._translate_visible_text(item)
            for item in self._collect_key_findings(report.get("agents") or [])
        ]
        warnings = [
            self._translate_visible_text(item)
            for item in self._string_list(consensus.get("warnings"))
        ]
        completeness, data_notes = self._data_completeness(report.get("intelligence"))
        kickoff = str(fixture["kickoff"]).strip().replace("T", " ")
        stage = STAGE_NAMES.get(
            str(fixture["stage"]).strip(), str(fixture["stage"]).strip()
        )

        protected_facts = {
            "match_id": str(fixture["match_id"]).strip(),
            "home_team": home,
            "away_team": away,
            "kickoff": kickoff,
            "stage": stage,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "home_win_probability": float(home_probability),
            "draw_probability": float(draw_probability),
            "away_win_probability": float(away_probability),
            "predicted_result": predicted_result,
            "agreement_score": (
                float(agreement_score) if agreement_score is not None else None
            ),
            "agent_count": agent_count,
        }
        fact_block = self._build_fact_block(protected_facts)

        basis_lines = findings or ["目前可参考的信息不多，临场变化仍然值得留意。"]
        warning_lines = warnings or data_notes or ["未发现额外警告。"]
        content_parts = [
            f"{home}对阵{away}，我把这场世界杯比赛的赛前数据和个人看法整理了一下。",
            fact_block,
            "【赛前看法】\n"
            + "\n".join(f"{index}. {item}" for index, item in enumerate(basis_lines, 1)),
            f"【数据状态】\n数据完整度：{float(completeness):.0%}\n"
            + "\n".join(f"- {item}" for item in warning_lines),
            "【风险提示】\n比分预测具有高方差，请结合临场阵容和比赛进程理性参考。",
            DISCLAIMER,
            " ".join(REQUIRED_TAGS),
        ]
        metadata = {
            **protected_facts,
            "key_findings": basis_lines,
            "warnings": warnings,
            "data_completeness": float(completeness),
            "data_notes": data_notes,
            "source_report": dict(report.get("_source_report") or {}),
        }
        return WorldCupPostDraft(
            title=f"{home}对阵{away}赛前预测"[:20],
            content="\n\n".join(content_parts),
            topic=f"{home}对阵{away}世界杯预测",
            metadata=metadata,
            protected_facts=protected_facts,
        )

    def apply_humanized_analysis(
        self,
        draft: WorldCupPostDraft,
        analysis: str,
    ) -> WorldCupPostDraft:
        """将口语化分析放回正文，同时保留受保护事实区块。"""

        cleaned = str(analysis or "").strip()
        if not cleaned:
            return draft
        if re.search(r"[A-Za-z]", cleaned):
            raise ValueError("改写结果包含非中文词语")
        banned_terms = ("AI", "模型", "算法", "机器人", "生成")
        if any(term in cleaned for term in banned_terms):
            raise ValueError("改写结果包含不允许出现的表述")
        if any(term in cleaned for term in self.prohibited_claim_terms):
            raise ValueError("改写结果包含未经报告支持的确定性表述")

        pattern = re.compile(
            r"【赛前看法】\n.*?(?=\n\n【数据状态】)",
            re.DOTALL,
        )
        content, count = pattern.subn(f"【赛前看法】\n{cleaned}", draft.content)
        if count != 1:
            raise ValueError("未找到赛前看法区块")
        metadata = dict(draft.metadata)
        metadata["humanized_analysis"] = cleaned
        return replace(draft, content=content, metadata=metadata)

    def validate_protected_facts(
        self,
        original_draft: WorldCupPostDraft,
        rewritten_title: str,
        rewritten_content: str,
    ) -> bool:
        """结构化比较改写后的固定事实区块；无法确认时返回 False。"""

        rewritten_title = str(rewritten_title or "").strip()
        original_content = str(original_draft.content or "")
        rewritten_content = str(rewritten_content or "")
        expected = original_draft.protected_facts
        if (
            str(expected["home_team"]) not in rewritten_title
            or str(expected["away_team"]) not in rewritten_title
        ):
            return False
        parsed = self._parse_fact_block(rewritten_content)
        if parsed is None:
            return False
        comparable_keys = (
            "home_team",
            "away_team",
            "kickoff",
            "stage",
            "home_goals",
            "away_goals",
            "home_win_probability",
            "draw_probability",
            "away_win_probability",
            "predicted_result",
            "agreement_score",
            "agent_count",
        )
        for key in comparable_keys:
            if parsed.get(key) != self._canonical_fact(expected.get(key), key):
                return False

        for term in self.prohibited_claim_terms:
            if term in rewritten_content and term not in original_content:
                return False
        return DISCLAIMER in rewritten_content

    def build_image_pages(self, draft: WorldCupPostDraft) -> List[str]:
        """构造封面之后的三张世界杯专用内容页。"""

        facts = draft.protected_facts
        findings = list(draft.metadata.get("key_findings") or [])[:3]
        warnings = list(draft.metadata.get("warnings") or [])
        risk = warnings[0] if warnings else "比分预测存在高方差，请理性参考。"
        return [
            "\n".join(
                [
                    "# 预测结论",
                    f"预测比分：{facts['home_team']} {facts['home_goals']}-{facts['away_goals']} {facts['away_team']}",
                    f"预测结果：{facts['predicted_result']}",
                ]
            ),
            "\n".join(
                [
                    "# 胜平负概率",
                    f"主胜概率：{self._format_percent(facts['home_win_probability'])}",
                    f"平局概率：{self._format_percent(facts['draw_probability'])}",
                    f"客胜概率：{self._format_percent(facts['away_win_probability'])}",
                ]
            ),
            "\n".join(
                [
                    "# 分析依据",
                    *[f"{index}. {item}" for index, item in enumerate(findings, 1)],
                    f"综合意见一致率：{self._format_optional_percent(facts['agreement_score'])}",
                    f"风险提示：{risk}",
                ]
            ),
        ]

    def _build_fact_block(self, facts: Dict[str, Any]) -> str:
        result_label = "平局" if facts["predicted_result"] == "平局" else facts["predicted_result"]
        return "\n".join(
            [
                FACT_BLOCK_START,
                f"比赛：{facts['home_team']}对阵{facts['away_team']}",
                f"阶段：{facts['stage']}",
                f"开球时间：{facts['kickoff']}",
                f"预测比分：{facts['home_team']} {facts['home_goals']}-{facts['away_goals']} {facts['away_team']}",
                f"预测结果：{result_label}",
                f"主胜概率：{self._format_percent(facts['home_win_probability'])}",
                f"平局概率：{self._format_percent(facts['draw_probability'])}",
                f"客胜概率：{self._format_percent(facts['away_win_probability'])}",
                f"综合意见一致率：{self._format_optional_percent(facts['agreement_score'])}",
                f"参考分析数量：{facts['agent_count'] if facts['agent_count'] is not None else '未知'}",
                FACT_BLOCK_END,
            ]
        )

    def _parse_fact_block(self, content: str) -> Dict[str, Any] | None:
        pattern = re.compile(
            re.escape(FACT_BLOCK_START)
            + r"\s*(.*?)\s*"
            + re.escape(FACT_BLOCK_END),
            re.DOTALL,
        )
        match = pattern.search(content)
        if not match:
            return None
        values: Dict[str, str] = {}
        for line in match.group(1).splitlines():
            if "：" not in line:
                continue
            key, value = line.split("：", 1)
            values[key.strip()] = value.strip()
        required = {
            "比赛",
            "阶段",
            "开球时间",
            "预测比分",
            "预测结果",
            "主胜概率",
            "平局概率",
            "客胜概率",
            "综合意见一致率",
            "参考分析数量",
        }
        if not required.issubset(values):
            return None
        teams = re.fullmatch(r"(.+?)对阵(.+)", values["比赛"])
        score = re.fullmatch(r"(.+?)\s+(\d+)-(\d+)\s+(.+)", values["预测比分"])
        if not teams or not score:
            return None
        if teams.group(1) != score.group(1) or teams.group(2) != score.group(4):
            return None
        try:
            return {
                "home_team": teams.group(1),
                "away_team": teams.group(2),
                "kickoff": values["开球时间"],
                "stage": values["阶段"],
                "home_goals": int(score.group(2)),
                "away_goals": int(score.group(3)),
                "home_win_probability": self._percent_to_float(values["主胜概率"]),
                "draw_probability": self._percent_to_float(values["平局概率"]),
                "away_win_probability": self._percent_to_float(values["客胜概率"]),
                "predicted_result": values["预测结果"],
                "agreement_score": (
                    None
                    if values["综合意见一致率"] == "未知"
                    else self._percent_to_float(values["综合意见一致率"])
                ),
                "agent_count": (
                    None
                    if values["参考分析数量"] == "未知"
                    else int(values["参考分析数量"])
                ),
            }
        except (ValueError, InvalidOperation):
            return None

    @staticmethod
    def _require_dict(
        data: Dict[str, Any], key: str, message: str
    ) -> Dict[str, Any]:
        value = data.get(key)
        if not isinstance(value, dict):
            raise ValueError(message)
        return value

    @staticmethod
    def _require_value(
        data: Dict[str, Any],
        key: str,
        message: str,
        *,
        allow_zero: bool = False,
    ) -> None:
        if key not in data or data[key] is None:
            raise ValueError(message)
        if not allow_zero and isinstance(data[key], str) and not data[key].strip():
            raise ValueError(message)

    @staticmethod
    def _as_non_negative_int(value: Any, field: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field} 必须是非负整数")
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field} 必须是非负整数") from exc
        if number < 0 or number != number.to_integral_value():
            raise ValueError(f"{field} 必须是非负整数")
        return int(number)

    @classmethod
    def _optional_non_negative_int(cls, value: Any, field: str) -> int | None:
        if value is None:
            return None
        return cls._as_non_negative_int(value, field)

    @staticmethod
    def _as_probability(value: Any, field: str) -> Decimal:
        if isinstance(value, bool):
            raise ValueError(f"{field} 必须是 0 到 1 之间的数字")
        try:
            probability = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field} 必须是 0 到 1 之间的数字") from exc
        if not Decimal("0") <= probability <= Decimal("1"):
            raise ValueError(f"{field} 必须在 0 到 1 之间")
        return probability

    @classmethod
    def _optional_probability(cls, value: Any, field: str) -> Decimal | None:
        if value is None:
            return None
        return cls._as_probability(value, field)

    @staticmethod
    def _predicted_result(
        home: str,
        away: str,
        home_probability: Decimal,
        draw_probability: Decimal,
        away_probability: Decimal,
    ) -> str:
        values = [
            (home_probability, home),
            (draw_probability, "平局"),
            (away_probability, away),
        ]
        return max(values, key=lambda item: item[0])[1]

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _collect_key_findings(self, agents: Iterable[Any]) -> List[str]:
        findings: List[str] = []
        seen = set()
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            for finding in self._string_list(agent.get("key_findings")):
                key = re.sub(r"\s+", "", finding).casefold()
                if not key or key in seen:
                    continue
                seen.add(key)
                findings.append(finding)
                if len(findings) == 3:
                    return findings
        return findings

    @staticmethod
    def _translate_team(team: str) -> str:
        return TEAM_NAMES.get(str(team or "").strip(), str(team or "").strip())

    @classmethod
    def _translate_visible_text(cls, text: str) -> str:
        translated = str(text or "").strip()
        for english, chinese in sorted(
            TEAM_NAMES.items(), key=lambda item: len(item[0]), reverse=True
        ):
            translated = translated.replace(english, chinese)
        return (
            translated.replace("Elo", "实力评分")
            .replace("Agent", "分析意见")
            .replace("AI", "")
            .replace("模型生成", "个人整理")
        )

    @staticmethod
    def _data_completeness(intelligence: Any) -> tuple[Decimal, List[str]]:
        if not isinstance(intelligence, dict):
            return Decimal("0"), ["未获取结构化比赛数据。"]
        keys = (
            "home_metrics",
            "away_metrics",
            "home_availability",
            "away_availability",
            "head_to_head",
            "odds",
            "weather",
            "venue",
            "travel",
        )
        present = sum(
            1
            for key in keys
            if intelligence.get(key) not in (None, "", [], {})
        )
        completeness = Decimal(present) / Decimal(len(keys))
        missing = [key for key in keys if intelligence.get(key) in (None, "", [], {})]
        labels = {
            "home_metrics": "主队数据",
            "away_metrics": "客队数据",
            "home_availability": "主队人员情况",
            "away_availability": "客队人员情况",
            "head_to_head": "历史交锋",
            "odds": "参考数据",
            "weather": "天气",
            "venue": "比赛场地",
            "travel": "行程信息",
        }
        notes = (
            ["关键结构化数据较完整。"]
            if not missing
            else [f"缺失或为空：{'、'.join(labels[key] for key in missing)}。"]
        )
        return completeness, notes

    @staticmethod
    def _normalize_intelligence(report: Dict[str, Any]) -> Dict[str, Any] | None:
        team_features = report.get("team_features")
        if not isinstance(team_features, dict):
            return None
        return {
            "home_metrics": team_features.get("home"),
            "away_metrics": team_features.get("away"),
            "home_availability": None,
            "away_availability": None,
            "head_to_head": None,
            "odds": None,
            "weather": report.get("weather"),
            "venue": None,
            "travel": None,
        }

    @staticmethod
    def _format_percent(value: Any) -> str:
        decimal_value = Decimal(str(value))
        percent = decimal_value * Decimal("100")
        text = format(percent.normalize(), "f")
        if "." not in text:
            text += ".0"
        return f"{text}%"

    @classmethod
    def _format_optional_percent(cls, value: Any) -> str:
        return "未知" if value is None else cls._format_percent(value)

    @staticmethod
    def _percent_to_float(value: str) -> float:
        if not value.endswith("%"):
            raise ValueError("概率缺少百分号")
        return float(Decimal(value[:-1]) / Decimal("100"))

    @staticmethod
    def _canonical_fact(value: Any, key: str) -> Any:
        if key in {
            "home_win_probability",
            "draw_probability",
            "away_win_probability",
            "agreement_score",
        }:
            return None if value is None else float(Decimal(str(value)))
        return value
