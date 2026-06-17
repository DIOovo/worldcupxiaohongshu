from __future__ import annotations

import sys
import types


playwright_module = types.ModuleType("playwright")
playwright_async_api = types.ModuleType("playwright.async_api")
playwright_sync_api = types.ModuleType("playwright.sync_api")
playwright_async_api.async_playwright = lambda: None
playwright_sync_api.sync_playwright = lambda: None
sys.modules.setdefault("playwright", playwright_module)
sys.modules.setdefault("playwright.async_api", playwright_async_api)
sys.modules.setdefault("playwright.sync_api", playwright_sync_api)

from src.core.browser import BrowserThread


def test_login_queue_rejects_duplicate_login_actions():
    thread = BrowserThread()

    assert thread.enqueue_login("18800000000", "+86") is True
    assert thread.enqueue_login("18800000000", "+86") is False

    login_actions = [
        action for action in thread.action_queue if action.get("type") == "login"
    ]
    assert len(login_actions) == 1
    assert thread.login_in_progress is True
