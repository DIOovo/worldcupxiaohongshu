"""一键刷新数据并生成世界杯预测报告。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence

import pandas as pd
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from build_world_cup_fixtures import build_fixtures_from_football_data_file
from football_data_client import refresh_world_cup_matches
import generate_world_cup_reports
from historical_match_loader import (
    add_match_result,
    clean_historical_matches,
    load_historical_matches,
    save_cleaned_matches,
)


ENV_FILE = PROJECT_ROOT / ".env"
HISTORICAL_DATA_FILE = PROJECT_ROOT / "data" / "raw" / "international_results.csv"
DEFAULT_HISTORICAL_RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/"
    "international_results/master/results.csv"
)
REQUIRED_HISTORY_COLUMNS = {
    "date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "tournament",
    "neutral",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从数据刷新开始，一键生成世界杯预测 JSON 报告"
    )
    parser.add_argument(
        "--historical-url",
        default=os.getenv("HISTORICAL_RESULTS_URL", DEFAULT_HISTORICAL_RESULTS_URL),
        help="国际比赛历史数据 CSV 的 GitHub Raw 地址",
    )
    parser.add_argument(
        "--skip-history-download",
        action="store_true",
        help="不下载历史数据，使用本地 international_results.csv",
    )
    parser.add_argument(
        "--skip-fixtures-download",
        action="store_true",
        help="不调用赛程接口，使用本地 world_cup_2026_matches.csv",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="保留已有报告；默认会重新生成同名报告",
    )
    parser.add_argument(
        "--max-reports",
        type=int,
        default=int(os.getenv("WORLDCUP_MAX_REPORTS", "1")),
        help="本次最多生成几份报告；默认 1，设为 0 表示全部",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=float(os.getenv("WORLDCUP_REQUEST_INTERVAL", "1.5")),
        help="每次文本接口调用之间的等待秒数",
    )
    return parser


def download_historical_results(url: str) -> Path:
    """下载并原子替换历史比赛 CSV。"""

    url = str(url or "").strip()
    if not url:
        raise ValueError("历史比赛数据地址不能为空")

    print(f"[1/5] 正在下载历史比赛数据：{url}")
    response = requests.get(url, timeout=(20, 120))
    response.raise_for_status()

    HISTORICAL_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = HISTORICAL_DATA_FILE.with_suffix(".csv.download")
    temporary_file.write_bytes(response.content)
    try:
        data = pd.read_csv(temporary_file)
        missing = REQUIRED_HISTORY_COLUMNS - set(data.columns)
        if missing:
            raise ValueError(f"历史比赛数据缺少字段：{sorted(missing)}")
        if data.empty:
            raise ValueError("历史比赛数据为空")
        temporary_file.replace(HISTORICAL_DATA_FILE)
    finally:
        if temporary_file.exists():
            temporary_file.unlink()

    print(
        f"历史比赛数据已更新：{HISTORICAL_DATA_FILE}，"
        f"共 {len(data)} 场"
    )
    return HISTORICAL_DATA_FILE


def clean_history() -> Path:
    """清洗历史比赛并保存检查结果。"""

    print("[3/5] 正在清洗历史比赛数据...")
    raw_matches = load_historical_matches()
    matches = add_match_result(clean_historical_matches(raw_matches))
    save_cleaned_matches(matches)
    output = PROJECT_ROOT / "data" / "processed" / "historical_matches_clean.csv"
    print(f"历史比赛清洗完成：{len(matches)} 场")
    return output


def run(argv: Sequence[str] | None = None) -> None:
    load_dotenv(ENV_FILE, override=True)
    args = build_parser().parse_args(argv)

    print("=" * 72)
    print("世界杯数据刷新与报告生成")
    print(f"项目目录：{PROJECT_ROOT}")
    print("=" * 72)

    if args.skip_history_download:
        print(f"[1/5] 跳过下载，使用本地历史数据：{HISTORICAL_DATA_FILE}")
        if not HISTORICAL_DATA_FILE.exists():
            raise FileNotFoundError(f"本地历史数据不存在：{HISTORICAL_DATA_FILE}")
    else:
        download_historical_results(args.historical_url)

    if args.skip_fixtures_download:
        fixtures_source = (
            PROJECT_ROOT / "data" / "raw" / "world_cup_2026_matches.csv"
        )
        print(f"[2/5] 跳过接口请求，使用本地赛程：{fixtures_source}")
        if not fixtures_source.exists():
            raise FileNotFoundError(f"本地网站赛程不存在：{fixtures_source}")
    else:
        print("[2/5] 正在从 football-data.org 更新世界杯赛程...")
        fixtures_source = refresh_world_cup_matches()

    clean_history()

    print("[4/5] 正在转换世界杯赛程...")
    fixtures = build_fixtures_from_football_data_file(fixtures_source)
    print(f"待预测赛程已更新：{len(fixtures)} 场")

    print("[5/5] 正在生成预测报告...")
    print("陈工调用了大模型：即将进入世界杯预测报告生成阶段。")
    generate_world_cup_reports.OVERWRITE_EXISTING = not args.no_overwrite
    generate_world_cup_reports.MAX_REPORTS = (
        None if args.max_reports <= 0 else args.max_reports
    )
    generate_world_cup_reports.REQUEST_INTERVAL_SECONDS = max(
        0.0, args.request_interval
    )
    generate_world_cup_reports.main()

    print("\n一键流程执行完成。")
    print(
        "报告目录："
        f"{PROJECT_ROOT / 'data' / 'reports' / 'world_cup_2026'}"
    )


def main() -> int:
    try:
        run()
    except Exception as exc:
        print(f"\n执行失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
