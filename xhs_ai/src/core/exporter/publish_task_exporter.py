# src/core/exporter/publish_task_exporter.py

import json
from pathlib import Path
from datetime import datetime


def export_publish_task(
    title: str,
    content: str,
    platform: str = "toutiao",
    cover_image: str | None = None,
    images: list[str] | None = None,
    tags: list[str] | None = None,
    output_path: str = "output/publish_task.json",
):
    task = {
        "platform": platform,
        "title": title,
        "content": content,
        "cover_image": cover_image,
        "images": images or [],
        "tags": tags or [],
        "publish_mode": "manual_confirm",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "xhs_ai_backend"
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)

    return str(path.resolve())