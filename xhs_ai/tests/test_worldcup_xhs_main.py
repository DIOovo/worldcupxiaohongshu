from __future__ import annotations

import json
import os
from pathlib import Path

import worldcup_xhs_main as runner


class FakeWorkflow:
    def __init__(self):
        self.calls = []

    def build_publish_payload(self, report_path, **kwargs):
        self.calls.append({"report_path": Path(report_path), **kwargs})
        output_path = kwargs.get("output_path")
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(
                json.dumps({"title": "测试标题"}, ensure_ascii=False),
                encoding="utf-8",
            )
        return {
            "title": "测试标题",
            "content": "测试正文",
            "images": ["/tmp/worldcup-cover.png"],
        }


def test_discover_latest_report_skips_report_index(tmp_path):
    (tmp_path / "report_index.json").write_text("{}", encoding="utf-8")
    (tmp_path / "2026-06-15_belgium_vs_egypt.json").write_text("{}", encoding="utf-8")
    (tmp_path / "2026-06-16_france_vs_japan.json").write_text("{}", encoding="utf-8")

    latest = runner.discover_latest_report(tmp_path)

    assert latest.name == "2026-06-16_france_vs_japan.json"


def test_run_uses_latest_report_and_default_output(tmp_path):
    report = tmp_path / "2026-06-15_belgium_vs_egypt.json"
    report.write_text("{}", encoding="utf-8")
    workflow = FakeWorkflow()

    payload = runner.run(["--reports-dir", str(tmp_path)], workflow=workflow)

    assert payload["title"] == "测试标题"
    assert workflow.calls[0]["report_path"] == report.resolve()
    assert workflow.calls[0]["output_path"].name == "2026-06-15_belgium_vs_egypt_publish.json"
    assert workflow.calls[0]["page_count"] == 1
    assert workflow.calls[0]["image_mode"] == "template"


def test_run_forwards_image_options_and_key(tmp_path, monkeypatch):
    report = tmp_path / "match.json"
    output = tmp_path / "publish.json"
    report.write_text("{}", encoding="utf-8")
    workflow = FakeWorkflow()
    monkeypatch.delenv("XHS_IMAGE_API_KEY", raising=False)

    runner.run(
        [
            "--report",
            str(report),
            "--output",
            str(output),
            "--image-mode",
            "ai",
            "--image-provider",
            "openai",
            "--image-endpoint",
            "https://example.com/v1",
            "--image-model",
            "gpt-image-1",
            "--image-size",
            "1024x1024",
            "--image-api-key",
            "sk-test",
        ],
        workflow=workflow,
    )

    call = workflow.calls[0]
    assert call["output_path"] == output.resolve()
    assert call["image_mode"] == "ai"
    assert call["image_provider"] == "openai"
    assert call["image_endpoint"] == "https://example.com/v1"
    assert call["image_model"] == "gpt-image-1"
    assert call["image_size"] == "1024x1024"
    assert output.exists()
    assert os.environ["XHS_IMAGE_API_KEY"] == "sk-test"
