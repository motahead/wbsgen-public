import io
from http.client import HTTPException
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

import pytest

from wbsgen.gov_holidays import (
    GOV_HOLIDAYS_INFO_URL,
    MAX_RESPONSE_BYTES,
    GovHolidayImportError,
    load_gov_holidays,
)


CSV_HEADER = "国民の祝日・休日月日,国民の祝日・休日名称\r\n"


def csv_bytes(rows: str) -> bytes:
    return (CSV_HEADER + rows).encode("cp932")


def assert_import_error(operation, pattern: str = ".*") -> None:
    with pytest.raises(GovHolidayImportError, match=pattern) as raised:
        operation()
    assert GOV_HOLIDAYS_INFO_URL in str(raised.value)
    assert "--csv PATH" in str(raised.value)


def test_load_gov_holidays_from_local_csv_normalizes_dates(tmp_path):
    path = tmp_path / "holidays.csv"
    path.write_bytes(csv_bytes("2026/7/20,海の日\r\n"))

    with mock.patch("wbsgen.gov_holidays.request.build_opener") as build_opener:
        assert load_gov_holidays(url=None, csv_path=path) == {
            "holidays": [{"date": "2026-07-20", "name": "海の日"}]
        }
    build_opener.assert_not_called()


@pytest.mark.parametrize("url", ["http://example.invalid/holidays.csv", "", "https://["])
def test_load_gov_holidays_rejects_invalid_url(url):
    assert_import_error(lambda: load_gov_holidays(url=url, csv_path=None), "HTTPS|URL")


def test_load_gov_holidays_rejects_url_and_csv_together(tmp_path):
    assert_import_error(
        lambda: load_gov_holidays(url="https://example.invalid/a.csv", csv_path=tmp_path / "a.csv")
    )


@pytest.mark.parametrize(
    "rows, pattern",
    [
        ("2026/7/20,海の日,extra\r\n", "two columns"),
        ("2026/7/20,   \r\n", "holiday name"),
        ("2026/2/30,休日\r\n", "invalid date"),
        ("2026/7/20,海の日\r\n2026/07/20,重複\r\n", "duplicate date"),
    ],
)
def test_load_gov_holidays_rejects_invalid_rows(tmp_path, rows, pattern):
    path = tmp_path / "holidays.csv"
    path.write_bytes(csv_bytes(rows))
    assert_import_error(lambda: load_gov_holidays(url=None, csv_path=path), pattern)


def test_load_gov_holidays_rejects_invalid_encoding_and_header(tmp_path):
    invalid = tmp_path / "invalid.csv"
    invalid.write_bytes(b"\x81")
    assert_import_error(lambda: load_gov_holidays(url=None, csv_path=invalid), "CP932")
    header = tmp_path / "header.csv"
    header.write_bytes("date,name\r\n2026/7/20,海の日\r\n".encode("cp932"))
    assert_import_error(lambda: load_gov_holidays(url=None, csv_path=header), "header")


def test_load_gov_holidays_rejects_redirect_and_timeout():
    opener = mock.Mock()
    opener.open.side_effect = HTTPError("https://example.invalid/a.csv", 302, "Found", {}, io.BytesIO())
    with mock.patch("wbsgen.gov_holidays.request.build_opener", return_value=opener):
        assert_import_error(lambda: load_gov_holidays(url="https://example.invalid/a.csv", csv_path=None), "HTTP 302")
    opener.open.side_effect = URLError("timed out")
    with mock.patch("wbsgen.gov_holidays.request.build_opener", return_value=opener):
        assert_import_error(lambda: load_gov_holidays(url="https://example.invalid/a.csv", csv_path=None), "timed out")


def test_load_gov_holidays_rejects_oversized_and_read_error():
    response = mock.Mock()
    response.getcode.return_value = 200
    response.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
    response.__enter__ = mock.Mock(return_value=response)
    response.__exit__ = mock.Mock(return_value=None)
    opener = mock.Mock()
    opener.open.return_value = response
    with mock.patch("wbsgen.gov_holidays.request.build_opener", return_value=opener):
        assert_import_error(lambda: load_gov_holidays(url="https://example.invalid/a.csv", csv_path=None), "1 MiB")
    response.read.side_effect = HTTPException("incomplete response")
    with mock.patch("wbsgen.gov_holidays.request.build_opener", return_value=opener):
        assert_import_error(lambda: load_gov_holidays(url="https://example.invalid/a.csv", csv_path=None), "incomplete response")
