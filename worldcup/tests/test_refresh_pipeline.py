from __future__ import annotations

from pathlib import Path

import pandas as pd

import build_world_cup_fixtures
import football_data_client
import main as refresh_main


class FakeResponse:
    status_code = 200

    def __init__(self, data=None, content=b""):
        self._data = data or {}
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_football_data_request_uses_supplied_token(monkeypatch):
    captured = {}

    def fake_get(url, headers, timeout):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse({"matches": [{"id": 1}]})

    monkeypatch.setattr(football_data_client.requests, "get", fake_get)
    result = football_data_client.get_world_cup_matches(token="secret-token")

    assert result["matches"][0]["id"] == 1
    assert captured["headers"] == {"X-Auth-Token": "secret-token"}


def test_builds_report_fixtures_from_football_data_csv(tmp_path, monkeypatch):
    source = tmp_path / "world_cup_matches.csv"
    pd.DataFrame(
        [
            {
                "match_id": 100,
                "local_date": "2026-06-15 20:00:00+0800",
                "status": "TIMED",
                "stage": "GROUP_STAGE",
                "group": "GROUP_E",
                "home_team": "Belgium",
                "away_team": "Egypt",
            },
            {
                "match_id": 101,
                "local_date": "2026-06-14 20:00:00+0800",
                "status": "FINISHED",
                "stage": "GROUP_STAGE",
                "group": "GROUP_A",
                "home_team": "Brazil",
                "away_team": "Morocco",
            },
        ]
    ).to_csv(source, index=False)
    output = tmp_path / "fixtures.csv"
    monkeypatch.setattr(build_world_cup_fixtures, "OUTPUT_FILE", output)

    fixtures = build_world_cup_fixtures.build_fixtures_from_football_data_file(
        source
    )

    assert len(fixtures) == 1
    assert fixtures.iloc[0]["home_team"] == "Belgium"
    assert fixtures.iloc[0]["away_team"] == "Egypt"
    assert fixtures.iloc[0]["stage"] == "Group Stage"
    assert fixtures.iloc[0]["kickoff_time"] == "2026-06-15 20:00:00+0800"
    assert output.exists()


def test_total_controller_runs_all_stages(monkeypatch, tmp_path):
    history = tmp_path / "international_results.csv"
    fixtures_source = tmp_path / "world_cup_2026_matches.csv"
    calls = []

    monkeypatch.setattr(refresh_main, "HISTORICAL_DATA_FILE", history)
    monkeypatch.setattr(
        refresh_main,
        "download_historical_results",
        lambda url: calls.append(("history", url)) or history,
    )
    monkeypatch.setattr(
        refresh_main,
        "refresh_world_cup_matches",
        lambda: calls.append(("fixtures", None)) or fixtures_source,
    )
    monkeypatch.setattr(
        refresh_main,
        "clean_history",
        lambda: calls.append(("clean", None)) or tmp_path / "clean.csv",
    )
    monkeypatch.setattr(
        refresh_main,
        "build_fixtures_from_football_data_file",
        lambda path: calls.append(("convert", path))
        or pd.DataFrame([{"match_id": "m1"}]),
    )
    monkeypatch.setattr(
        refresh_main.generate_world_cup_reports,
        "main",
        lambda: calls.append(("reports", None)),
    )

    refresh_main.run(
        [
            "--historical-url",
            "https://example.com/results.csv",
            "--max-reports",
            "2",
            "--request-interval",
            "0",
        ]
    )

    assert [item[0] for item in calls] == [
        "history",
        "fixtures",
        "clean",
        "convert",
        "reports",
    ]
    assert refresh_main.generate_world_cup_reports.OVERWRITE_EXISTING is True
    assert refresh_main.generate_world_cup_reports.MAX_REPORTS == 2
    assert refresh_main.generate_world_cup_reports.REQUEST_INTERVAL_SECONDS == 0
