"""Import Japanese public holidays from the Cabinet Office CSV format."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from urllib import error, parse, request


DEFAULT_GOV_HOLIDAYS_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
GOV_HOLIDAYS_INFO_URL = "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
_CSV_HEADER = ["国民の祝日・休日月日", "国民の祝日・休日名称"]


class GovHolidayImportError(ValueError):
    """Raised when a Cabinet Office holiday CSV cannot be imported."""


class _NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_gov_holidays(*, url: str | None, csv_path: Path | None) -> dict[str, list[dict[str, str]]]:
    """Load, validate, and normalize a Cabinet Office compatible CSV."""
    if url is not None and csv_path is not None:
        raise _import_error("--url and --csv cannot be used together")
    if csv_path is None:
        raw = _fetch_csv(url if url is not None else DEFAULT_GOV_HOLIDAYS_URL)
    else:
        try:
            raw = csv_path.read_bytes()
        except OSError as exc:
            raise _import_error(f"cannot read CSV file: {csv_path}") from exc
    return {"holidays": _parse_csv(raw)}


def _fetch_csv(url: str) -> bytes:
    try:
        parsed = parse.urlsplit(url)
        parsed.port
    except ValueError as exc:
        raise _import_error("holiday CSV URL is invalid") from exc
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise _import_error("holiday CSV URL must use HTTPS")
    opener = request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.getcode() != 200:
                raise _import_error(f"holiday CSV request returned HTTP {response.getcode()}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except GovHolidayImportError:
        raise
    except error.HTTPError as exc:
        raise _import_error(f"holiday CSV request returned HTTP {exc.code}") from exc
    except (error.URLError, OSError, OverflowError, ValueError, HTTPException) as exc:
        detail = exc.reason if isinstance(exc, error.URLError) else exc
        raise _import_error(f"holiday CSV request failed: {detail}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise _import_error("holiday CSV response exceeds 1 MiB")
    return raw


def _parse_csv(raw: bytes) -> list[dict[str, str]]:
    try:
        text = raw.decode("cp932")
    except UnicodeDecodeError as exc:
        raise _import_error("holiday CSV must be encoded as CP932") from exc
    try:
        rows = csv.reader(text.splitlines(), strict=True)
        if next(rows, None) != _CSV_HEADER:
            raise _import_error("holiday CSV header does not match the Cabinet Office format")
        holidays: list[dict[str, str]] = []
        seen_dates: set[str] = set()
        for row_number, row in enumerate(rows, start=2):
            if len(row) != 2:
                raise _import_error(f"holiday CSV row {row_number} must have exactly two columns")
            date_text, name_text = row
            name = name_text.strip()
            if not name:
                raise _import_error(f"holiday CSV row {row_number} must have a holiday name")
            date_text = date_text.strip()
            if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", date_text):
                raise _import_error(f"holiday CSV row {row_number} has an invalid date")
            try:
                date_value = datetime.strptime(date_text, "%Y/%m/%d").date().isoformat()
            except ValueError as exc:
                raise _import_error(f"holiday CSV row {row_number} has an invalid date") from exc
            if date_value in seen_dates:
                raise _import_error(f"holiday CSV contains duplicate date: {date_value}")
            seen_dates.add(date_value)
            holidays.append({"date": date_value, "name": name})
    except csv.Error as exc:
        raise _import_error("holiday CSV is not valid CSV") from exc
    return holidays


def _import_error(message: str) -> GovHolidayImportError:
    return GovHolidayImportError(
        f"{message}. See {GOV_HOLIDAYS_INFO_URL} or provide a downloaded CSV with --csv PATH."
    )
