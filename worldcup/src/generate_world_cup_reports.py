"""
批量生成2026世界杯比赛预测JSON报告。

执行流程：
1. 读取世界杯赛程CSV；
2. 跳过已经完成或已经生成报告的比赛；
3. 构造比赛最新赛前特征；
4. 调用大模型进行有限预期进球修正；
5. 使用泊松分布生成比分概率；
6. 每场比赛保存一个JSON；
7. 生成总报告索引。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from current_team_feature_builder import (
    create_current_feature_builder,
)
from llm_match_predictor import (
    LLMMatchPredictor,
    build_prediction_features,
)
from world_cup_teams import (
    is_world_cup_2026_team,
    normalize_team_name,
)


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parent.parent

FIXTURE_FILE = (
    PROJECT_ROOT
    / "data"
    / "fixtures"
    / "world_cup_2026_fixtures.csv"
)

REPORT_DIR = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "world_cup_2026"
)

REPORT_INDEX_FILE = (
    REPORT_DIR
    / "report_index.json"
)

REQUEST_INTERVAL_SECONDS = 1.5

OVERWRITE_EXISTING = False

MAX_REPORTS: int | None = None


def safe_filename(
    value: str,
) -> str:
    """
    将球队名称转换成适合作为文件名的形式。
    """

    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("'", "")
    )


def build_report_filename(
    prediction_date: str,
    home_team: str,
    away_team: str,
) -> str:
    """
    生成单场报告文件名。
    """

    home_text = safe_filename(
        home_team
    )

    away_text = safe_filename(
        away_team
    )

    return (
        f"{prediction_date}_"
        f"{home_text}_vs_{away_text}.json"
    )


def load_fixtures() -> pd.DataFrame:
    """
    读取并校验世界杯赛程。
    """

    if not FIXTURE_FILE.exists():
        raise FileNotFoundError(
            f"没有找到赛程文件：{FIXTURE_FILE}"
        )

    fixtures = pd.read_csv(
        FIXTURE_FILE
    )

    required_columns = {
        "match_id",
        "prediction_date",
        "home_team",
        "away_team",
        "tournament",
        "neutral",
        "status",
    }

    missing_columns = (
        required_columns
        - set(fixtures.columns)
    )

    if missing_columns:
        raise ValueError(
            "赛程文件缺少字段："
            f"{sorted(missing_columns)}"
        )

    fixtures = fixtures.copy()

    fixtures["prediction_date"] = (
        pd.to_datetime(
            fixtures["prediction_date"],
            errors="coerce",
        )
    )

    fixtures["home_team"] = (
        fixtures["home_team"]
        .astype(str)
        .map(normalize_team_name)
    )

    fixtures["away_team"] = (
        fixtures["away_team"]
        .astype(str)
        .map(normalize_team_name)
    )

    fixtures["status"] = (
        fixtures["status"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    fixtures = fixtures.dropna(
        subset=[
            "prediction_date",
            "home_team",
            "away_team",
        ]
    ).copy()

    invalid_teams = fixtures[
        ~fixtures["home_team"].map(
            is_world_cup_2026_team
        )
        |
        ~fixtures["away_team"].map(
            is_world_cup_2026_team
        )
    ]

    if not invalid_teams.empty:
        raise ValueError(
            "赛程中存在非世界杯球队：\n"
            f"{invalid_teams[['home_team', 'away_team']]}"
        )

    fixtures = fixtures[
        fixtures["status"]
        == "SCHEDULED"
    ].copy()

    return fixtures.sort_values(
        [
            "prediction_date",
            "match_id",
        ]
    ).reset_index(drop=True)


def build_report(
    fixture: pd.Series,
    prediction: dict[str, Any],
    match_features: dict[str, Any],
) -> dict[str, Any]:
    """
    构造适合后续内容生成的单场JSON报告。
    """

    generated_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    return {
        "schema_version": "1.0",

        "report_type": (
            "world_cup_match_prediction"
        ),

        "generated_at": generated_at,

        "match": {
            "match_id": str(
                fixture["match_id"]
            ),

            "prediction_date": (
                fixture[
                    "prediction_date"
                ].strftime("%Y-%m-%d")
            ),

            "kickoff_time": (
                None
                if pd.isna(
                    fixture.get(
                        "kickoff_time"
                    )
                )
                else str(
                    fixture.get(
                        "kickoff_time"
                    )
                )
            ),

            "home_team": str(
                fixture["home_team"]
            ),

            "away_team": str(
                fixture["away_team"]
            ),

            "tournament": str(
                fixture["tournament"]
            ),

            "stage": (
                None
                if pd.isna(
                    fixture.get("stage")
                )
                else str(
                    fixture.get("stage")
                )
            ),

            "group": (
                None
                if pd.isna(
                    fixture.get("group")
                )
                else str(
                    fixture.get("group")
                )
            ),

            "neutral": bool(
                int(fixture["neutral"])
            ),
        },

        "prediction": {
            "predicted_result": (
                prediction[
                    "predicted_result"
                ]
            ),

            "predicted_scoreline": (
                prediction[
                    "predicted_scoreline"
                ]
            ),

            "predicted_home_score": (
                prediction[
                    "predicted_home_score"
                ]
            ),

            "predicted_away_score": (
                prediction[
                    "predicted_away_score"
                ]
            ),

            "scoreline_probability": (
                prediction[
                    "scoreline_probability"
                ]
            ),

            "home_win_probability": (
                prediction[
                    "home_win_probability"
                ]
            ),

            "draw_probability": (
                prediction[
                    "draw_probability"
                ]
            ),

            "away_win_probability": (
                prediction[
                    "away_win_probability"
                ]
            ),

            "expected_home_goals": (
                prediction[
                    "expected_home_goals"
                ]
            ),

            "expected_away_goals": (
                prediction[
                    "expected_away_goals"
                ]
            ),

            "expected_total_goals": (
                prediction[
                    "expected_total_goals"
                ]
            ),

            "over_2_5_probability": (
                prediction.get(
                    "over_2_5_probability"
                )
            ),

            "under_2_5_probability": (
                prediction.get(
                    "under_2_5_probability"
                )
            ),

            "both_teams_score_probability": (
                prediction.get(
                    "both_teams_score_probability"
                )
            ),

            "top_scorelines": (
                prediction.get(
                    "alternate_scorelines",
                    [],
                )
            ),
        },

        "model_details": {
            "model": prediction.get(
                "model"
            ),

            "base_home_expected_goals": (
                prediction.get(
                    "base_home_expected_goals"
                )
            ),

            "base_away_expected_goals": (
                prediction.get(
                    "base_away_expected_goals"
                )
            ),

            "home_goal_adjustment": (
                prediction.get(
                    "home_goal_adjustment"
                )
            ),

            "away_goal_adjustment": (
                prediction.get(
                    "away_goal_adjustment"
                )
            ),

            "adjustment_confidence": (
                prediction.get(
                    "confidence"
                )
            ),

            "adjustment_reasons": (
                prediction.get(
                    "adjustment_reasons",
                    [],
                )
            ),
        },

        "team_features": {
            "home": match_features[
                "home_team_features"
            ],

            "away": match_features[
                "away_team_features"
            ],

            "differences": match_features[
                "derived_features"
            ],
        },

        "weather": match_features.get(
            "weather"
        ),

        "content_material": {
            "headline": (
                f"{fixture['home_team']} "
                f"vs {fixture['away_team']}："
                f"模型预测比分 "
                f"{prediction['predicted_scoreline']}"
            ),

            "summary": (
                f"模型预测"
                f"{fixture['home_team']} "
                f"{prediction['predicted_scoreline']} "
                f"{fixture['away_team']}。"
                f"主胜概率"
                f"{prediction['home_win_probability'] * 100:.1f}%，"
                f"平局概率"
                f"{prediction['draw_probability'] * 100:.1f}%，"
                f"客胜概率"
                f"{prediction['away_win_probability'] * 100:.1f}%。"
            ),

            "disclaimer": (
                "本报告为基于历史数据和概率模型的分析，"
                "不代表比赛必然结果。"
            ),
        },
    }


def save_report(
    report: dict[str, Any],
    report_file: Path,
) -> None:
    """
    保存单场JSON报告。
    """

    report_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with report_file.open(
        mode="w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )


def save_report_index(
    report_items: list[dict[str, Any]],
) -> None:
    """
    保存全部报告索引。
    """

    index_data = {
        "schema_version": "1.0",

        "generated_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),

        "report_count": len(
            report_items
        ),

        "reports": report_items,
    }

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with REPORT_INDEX_FILE.open(
        mode="w",
        encoding="utf-8",
    ) as file:
        json.dump(
            index_data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:
    """
    批量生成世界杯JSON报告。
    """

    fixtures = load_fixtures()

    if MAX_REPORTS is not None:
        fixtures = fixtures.head(
            MAX_REPORTS
        )

    print(
        "待生成报告的比赛数量：",
        len(fixtures),
    )

    if fixtures.empty:
        raise ValueError(
            "没有待处理的世界杯赛程"
        )

    predictor = LLMMatchPredictor()

    report_items: list[
        dict[str, Any]
    ] = []

    for index, fixture in (
        fixtures.iterrows()
    ):
        prediction_date = (
            fixture[
                "prediction_date"
            ].strftime("%Y-%m-%d")
        )

        report_filename = (
            build_report_filename(
                prediction_date=(
                    prediction_date
                ),
                home_team=(
                    fixture["home_team"]
                ),
                away_team=(
                    fixture["away_team"]
                ),
            )
        )

        report_file = (
            REPORT_DIR
            / report_filename
        )

        print(
            f"\n[{index + 1}/{len(fixtures)}] "
            f"{fixture['home_team']} "
            f"vs {fixture['away_team']}"
        )

        if (
            report_file.exists()
            and not OVERWRITE_EXISTING
        ):
            print(
                "报告已存在，跳过：",
                report_file,
            )

            report_items.append({
                "match_id": str(
                    fixture["match_id"]
                ),

                "home_team": (
                    fixture["home_team"]
                ),

                "away_team": (
                    fixture["away_team"]
                ),

                "prediction_date": (
                    prediction_date
                ),

                "report_file": str(
                    report_file
                ),

                "status": "EXISTING",
            })

            continue

        feature_builder = (
            create_current_feature_builder(
                cutoff_date=prediction_date
            )
        )

        match_features = (
            build_prediction_features(
                feature_builder=(
                    feature_builder
                ),
                home_team=(
                    fixture["home_team"]
                ),
                away_team=(
                    fixture["away_team"]
                ),
                prediction_date=(
                    prediction_date
                ),
                neutral=bool(
                    int(
                        fixture["neutral"]
                    )
                ),
                tournament=str(
                    fixture["tournament"]
                ),
                weather=None,
            )
        )

        try:
            prediction = predictor.predict(
                match_features
            )

            report = build_report(
                fixture=fixture,
                prediction=prediction,
                match_features=(
                    match_features
                ),
            )

            save_report(
                report=report,
                report_file=report_file,
            )

            print(
                "JSON报告已保存：",
                report_file,
            )

            print(
                "预测比分：",
                prediction[
                    "predicted_scoreline"
                ],
            )

            report_items.append({
                "match_id": str(
                    fixture["match_id"]
                ),

                "home_team": (
                    fixture["home_team"]
                ),

                "away_team": (
                    fixture["away_team"]
                ),

                "prediction_date": (
                    prediction_date
                ),

                "predicted_scoreline": (
                    prediction[
                        "predicted_scoreline"
                    ]
                ),

                "report_file": str(
                    report_file
                ),

                "status": "SUCCESS",
            })

        except Exception as error:
            print(
                "报告生成失败：",
                error,
            )

            report_items.append({
                "match_id": str(
                    fixture["match_id"]
                ),

                "home_team": (
                    fixture["home_team"]
                ),

                "away_team": (
                    fixture["away_team"]
                ),

                "prediction_date": (
                    prediction_date
                ),

                "report_file": str(
                    report_file
                ),

                "status": "FAILED",

                "error": str(error),
            })

        time.sleep(
            REQUEST_INTERVAL_SECONDS
        )

    save_report_index(
        report_items
    )

    success_count = sum(
        item["status"] == "SUCCESS"
        for item in report_items
    )

    existing_count = sum(
        item["status"] == "EXISTING"
        for item in report_items
    )

    failed_count = sum(
        item["status"] == "FAILED"
        for item in report_items
    )

    print("\n" + "=" * 70)

    print(
        "报告生成完成"
    )

    print(
        "新生成：",
        success_count,
    )

    print(
        "已存在：",
        existing_count,
    )

    print(
        "失败：",
        failed_count,
    )

    print(
        "报告索引：",
        REPORT_INDEX_FILE,
    )

    print("=" * 70)


if __name__ == "__main__":
    main()