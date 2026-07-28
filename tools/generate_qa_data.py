from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ASSIGNEES = ["田中", "佐藤", "鈴木", "高橋", "伊藤"]

PHASES = [
    ("要件定義", ["業務ヒアリング", "要件整理", "要件レビュー"]),
    ("設計", ["画面設計", "DB設計", "API設計", "設計レビュー"]),
    ("実装", ["基盤実装", "画面実装", "API実装", "バッチ実装", "単体テスト"]),
    ("結合テスト", ["結合シナリオ作成", "結合テスト実施", "不具合修正"]),
    ("リリース準備", ["リリース判定", "リリース作業"]),
]

COMMENTS = [
    "外部ベンダー待ち",
    "仕様確認中",
    "レビュー指摘対応中",
    "テストデータ準備中",
    "関連チームと調整中",
]


def fmt(d: date) -> str:
    return d.isoformat()


def generate_project(seed: int, today: date) -> dict:
    """1〜2ヶ月規模のランダムな仮想案件JSONを生成する。

    タスクを先にスケジューリングしてから実際に使われた日付の範囲で
    project.startDate/endDateを逆算する(先にstartDate/endDateを固定すると
    TASK_DATE_OUT_OF_RANGE警告が意図せず発生するため)。
    """
    rng = random.Random(seed)

    provisional_start = today - timedelta(days=rng.randint(10, 15))
    status = today

    tasks: list[dict] = []
    cursor_date = provisional_start
    for phase_index, (phase_name, subtasks) in enumerate(PHASES, start=1):
        parent_id = str(phase_index)
        tasks.append({"id": parent_id, "name": phase_name})

        for sub_index, sub_name in enumerate(subtasks, start=1):
            child_id = f"{parent_id}.{sub_index}"
            duration = rng.randint(1, 3)
            planned_start = cursor_date + timedelta(days=rng.randint(0, 1))
            assignee = rng.choice(ASSIGNEES)
            planned_end_estimate = planned_start + timedelta(days=int(duration * 1.4))

            task: dict = {
                "id": child_id,
                "name": sub_name,
                "assignee": assignee,
                "plannedStart": fmt(planned_start),
                "plannedDuration": duration,
            }

            if rng.random() < 0.08:
                task.pop("plannedStart")
                task.pop("plannedDuration")
                task["progress"] = 0
            elif planned_end_estimate < status - timedelta(days=3):
                if rng.random() < 0.75:
                    actual_start = max(
                        planned_start, planned_start + timedelta(days=rng.randint(-1, 3))
                    )
                    actual_end = actual_start + timedelta(days=rng.randint(1, duration + 4))
                    task["actualStart"] = fmt(actual_start)
                    task["actualEnd"] = fmt(actual_end)
                    task["progress"] = 100
                else:
                    actual_start = planned_start + timedelta(days=rng.randint(3, 10))
                    task["actualStart"] = fmt(actual_start)
                    task["progress"] = rng.randint(10, 40)
            elif planned_start <= status <= planned_end_estimate:
                if rng.random() < 0.85:
                    actual_start = max(
                        planned_start, planned_start + timedelta(days=rng.randint(-2, 2))
                    )
                    elapsed_ratio = max(0.0, (status - actual_start).days / max(duration, 1))
                    task["actualStart"] = fmt(actual_start)
                    task["progress"] = min(
                        95, max(5, int(elapsed_ratio * 100 * rng.uniform(0.5, 1.1)))
                    )
                else:
                    task["progress"] = 0
            else:
                task["progress"] = 0

            if rng.random() < 0.5:
                task["issue"] = rng.randint(100, 199)
            if rng.random() < 0.4:
                task["comment"] = rng.choice(COMMENTS)

            tasks.append(task)
            cursor_date = planned_start + timedelta(days=max(duration - 1, 0))
        cursor_date += timedelta(days=rng.randint(0, 2))

    _force_unplanned_task(tasks)

    start = _min_used_date(tasks, provisional_start) - timedelta(days=2)
    end = _max_used_date(tasks, provisional_start) + timedelta(days=5)

    holidays = _generate_holidays(rng, start, end)
    _force_weekend_start(tasks)
    _force_holiday_start(tasks, holidays)

    # 強制付与でタスクの日付が後ろにずれる場合があるため、期間を再計算して
    # 生成後のholidays/タスクが常にstart..end範囲に収まるようにする。
    end = max(end, _max_used_date(tasks, provisional_start) + timedelta(days=2))

    milestones = [
        {"date": fmt(start + timedelta(days=3)), "name": "要件確定"},
        {"date": fmt(status + timedelta(days=2)), "name": "中間レビュー"},
        {"date": fmt(end - timedelta(days=3)), "name": "リリース"},
    ]

    return {
        "project": {
            "name": "QA確認仮想案件",
            "startDate": fmt(start),
            "endDate": fmt(end),
            "statusDate": fmt(status),
            "issueBaseUrl": "https://github.com/your_account/your_repo/issues/",
        },
        "holidays": holidays,
        "milestones": milestones,
        "tasks": tasks,
    }


def _min_used_date(tasks: list[dict], fallback: date) -> date:
    dates = [fallback]
    for task in tasks:
        if "plannedStart" in task:
            dates.append(date.fromisoformat(task["plannedStart"]))
        if "actualStart" in task:
            dates.append(date.fromisoformat(task["actualStart"]))
    return min(dates)


def _max_used_date(tasks: list[dict], fallback: date) -> date:
    dates = [fallback]
    for task in tasks:
        if "plannedStart" in task and "plannedDuration" in task:
            planned_start = date.fromisoformat(task["plannedStart"])
            dates.append(planned_start + timedelta(days=task["plannedDuration"] - 1))
        if "actualEnd" in task:
            dates.append(date.fromisoformat(task["actualEnd"]))
        if "actualStart" in task:
            dates.append(date.fromisoformat(task["actualStart"]))
    return max(dates)


def _generate_holidays(rng: random.Random, start: date, end: date) -> list[dict]:
    holidays: list[dict] = []
    cursor = start
    month_seen: set[tuple[int, int]] = set()
    while cursor <= end:
        key = (cursor.year, cursor.month)
        if key not in month_seen:
            holiday_date = cursor
            if holiday_date.weekday() >= 5:
                holiday_date += timedelta(days=7 - holiday_date.weekday())
            if holiday_date <= end:
                holidays.append(
                    {
                        "date": fmt(holiday_date),
                        "name": rng.choice(["特別休暇", "創立記念日", "夏季休業"]),
                    }
                )
                month_seen.add(key)
        cursor += timedelta(days=7)
    return holidays


def _force_unplanned_task(tasks: list[dict]) -> None:
    leaf_tasks = [t for t in tasks if "assignee" in t]
    if any("plannedStart" not in t for t in leaf_tasks):
        return
    for task in leaf_tasks:
        task.pop("plannedStart", None)
        task.pop("plannedDuration", None)
        task.pop("actualStart", None)
        task.pop("actualEnd", None)
        task["progress"] = 0
        return


def _force_weekend_start(tasks: list[dict]) -> None:
    if any(
        "plannedStart" in t and date.fromisoformat(t["plannedStart"]).weekday() >= 5
        for t in tasks
    ):
        return
    for task in tasks:
        if "plannedStart" in task:
            planned = date.fromisoformat(task["plannedStart"])
            while planned.weekday() < 5:
                planned += timedelta(days=1)
            task["plannedStart"] = fmt(planned)
            return


def _force_holiday_start(tasks: list[dict], holidays: list[dict]) -> None:
    if not holidays:
        return
    holiday_dates = {h["date"] for h in holidays}
    if any("plannedStart" in t and t["plannedStart"] in holiday_dates for t in tasks):
        return

    holiday_date = date.fromisoformat(holidays[0]["date"])
    for task in tasks:
        if "plannedStart" in task and date.fromisoformat(task["plannedStart"]).weekday() < 5:
            task["plannedStart"] = fmt(holiday_date)
            return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a randomized virtual project JSON for the wbsgen-qa-check skill.",
    )
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args(argv)


def write_project(data: dict, output: Path) -> None:
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    seed = args.seed if args.seed is not None else int(time.time())
    print(f"seed={seed}", file=sys.stderr)

    data = generate_project(seed, date.today())
    write_project(data, args.output)
    print(
        f"wrote {args.output} ({len(data['tasks'])} tasks, "
        f"{len(data['holidays'])} holidays, {len(data['milestones'])} milestones)",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"generate_qa_data: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
