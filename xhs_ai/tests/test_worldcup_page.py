from __future__ import annotations

import os
from pathlib import Path
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QTextEdit

playwright_module = types.ModuleType("playwright")
playwright_sync_api = types.ModuleType("playwright.sync_api")
playwright_sync_api.sync_playwright = lambda: None
sys.modules.setdefault("playwright", playwright_module)
sys.modules.setdefault("playwright.sync_api", playwright_sync_api)

from src.core.pages.home import HomePage
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


def test_worldcup_page_sends_payload_to_home_generator(monkeypatch):
    get_app()

    class FakeTip:
        def __init__(self, *args, **kwargs):
            pass

        def show(self):
            return None

    class FakeHome:
        def __init__(self):
            self.payload = None

        def generate_from_worldcup_payload(self, payload):
            self.payload = payload

    class FakeWindow:
        def __init__(self):
            self.home_page = FakeHome()
            self.switched = None

        def switch_page(self, index):
            self.switched = index

    monkeypatch.setattr("src.core.pages.worldcup_page.TipWindow", FakeTip)
    window = FakeWindow()
    page = WorldCupPage(app_window=window)
    page.current_payload = {
        "title": "奥地利能赢吗",
        "content": "奥地利对阵约旦。",
        "images": ["/tmp/cover.png"],
    }

    page.send_to_home()

    assert window.switched == 0
    assert window.home_page.payload["title"] == "奥地利能赢吗"


def test_home_generates_again_from_worldcup_payload(monkeypatch):
    get_app()

    class FakeTip:
        def __init__(self, *args, **kwargs):
            pass

        def show(self):
            return None

    called = {"generate": 0}
    monkeypatch.setattr("src.core.pages.home.TipWindow", FakeTip)

    class FakeHome:
        def __init__(self):
            self.input_text = QTextEdit()
            self.parent = None

        def generate_content(self):
            called["generate"] += 1

    page = FakeHome()

    HomePage.generate_from_worldcup_payload(
        page,
        {
            "title": "奥地利能赢吗",
            "content": "【预测事实】\n比赛：奥地利对阵约旦",
        }
    )

    text = page.input_text.toPlainText()
    assert "重新生成一篇适合小红书发布的中文内容" in text
    assert "奥地利能赢吗" in text
    assert "奥地利对阵约旦" in text
    assert called["generate"] == 1
