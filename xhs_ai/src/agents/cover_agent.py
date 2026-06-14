"""
封面/内容图生成 Agent。

职责：按文案和模板生成小红书图文发布需要的图片。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class CoverResult:
    images: List[str]
    source: str = ""
    title_override: str = ""
    content_override: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "images": list(self.images or []),
            "source": self.source,
            "title_override": self.title_override,
            "content_override": self.content_override,
        }


class CoverAgent:
    """负责把文案变成发布图片。"""

    name = "cover_agent"

    def generate_for_post(
        self,
        *,
        title: str,
        content: str,
        topic: str = "",
        cover_template_id: str = "",
        page_count: int = 3,
        content_pages: Optional[Sequence[str]] = None,
    ) -> CoverResult:
        title = str(title or "").strip()
        content = str(content or "").strip()
        topic = str(topic or title or content or "内容").strip()
        cover_template_id = str(cover_template_id or "").strip()
        try:
            page_count = int(page_count or 3)
        except Exception:
            page_count = 3
        page_count = max(1, page_count)

        if cover_template_id == "showcase_marketing_poster":
            result = self._generate_marketing_poster(topic=topic)
            if result.images:
                return result

        images = self._generate_system_template_images(
            title=title or topic,
            content=content or topic,
            cover_template_id=cover_template_id,
            page_count=page_count,
            content_pages=content_pages,
        )
        if images:
            return CoverResult(images=images, source="system_template")

        cover_path, content_paths = self.generate_local_placeholder_images(title or topic, count=max(2, page_count))
        return CoverResult(images=[cover_path] + list(content_paths or []), source="placeholder")

    def _generate_marketing_poster(self, *, topic: str) -> CoverResult:
        try:
            from src.config.config import Config
            from src.core.services.llm_service import llm_service
            from src.core.services.marketing_poster_service import marketing_poster_service

            poster_content = llm_service.generate_marketing_poster_content(topic=topic)
            try:
                asset_path = str(Config().get_templates_config().get("marketing_poster_asset_path") or "").strip()
            except Exception:
                asset_path = ""
            asset_path = os.path.expanduser(asset_path) if asset_path else ""
            if asset_path and os.path.exists(asset_path):
                poster_content["asset_image_path"] = asset_path

            cover_path, content_paths = marketing_poster_service.generate_to_local_paths(poster_content)
            images = [cover_path] + list(content_paths or [])
            images = [p for p in images if isinstance(p, str) and p]
            if not images:
                return CoverResult(images=[], source="")

            title_override = str((poster_content or {}).get("title") or "").strip()
            caption = str((poster_content or {}).get("caption") or "").strip()
            subtitle = str((poster_content or {}).get("subtitle") or "").strip()
            return CoverResult(
                images=images,
                source="marketing_poster",
                title_override=title_override,
                content_override=caption or subtitle,
            )
        except Exception:
            return CoverResult(images=[], source="")

    def _generate_system_template_images(
        self,
        *,
        title: str,
        content: str,
        cover_template_id: str,
        page_count: int,
        content_pages: Optional[Sequence[str]] = None,
    ) -> List[str]:
        try:
            from src.core.services.system_image_template_service import system_image_template_service

            cover_bg = ""
            try:
                if cover_template_id:
                    showcase_dir = system_image_template_service.resolve_showcase_dir()
                    if showcase_dir:
                        candidate = Path(showcase_dir) / f"{cover_template_id}.png"
                        if candidate.exists():
                            cover_bg = str(candidate)
            except Exception:
                cover_bg = ""

            generated = system_image_template_service.generate_post_images(
                title=title,
                content=content,
                content_pages=content_pages,
                page_count=page_count,
                bg_image_path=cover_bg,
                cover_bg_image_path=cover_bg,
            )
            if not generated:
                return []
            cover_path, content_paths = generated
            return [cover_path] + list(content_paths or [])
        except Exception:
            return []

    @staticmethod
    def generate_local_placeholder_images(title: str, count: int = 3):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception as exc:
            raise RuntimeError(f"Pillow 不可用: {exc}")

        base_dir = os.path.join(os.path.expanduser("~"), ".xhs_system", "generated_imgs")
        os.makedirs(base_dir, exist_ok=True)

        def _make(path: str, label: str):
            width, height = 1080, 1440
            img = Image.new("RGB", (width, height), (245, 245, 245))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            text = f"{label}\n{(title or '').strip()[:40]}"
            draw.multiline_text((60, 80), text, fill=(30, 30, 30), font=font, spacing=10)
            img.save(path, format="JPEG", quality=90)

        ts = int(time.time())
        unique = f"{ts}_{random.randint(1000, 9999)}"
        cover_path = os.path.join(base_dir, f"cover_{unique}.jpg")
        _make(cover_path, "封面")

        content_paths = []
        for i in range(max(1, int(count))):
            path = os.path.join(base_dir, f"content_{i + 1}_{unique}.jpg")
            _make(path, f"内容图{i + 1}")
            content_paths.append(path)

        return cover_path, content_paths
