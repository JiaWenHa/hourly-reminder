"""Regression tests for Work Log's scheduling and record-safety behavior."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import hourly_reminder as reminder
from setup_installer import read_existing_settings


class Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def schedule_app(*, working: bool) -> tuple[reminder.HourlyReminder, list[dict[str, object]]]:
    """Create the scheduler portion without opening a Tk window."""
    app = reminder.HourlyReminder.__new__(reminder.HourlyReminder)
    app.prompt = None
    app.decision_window = None
    app.working = working
    app.start_prompted_date = None
    app.end_prompted_date = None
    app.schedule_mode_var = Value("daily")
    app.start_hour_var = Value("09")
    app.start_minute_var = Value("00")
    app.end_hour_var = Value("18")
    app.end_minute_var = Value("00")
    calls: list[dict[str, object]] = []
    app._show_schedule_decision = lambda **kwargs: calls.append(kwargs)
    return app, calls


class ScheduleWindowTests(unittest.TestCase):
    def test_start_reminder_appears_only_in_half_hour_window(self) -> None:
        app, calls = schedule_app(working=False)
        app._check_work_schedule(datetime(2026, 9, 3, 8, 29))
        self.assertEqual(calls, [])

        app._check_work_schedule(datetime(2026, 9, 3, 8, 30))
        self.assertEqual(calls, [{"is_start": True, "scheduled_time": "09:00"}])

    def test_start_reminder_does_not_appear_after_window(self) -> None:
        app, calls = schedule_app(working=False)
        app._check_work_schedule(datetime(2026, 9, 3, 9, 31))
        self.assertEqual(calls, [])

    def test_end_reminder_appears_only_in_half_hour_window(self) -> None:
        app, calls = schedule_app(working=True)
        app._check_work_schedule(datetime(2026, 9, 3, 17, 30))
        self.assertEqual(calls, [{"is_start": False, "scheduled_time": "18:00"}])

        app, calls = schedule_app(working=True)
        app._check_work_schedule(datetime(2026, 9, 3, 18, 31))
        self.assertEqual(calls, [])


class RecordSafetyTests(unittest.TestCase):
    def test_monthly_log_is_created_without_touching_legacy_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "settings.json"
            records = root / "records"
            records.mkdir()
            legacy = records / "activity_log.csv"
            legacy.write_text("old-record-must-remain\n", encoding="utf-8")
            settings.write_text(json.dumps({"log_directory": str(records)}), encoding="utf-8")

            with patch.object(reminder, "APP_DATA_DIR", root), patch.object(reminder, "SETTINGS_FILE", settings):
                monthly = reminder.get_log_file(datetime(2026, 9, 3, 10, 0))
                app = reminder.HourlyReminder.__new__(reminder.HourlyReminder)
                app._ensure_log_file(monthly)

            self.assertEqual(monthly.name, "activity_log_2026-09.csv")
            self.assertEqual(legacy.read_text(encoding="utf-8"), "old-record-must-remain\n")
            with monthly.open(newline="", encoding="utf-8-sig") as file:
                self.assertEqual(next(csv.reader(file)), ["记录周期开始", "提交时间", "这段时间做的事情"])

    def test_existing_settings_are_read_without_resetting_log_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            settings.write_text(json.dumps({"log_directory": "D:/records", "custom": True}), encoding="utf-8")
            self.assertEqual(read_existing_settings(settings), {"log_directory": "D:/records", "custom": True})

    def test_invalid_existing_settings_stop_upgrade_instead_of_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            original = "not valid json"
            settings.write_text(original, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_existing_settings(settings)
            self.assertEqual(settings.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
