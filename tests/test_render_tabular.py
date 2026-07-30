import csv
import io

import wbsgen
from wbsgen.render import tabular


SOURCE = {
    "project": {
        "name": "表エクスポート確認",
        "startDate": "2026-07-01",
        "endDate": "2026-07-31",
        "statusDate": "2026-07-10",
        "issueBaseUrl": "https://example.test/issues/",
    },
    "tasks": [
        {
            "id": "1.1",
            "name": "子|タスク\\確認",
            "assignee": "担当者A",
            "plannedStart": "2026-07-01",
            "plannedDuration": 10,
            "actualStart": "2026-07-02",
            "progress": 50,
            "issue": 42,
            "comment": "カンマ,引用\"改行\n確認",
        }
    ],
}


def _result(source=SOURCE):
    result = wbsgen.build_project_model(source)
    assert not result.validation.has_errors
    return result


def test_build_wbs_rows_uses_xlsx_headers_and_computed_parent_rows():
    rows = tabular.build_wbs_rows(_result())

    assert tabular.WBS_HEADERS == (
        "ID", "タスク名", "担当者", "計画開始", "計画終了", "実績開始",
        "実績終了", "進捗", "期待進捗", "差分", "遅れ(営業日)",
        "残り必要ペース", "Issue", "コメント",
    )
    assert len(rows) == 2
    assert rows[0][:3] == ("1", "タスクを定義してください", "")
    assert rows[1][:8] == (
        "1.1", "子|タスク\\確認", "担当者A", "2026-07-01", "2026-07-14",
        "2026-07-02", "", "50%",
    )
    assert rows[1][12] == "https://example.test/issues/42"
    assert rows[1][13] == "カンマ,引用\"改行\n確認"


def test_render_markdown_escapes_table_cells_and_links_issue_url():
    markdown = tabular.render_markdown(_result())

    assert markdown.startswith("| ID | タスク名 |")
    assert "子\\|タスク\\\\確認" in markdown
    assert "改行<br>確認" in markdown
    assert "[#42](https://example.test/issues/42)" in markdown


def test_render_csv_round_trips_quoted_cells_and_issue_url():
    csv_text = tabular.render_csv(_result())
    rows = list(csv.reader(io.StringIO(csv_text)))

    assert rows[0] == list(tabular.WBS_HEADERS)
    assert rows[2][1] == "子|タスク\\確認"
    assert rows[2][12] == "https://example.test/issues/42"
    assert rows[2][13] == "カンマ,引用\"改行\n確認"


def test_issue_without_valid_base_url_uses_number_label():
    source = {**SOURCE, "project": {**SOURCE["project"], "issueBaseUrl": "invalid"}}
    rows = tabular.build_wbs_rows(_result(source))

    assert rows[1][12] == "#42"
    assert "#42" in tabular.render_markdown(_result(source))
