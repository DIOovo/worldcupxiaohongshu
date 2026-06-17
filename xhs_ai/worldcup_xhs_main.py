#!/usr/bin/env python3
"""一键把 worldcup 预测报告转换成小红书发布 JSON。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any, Dict, Sequence


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.agents.worldcup_workflow_agent import WorldCupWorkflowAgent


DEFAULT_REPORTS_DIR = ROOT.parent / "worldcup" / "data" / "reports" / "world_cup_2026"
DEFAULT_IMAGE_PROVIDERS = ("qwen", "kimi", "custom", "anthropic", "deepseek", "openai")


def discover_latest_report(reports_dir: str | Path = DEFAULT_REPORTS_DIR) -> Path:
    """从 worldcup 报告目录中选择最新的一份比赛报告。"""

    root = Path(reports_dir).expanduser().resolve()
    reports = [
        path
        for path in sorted(root.glob("*.json"), key=lambda item: item.name, reverse=True)
        if path.name != "report_index.json"
    ]
    if not reports:
        raise FileNotFoundError(f"未找到 worldcup 报告 JSON：{root}")
    return reports[0]


def default_output_path(report_path: str | Path) -> Path:
    report = Path(report_path)
    return ROOT / "output" / f"{report.stem}_publish.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 worldcup 预测报告一键生成小红书图文发布 JSON"
    )
    parser.add_argument(
        "--report",
        default="",
        help="指定 worldcup JSON 报告路径；不传则自动使用最新报告",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="自动查找报告时使用的目录",
    )
    parser.add_argument(
        "--output",
        default="",
        help="publish JSON 输出路径；不传则写入 output/<报告名>_publish.json",
    )
    parser.add_argument(
        "--page-count",
        type=int,
        default=1,
        help="图片数量，默认 1 张封面",
    )
    parser.add_argument("--min-review-score", type=int, default=85)
    parser.add_argument("--max-rewrite-rounds", type=int, default=1)
    parser.add_argument("--cover-template-id", default="")
    parser.add_argument(
        "--image-mode",
        choices=("template", "ai"),
        default="template",
        help="template 使用本地模板；ai 使用图片接口生成背景",
    )
    parser.add_argument(
        "--image-provider",
        choices=DEFAULT_IMAGE_PROVIDERS,
        default="",
        help="图片接口提供商",
    )
    parser.add_argument("--image-model", default="", help="图片模型名称")
    parser.add_argument("--image-size", default="", help="图片尺寸")
    parser.add_argument(
        "--image-endpoint",
        default="",
        help="OpenAI Images 兼容接口地址或中转站地址",
    )
    parser.add_argument(
        "--image-api-key",
        default="",
        help="图片接口密钥；只在本次运行写入环境变量 XHS_IMAGE_API_KEY",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    workflow: WorldCupWorkflowAgent | None = None,
) -> Dict[str, Any]:
    args = build_parser().parse_args(argv)
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else discover_latest_report(args.reports_dir)
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else default_output_path(report_path).resolve()
    )

    if args.image_api_key:
        os.environ["XHS_IMAGE_API_KEY"] = args.image_api_key

    agent = workflow or WorldCupWorkflowAgent()
    payload = agent.build_publish_payload(
        report_path,
        page_count=args.page_count,
        min_review_score=args.min_review_score,
        max_rewrite_rounds=args.max_rewrite_rounds,
        cover_template_id=args.cover_template_id,
        image_mode=args.image_mode,
        image_provider=args.image_provider,
        image_model=args.image_model,
        image_size=args.image_size,
        image_endpoint=args.image_endpoint,
        output_path=output_path,
    )
    payload["_runner"] = {
        "report_path": str(report_path),
        "output_path": str(output_path),
        "image_mode": args.image_mode,
    }
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    try:
        payload = run(argv)
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1

    runner = payload.get("_runner") or {}
    images = payload.get("images") or []
    print("生成完成")
    print(f"报告文件：{runner.get('report_path', '')}")
    print(f"输出文件：{runner.get('output_path', '')}")
    print(f"标题：{payload.get('title', '')}")
    print(f"图片数量：{len(images)}")
    for index, image in enumerate(images, start=1):
        print(f"图片 {index}：{image}")
    print("未执行真实发布")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
