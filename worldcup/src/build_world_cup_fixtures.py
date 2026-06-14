"""
从国际比赛原始数据中提取2026世界杯赛程。

筛选规则：
1. tournament 为 FIFA World Cup；
2. 日期属于2026年；
3. 比分为空，表示比赛尚未结束；
4. 主客队均属于2026世界杯参赛球队；
5. 输出 generate_world_cup_reports.py 所需的赛程CSV。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from world_cup_teams import (
    is_world_cup_2026_team,
    normalize_team_name,
)


# ============================================================
# 一、路径配置
# ============================================================

CURRENT_FILE = Path(__file__).resolve()

PROJECT_ROOT = CURRENT_FILE.parent.parent

# 根据你的项目实际情况依次查找原始比赛文件
POSSIBLE_SOURCE_FILES = [
    PROJECT_ROOT
    / "data"
    / "raw"
    / "results.csv",

    PROJECT_ROOT
    / "data"
    / "results.csv",

    PROJECT_ROOT
    / "data"
    / "raw"
    / "international_results.csv",

    PROJECT_ROOT
    / "data"
    / "processed"
    / "match_features_full.csv",
]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "fixtures"
    / "world_cup_2026_fixtures.csv"
)


# ============================================================
# 二、查找原始数据
# ============================================================

def find_source_file() -> Path:
    """
    从常见路径中寻找包含国际比赛数据的CSV。
    """

    for file_path in POSSIBLE_SOURCE_FILES:
        if file_path.exists():
            print(
                "找到原始比赛文件：",
                file_path,
            )

            return file_path

    searched_paths = "\n".join(
        str(path)
        for path in POSSIBLE_SOURCE_FILES
    )

    raise FileNotFoundError(
        "没有找到国际比赛原始数据文件。\n"
        "已经检查以下路径：\n"
        f"{searched_paths}"
    )


# ============================================================
# 三、读取并检查数据
# ============================================================

def load_match_data(
    source_file: Path,
) -> pd.DataFrame:
    """
    读取比赛数据并检查必要字段。
    """

    data = pd.read_csv(
        source_file
    )

    required_columns = {
        "date",
        "home_team",
        "away_team",
        "tournament",
    }

    missing_columns = (
        required_columns
        - set(data.columns)
    )

    if missing_columns:
        raise ValueError(
            "原始比赛文件缺少字段："
            f"{sorted(missing_columns)}\n"
            f"文件：{source_file}"
        )

    data = data.copy()

    data["date"] = pd.to_datetime(
        data["date"],
        errors="coerce",
    )

    data["home_team"] = (
        data["home_team"]
        .astype(str)
        .map(normalize_team_name)
    )

    data["away_team"] = (
        data["away_team"]
        .astype(str)
        .map(normalize_team_name)
    )

    return data


# ============================================================
# 四、识别未结束比赛
# ============================================================

def build_unfinished_mask(
    data: pd.DataFrame,
) -> pd.Series:
    """
    判断比赛是否尚未结束。

    如果存在比分字段，则比分为空代表未结束。
    如果不存在比分字段，则把全部符合条件的比赛作为候选。
    """

    has_home_score = (
        "home_score" in data.columns
    )

    has_away_score = (
        "away_score" in data.columns
    )

    if (
        has_home_score
        and has_away_score
    ):
        return (
            data["home_score"].isna()
            | data["away_score"].isna()
        )

    print(
        "警告：原始数据没有比分字段，"
        "无法通过比分判断比赛是否结束。"
    )

    return pd.Series(
        True,
        index=data.index,
    )


# ============================================================
# 五、提取世界杯赛程
# ============================================================

def extract_world_cup_fixtures(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    提取2026世界杯尚未结束的比赛。
    """

    unfinished_mask = (
        build_unfinished_mask(data)
    )

    tournament_mask = (
        data["tournament"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq(
            "FIFA World Cup".casefold()
        )
    )

    year_mask = (
        data["date"].dt.year
        == 2026
    )

    world_cup_team_mask = (
        data["home_team"].map(
            is_world_cup_2026_team
        )
        &
        data["away_team"].map(
            is_world_cup_2026_team
        )
    )

    fixtures = data[
        tournament_mask
        & year_mask
        & unfinished_mask
        & world_cup_team_mask
    ].copy()

    fixtures = fixtures.dropna(
        subset=[
            "date",
            "home_team",
            "away_team",
        ]
    )

    fixtures = fixtures.drop_duplicates(
        subset=[
            "date",
            "home_team",
            "away_team",
        ]
    )

    fixtures = fixtures.sort_values(
        [
            "date",
            "home_team",
            "away_team",
        ]
    ).reset_index(drop=True)

    return fixtures


# ============================================================
# 六、转换为报告脚本需要的结构
# ============================================================

def convert_fixture_format(
    fixtures: pd.DataFrame,
) -> pd.DataFrame:
    """
    转换成 generate_world_cup_reports.py 需要的字段。
    """

    output_rows: list[
        dict[str, object]
    ] = []

    for index, row in fixtures.iterrows():
        match_date = row["date"]

        output_rows.append({
            "match_id": (
                f"wc2026_{index + 1:03d}"
            ),

            "prediction_date": (
                match_date.strftime(
                    "%Y-%m-%d"
                )
            ),

            # 原始数据如果没有准确开球时间，
            # 先留空，不影响报告生成。
            "kickoff_time": "",

            "home_team": (
                row["home_team"]
            ),

            "away_team": (
                row["away_team"]
            ),

            "tournament": (
                "FIFA World Cup"
            ),

            "stage": (
                "Group Stage"
            ),

            # 原始国际比赛数据通常不含小组字段，
            # 先留空。
            "group": "",

            # 世界杯通常视为中立场。
            # 后续可根据联合东道主比赛单独调整。
            "neutral": 1,

            "status": "SCHEDULED",
        })

    return pd.DataFrame(
        output_rows
    )


# ============================================================
# 七、保存文件
# ============================================================

def save_fixtures(
    fixtures: pd.DataFrame,
) -> None:
    """
    保存世界杯赛程CSV。
    """

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fixtures.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "赛程文件已保存：",
        OUTPUT_FILE,
    )

    print(
        "赛程数量：",
        len(fixtures),
    )


# ============================================================
# 八、打印赛程
# ============================================================

def print_fixtures(
    fixtures: pd.DataFrame,
) -> None:
    """
    打印提取出的赛程。
    """

    if fixtures.empty:
        print(
            "没有提取到符合条件的世界杯赛程。"
        )

        return

    print("\n提取到的世界杯赛程：")

    for _, row in fixtures.iterrows():
        print(
            f"{row['prediction_date']} "
            f"{row['home_team']} "
            f"vs {row['away_team']}"
        )


# ============================================================
# 九、主程序
# ============================================================

def main() -> None:
    source_file = find_source_file()

    match_data = load_match_data(
        source_file
    )

    print(
        "原始比赛数量：",
        len(match_data),
    )

    raw_fixtures = (
        extract_world_cup_fixtures(
            match_data
        )
    )

    print(
        "符合条件的未结束世界杯比赛：",
        len(raw_fixtures),
    )

    output_fixtures = (
        convert_fixture_format(
            raw_fixtures
        )
    )

    save_fixtures(
        output_fixtures
    )

    print_fixtures(
        output_fixtures
    )


if __name__ == "__main__":
    main()