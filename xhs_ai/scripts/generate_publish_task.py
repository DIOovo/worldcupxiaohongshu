# scripts/generate_publish_task.py

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.exporter.publish_task_exporter import export_publish_task


def fake_generate_content(topic: str):
    title = f"{topic}：普通人也能看懂的实用指南"
    content = f"""今天聊聊：{topic}

这篇内容主要包括：
1. 为什么这个话题值得关注
2. 普通人怎么理解
3. 可以怎么落地使用

#AI #自动化 #效率工具
"""
    tags = ["AI", "自动化", "效率工具"]
    return title, content, tags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, help="创作主题")
    parser.add_argument("--platform", default="toutiao", help="发布平台")
    parser.add_argument("--output", default="output/publish_task.json")
    args = parser.parse_args()

    title, content, tags = fake_generate_content(args.topic)

    output_file = export_publish_task(
        title=title,
        content=content,
        platform=args.platform,
        tags=tags,
        output_path=args.output,
    )

    print(f"已生成任务文件：{output_file}")


if __name__ == "__main__":
    main()