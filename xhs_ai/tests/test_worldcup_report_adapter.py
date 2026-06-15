from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.integrations.worldcup_report_adapter import (
    DISCLAIMER,
    REQUIRED_TAGS,
    WorldCupReportAdapter,
)


FIXTURE = Path(__file__).parent / "fixtures" / "worldcup_report.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_loads_report_with_real_production_structure():
    report = WorldCupReportAdapter().load_report(FIXTURE)
    assert report["fixture"]["match_id"] == "wc2026-mex-rsa"
    assert report["consensus"]["match_predictions"][0]["home_goals"] == 2


def test_normalizes_match_prediction_report_schema(tmp_path):
    path = tmp_path / "real-report.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "world_cup_match_prediction",
                "generated_at": "2026-06-14T15:45:36+08:00",
                "match": {
                    "match_id": "wc2026_009",
                    "prediction_date": "2026-06-15",
                    "kickoff_time": None,
                    "home_team": "Belgium",
                    "away_team": "Egypt",
                    "stage": "Group Stage",
                },
                "prediction": {
                    "predicted_home_score": 2,
                    "predicted_away_score": 0,
                    "home_win_probability": 0.74614,
                    "draw_probability": 0.156723,
                    "away_win_probability": 0.097136,
                },
                "model_details": {
                    "model": "test-model",
                    "adjustment_reasons": ["历史数据支持主队占优"],
                },
                "team_features": {
                    "home": {"team": "Belgium"},
                    "away": {"team": "Egypt"},
                },
                "weather": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = WorldCupReportAdapter().load_report(path)
    draft = WorldCupReportAdapter().build_post_draft(report)
    assert report["fixture"]["home_team"] == "Belgium"
    assert draft.protected_facts["home_goals"] == 2
    assert draft.protected_facts["away_goals"] == 0
    assert draft.protected_facts["home_win_probability"] == 0.74614
    assert draft.protected_facts["home_team"] == "比利时"
    assert draft.protected_facts["away_team"] == "埃及"
    assert draft.protected_facts["stage"] == "小组赛"
    assert "Belgium" not in draft.content
    assert "Egypt" not in draft.content
    assert "具体开球时间未提供" in draft.content


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="世界杯报告不存在"):
        WorldCupReportAdapter().load_report(tmp_path / "missing.json")


def test_invalid_json_raises_clear_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON 解析失败"):
        WorldCupReportAdapter().load_report(path)


def test_missing_fixture_is_rejected():
    report = load_fixture()
    report.pop("fixture")
    with pytest.raises(ValueError, match="缺少 fixture"):
        WorldCupReportAdapter().validate_report(report)


def test_missing_match_predictions_is_rejected():
    report = load_fixture()
    report["consensus"]["match_predictions"] = []
    with pytest.raises(ValueError, match="match_predictions"):
        WorldCupReportAdapter().validate_report(report)


def test_probability_out_of_range_is_rejected():
    report = load_fixture()
    report["consensus"]["match_predictions"][0]["home_win_probability"] = 1.2
    with pytest.raises(ValueError, match="0 到 1"):
        WorldCupReportAdapter().validate_report(report)


def test_probability_sum_is_rejected():
    report = load_fixture()
    prediction = report["consensus"]["match_predictions"][0]
    prediction["home_win_probability"] = 0.2
    prediction["draw_probability"] = 0.2
    prediction["away_win_probability"] = 0.2
    with pytest.raises(ValueError, match="概率总和"):
        WorldCupReportAdapter().validate_report(report)


def test_negative_score_is_rejected():
    report = load_fixture()
    report["consensus"]["match_predictions"][0]["away_goals"] = -1
    with pytest.raises(ValueError, match="非负整数"):
        WorldCupReportAdapter().validate_report(report)


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        ((0.6, 0.25, 0.15), "墨西哥"),
        ((0.3, 0.5, 0.2), "平局"),
        ((0.2, 0.25, 0.55), "南非"),
    ],
)
def test_predicted_result_uses_highest_probability(probabilities, expected):
    report = load_fixture()
    prediction = report["consensus"]["match_predictions"][0]
    (
        prediction["home_win_probability"],
        prediction["draw_probability"],
        prediction["away_win_probability"],
    ) = probabilities
    draft = WorldCupReportAdapter().build_post_draft(report)
    assert draft.protected_facts["predicted_result"] == expected


def test_key_findings_are_deduplicated_and_limited_to_three():
    draft = WorldCupReportAdapter().build_post_draft(load_fixture())
    findings = draft.metadata["key_findings"]
    assert findings == [
        "墨西哥近期状态更稳定",
        "中场控制可能决定比赛节奏",
        "南非反击效率是主要变量",
    ]


def test_disclaimer_and_required_tags_are_present():
    draft = WorldCupReportAdapter().build_post_draft(load_fixture())
    assert DISCLAIMER in draft.content
    assert all(tag in draft.content for tag in REQUIRED_TAGS)
    assert "AI" not in draft.content
    assert "模型" not in draft.content
    assert "Agent" not in draft.content


def test_protected_fact_validation_detects_score_and_probability_changes():
    adapter = WorldCupReportAdapter()
    draft = adapter.build_post_draft(load_fixture())
    assert adapter.validate_protected_facts(draft, draft.title, draft.content)
    assert not adapter.validate_protected_facts(
        draft,
        draft.title,
        draft.content.replace("墨西哥 2-1 南非", "墨西哥 3-1 南非"),
    )
    assert not adapter.validate_protected_facts(
        draft,
        draft.title,
        draft.content.replace("主胜概率：55.0%", "主胜概率：65.0%"),
    )


def test_protected_fact_validation_rejects_new_unreported_claims():
    adapter = WorldCupReportAdapter()
    draft = adapter.build_post_draft(load_fixture())
    rewritten = draft.content + "\n某球员受伤缺阵。"
    assert not adapter.validate_protected_facts(draft, draft.title, rewritten)
    assert not adapter.validate_protected_facts(
        draft,
        "巴西对阵南非世界杯预测",
        draft.content,
    )
    assert not adapter.validate_protected_facts(
        draft,
        draft.title,
        draft.content + "\n墨西哥必胜。",
    )


def test_applies_humanized_analysis_without_changing_protected_facts():
    adapter = WorldCupReportAdapter()
    draft = adapter.build_post_draft(load_fixture())
    rewritten = adapter.apply_humanized_analysis(
        draft,
        "这场球更值得留意中场节奏，墨西哥整体状态稍稳，但南非的快速反击也可能带来变化。",
    )
    assert "更值得留意中场节奏" in rewritten.content
    assert adapter.validate_protected_facts(rewritten, rewritten.title, rewritten.content)


@pytest.mark.parametrize("text", ["这是AI分析。", "墨西哥必胜。", "Use this result."])
def test_rejects_unsafe_humanized_analysis(text):
    adapter = WorldCupReportAdapter()
    draft = adapter.build_post_draft(load_fixture())
    with pytest.raises(ValueError):
        adapter.apply_humanized_analysis(draft, text)
