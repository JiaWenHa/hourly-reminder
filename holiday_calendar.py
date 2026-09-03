"""Download and normalize the Chinese public-holiday calendar.

The remote calendar contains both statutory holidays and make-up workdays.
Only the normalized exception dates are persisted; ordinary Monday-Friday dates
remain workdays without needing a huge calendar file.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.request import Request, urlopen


HOLIDAY_API = "https://timor.tech/api/holiday/year/{year}/"


def download_china_holiday_year(year: int, timeout: int = 12) -> dict[str, bool]:
    """Return ``{YYYY-MM-DD: is_holiday}`` for one Chinese calendar year."""
    request = Request(HOLIDAY_API.format(year=year), headers={"User-Agent": "WorkLog/1.0"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entries = payload.get("holiday", {})
    if not isinstance(entries, dict) or not entries:
        raise ValueError("节假日日历服务返回的数据格式无效")

    normalized: dict[str, bool] = {}
    for key, item in entries.items():
        if not isinstance(item, dict) or "holiday" not in item:
            continue
        date_key = key if len(key) == 10 else f"{year}-{key}"
        # Validate the date as well as normalizing inputs such as 01-01.
        parsed = date.fromisoformat(date_key)
        normalized[parsed.isoformat()] = bool(item["holiday"])
    if not normalized:
        raise ValueError("节假日日历服务未返回有效日期")
    return normalized


def is_china_legal_workday(day: date, calendar: dict[str, dict[str, bool]]) -> bool | None:
    """Return a legal-workday decision, or None if that year's data is absent."""
    year_entries = calendar.get(str(day.year))
    if not isinstance(year_entries, dict):
        return None
    exception = year_entries.get(day.isoformat())
    if exception is not None:
        return not bool(exception)
    return day.weekday() < 5
