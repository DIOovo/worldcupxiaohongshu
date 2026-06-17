from __future__ import annotations

from pathlib import Path

from src.core.services.system_image_template_service import SystemImageTemplateService


class FakeConfig:
    def load_config(self):
        return None

    def get_templates_config(self):
        return {}


class LocalTemplateService(SystemImageTemplateService):
    def __init__(self, repo_root: Path):
        super().__init__(config=FakeConfig())
        self.repo_root = repo_root

    def _get_repo_root(self) -> Path:
        return self.repo_root

    def resolve_templates_dir(self):
        return None


def test_showcase_templates_include_plain_png_names(tmp_path):
    showcase_dir = tmp_path / "assets" / "system_templates" / "template_showcase"
    showcase_dir.mkdir(parents=True)
    (showcase_dir / "ghy.png").write_bytes(b"not-empty")

    templates = LocalTemplateService(tmp_path).list_showcase_templates()

    assert [item["id"] for item in templates] == ["ghy"]
    assert templates[0]["path"] == str(showcase_dir / "ghy.png")
