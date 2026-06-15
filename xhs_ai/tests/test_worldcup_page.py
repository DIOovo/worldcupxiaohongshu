from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from src.core.pages.worldcup_page import WorldCupPage

APP = None


def get_app():
    global APP
    APP = QApplication.instance() or QApplication([])
    return APP


def test_worldcup_page_discovers_latest_reports(tmp_path, monkeypatch):
    get_app()
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    older = report_dir / "2026-06-14_match.json"
    latest = report_dir / "2026-06-15_match.json"
    older.write_text("{}", encoding="utf-8")
    latest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        WorldCupPage,
        "reports_directory",
        staticmethod(lambda: report_dir),
    )

    page = WorldCupPage()

    assert page.report_combo.count() == 2
    assert Path(page.report_combo.itemData(0)) == latest


def test_worldcup_page_build_options_switch_between_ai_and_template(
    tmp_path,
    monkeypatch,
):
    get_app()
    report = tmp_path / "report.json"
    report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        WorldCupPage,
        "discover_reports",
        classmethod(lambda cls: [report]),
    )
    page = WorldCupPage()
    template_options = page.build_options()
    assert template_options["image_mode"] == "template"
    assert template_options["image_provider"] == ""
    assert template_options["image_api_key"] == ""

    page.image_mode_combo.setCurrentIndex(1)
    page.endpoint_input.setText("https://relay.example.com/v1")
    page.model_input.setText("gpt-image-1")
    page.api_key_input.setText("session-key")

    ai_options = page.build_options()
    assert ai_options["page_count"] == 1
    assert ai_options["image_mode"] == "ai"
    assert ai_options["image_provider"] == "openai"
    assert ai_options["image_endpoint"] == "https://relay.example.com/v1"
    assert ai_options["image_api_key"] == "session-key"
