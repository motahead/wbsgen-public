"""Holiday and milestone source JSON update operations."""

from __future__ import annotations

import copy

from .parser import parse_holidays
from .update_common import _holidays, _milestones
from .validation import ValidationResult


def _find_holiday_index(holidays: list[object], date_text: str) -> int:
    for index, item in enumerate(holidays):
        if isinstance(item, dict) and item.get("date") == date_text:
            return index
    raise ValueError(f"holiday not found: {date_text}")


def add_holiday(data: dict[str, object], date_text: str, name: str | None) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate, create=True)
    if any(isinstance(item, dict) and item.get("date") == date_text for item in holidays):
        raise ValueError(f"holiday already exists: {date_text}")
    holiday: dict[str, object] = {"date": date_text}
    if name is not None:
        holiday["name"] = name
    holidays.append(holiday)
    return candidate, f"added holiday {date_text}"


def update_holiday(data: dict[str, object], date_text: str, name: str | None = None, clear_name: bool = False, *, new_date: str | None = None) -> tuple[dict[str, object], str]:
    if name is None and not clear_name and new_date is None:
        raise ValueError("must set or clear holiday name, or change the date")
    if name is not None and clear_name:
        raise ValueError("cannot both set and clear: name")
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate)
    target_index = _find_holiday_index(holidays, date_text)
    target = holidays[target_index]
    assert isinstance(target, dict)
    if new_date is not None and new_date != date_text:
        if any(index != target_index and isinstance(item, dict) and item.get("date") == new_date for index, item in enumerate(holidays)):
            raise ValueError(f"holiday already exists: {new_date}")
        target["date"] = new_date
    if clear_name:
        target.pop("name", None)
    else:
        target["name"] = name
    return candidate, f"updated holiday {date_text}"


def remove_holiday(data: dict[str, object], date_text: str) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate)
    holidays.pop(_find_holiday_index(holidays, date_text))
    return candidate, f"removed holiday {date_text}"


def show_holidays(data: dict[str, object]) -> list[dict[str, object]]:
    holidays = [item for item in _holidays(data) if isinstance(item, dict)]
    return sorted(copy.deepcopy(holidays), key=lambda item: str(item.get("date", "")))


def merge_holidays(data: dict[str, object], supplemental: dict[str, object]) -> tuple[dict[str, object], str]:
    if not isinstance(supplemental, dict):
        raise ValueError("invalid supplemental holidays: root must be an object")
    validation = ValidationResult()
    supplemental_holidays = parse_holidays(supplemental.get("holidays"), validation)
    if validation.has_errors:
        raise ValueError("invalid supplemental holidays")
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate, create=True)
    by_date = {item["date"]: index for index, item in enumerate(holidays) if isinstance(item, dict) and isinstance(item.get("date"), str)}
    for holiday in supplemental_holidays:
        item: dict[str, object] = {"date": holiday.date.isoformat()}
        if holiday.name is not None:
            item["name"] = holiday.name
        index = by_date.get(item["date"])
        if index is None:
            by_date[item["date"]] = len(holidays)
            holidays.append(item)
        else:
            holidays[index] = item
    return candidate, "merged holidays"


def _find_milestone_index(milestones: list[object], name: str, date_text: str | None) -> int:
    matches = [index for index, item in enumerate(milestones) if isinstance(item, dict) and item.get("name") == name and (date_text is None or item.get("date") == date_text)]
    if not matches:
        raise ValueError(f"milestone not found: {name}")
    if len(matches) > 1:
        raise ValueError(f"multiple milestones match: {name}; use --date to disambiguate")
    return matches[0]


def add_milestone(data: dict[str, object], date_text: str, name: str) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    milestones = _milestones(candidate, create=True)
    if any(isinstance(item, dict) and item.get("date") == date_text and item.get("name") == name for item in milestones):
        raise ValueError(f"milestone already exists: {date_text} {name}")
    milestones.append({"date": date_text, "name": name})
    return candidate, f"added milestone {name}"


def update_milestone(data: dict[str, object], name: str, date_text: str | None, new_date: str | None, new_name: str | None) -> tuple[dict[str, object], str]:
    if new_date is None and new_name is None:
        raise ValueError("at least one of --new-date or --new-name must be set")
    candidate = copy.deepcopy(data)
    milestones = _milestones(candidate)
    target = milestones[_find_milestone_index(milestones, name, date_text)]
    assert isinstance(target, dict)
    if new_date is not None:
        target["date"] = new_date
    if new_name is not None:
        target["name"] = new_name
    return candidate, f"updated milestone {name}"


def remove_milestone(data: dict[str, object], name: str, date_text: str | None) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    milestones = _milestones(candidate)
    milestones.pop(_find_milestone_index(milestones, name, date_text))
    return candidate, f"removed milestone {name}"


def show_milestones(data: dict[str, object]) -> list[dict[str, object]]:
    milestones = [item for item in _milestones(data) if isinstance(item, dict)]
    return sorted(copy.deepcopy(milestones), key=lambda item: str(item.get("date", "")))
