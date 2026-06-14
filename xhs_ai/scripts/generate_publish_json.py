# scripts/generate_publish_json.py

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.workflow_agent import (
    ContentWorkflowAgent,
    HotspotWorkflowRequest,
)


def main():

    agent = ContentWorkflowAgent()

    request = HotspotWorkflowRequest(
        source="weibo",
        rank=1,
        use_context=True,
        page_count=3,
    )

    result = agent.build_hotspot_payload(request)

    publish_task = {
        "platform": "toutiao",
        "title": result["title"],
        "content": result["content"],
        "images": result["images"],
        "review": result["review"],
        "hotspot_title": result["hotspot_title"],
        "publish_mode": "manual_confirm",
    }

    Path("output").mkdir(exist_ok=True)

    with open(
        "output/publish_task.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            publish_task,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("生成成功")
    print(json.dumps(publish_task, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()