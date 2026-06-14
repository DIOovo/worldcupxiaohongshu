"""从 worldcup JSON 报告构建小红书 publish payload。"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from typing import Any, Dict, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.worldcup_workflow_agent import WorldCupWorkflowAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成世界杯预测小红书图文")
    parser.add_argument("--report", required=True, help="worldcup JSON 报告路径")
    parser.add_argument(
        "--output",
        default="output/worldcup_publish.json",
        help="publish JSON 输出路径",
    )
    parser.add_argument("--page-count", type=int, default=4, help="图片总页数")
    parser.add_argument("--min-review-score", type=int, default=85)
    parser.add_argument("--max-rewrite-rounds", type=int, default=1)
    parser.add_argument("--cover-template-id", default="")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--build-only", action="store_true", help="仅构建，不打开浏览器")
    mode.add_argument("--preview", action="store_true", help="填充页面但不点击最终发布")
    mode.add_argument("--publish", action="store_true", help="显式执行真实发布")
    return parser


async def publish_with_poster(
    poster: Any,
    payload: Dict[str, Any],
    *,
    auto_publish: bool = False,
    workflow: WorldCupWorkflowAgent | None = None,
) -> Dict[str, Any]:
    """供 GUI/BrowserThread 使用其已登录 poster 调用。"""

    agent = workflow or WorldCupWorkflowAgent()
    return await agent.publish_with_poster(
        poster,
        payload,
        auto_publish=auto_publish,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    poster: Any = None,
    workflow: WorldCupWorkflowAgent | None = None,
) -> Dict[str, Any]:
    """执行 CLI；默认及 --build-only 均不触发浏览器。"""

    args = build_parser().parse_args(argv)
    agent = workflow or WorldCupWorkflowAgent()
    payload = agent.build_publish_payload(
        args.report,
        page_count=args.page_count,
        min_review_score=args.min_review_score,
        max_rewrite_rounds=args.max_rewrite_rounds,
        cover_template_id=args.cover_template_id,
        output_path=args.output,
    )
    if args.preview or args.publish:
        if poster is None:
            mode = "--publish" if args.publish else "--preview"
            raise RuntimeError(
                f"{mode} 需要由现有 GUI/BrowserThread 传入已登录 poster；"
                "payload 已生成，未启动新的浏览器发布器"
            )
        payload = asyncio.run(
            publish_with_poster(
                poster,
                payload,
                auto_publish=bool(args.publish),
                workflow=agent,
            )
        )
    return payload


def main() -> int:
    try:
        payload = run()
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1
    print(f"生成成功：{len(payload.get('images') or [])} 张图片")
    print(f"输出文件：{Path(build_parser().parse_args().output).expanduser().resolve()}")
    print("未执行真实发布")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
