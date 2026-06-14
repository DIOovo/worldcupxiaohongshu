# scripts/generate_json.py

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.workflow_agent import WorkflowAgent


def main():

    topic = "AI Agent 如何改变内容运营"

    agent = WorkflowAgent()

    result = agent.run(topic)

    # 这里打印看看结构
    print(result)

    # 根据真实返回结构调整
    task = {
        "platform": "toutiao",
        "title": result.get("title", ""),
        "content": result.get("content", ""),
        "tags": result.get("tags", []),
        "publish_mode": "manual_confirm"
    }

    Path("output").mkdir(exist_ok=True)

    with open(
        "output/publish_task.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(task, f, ensure_ascii=False, indent=2)

    print("JSON 已生成")


if __name__ == "__main__":
    main()