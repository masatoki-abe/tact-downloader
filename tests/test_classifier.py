"""実際の TACT タイトルを用いて classifier をテストする。"""

import json
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent))

from tact_downloader.classifier import (  # noqa: E402
    classify_site,
    extract_semester,
)

FIXTURE = Path(__file__).parent / "fixtures" / "titles.json"
FIXTURE_ANS = Path(__file__).parent / "fixtures" / "titles_ans.json"


class TitleEntry(TypedDict):
    site_id: str
    title: str


class SnapshotEntry(TitleEntry):
    year: str
    semester: str
    course_name: str


def load_titles() -> list[TitleEntry]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_expected() -> list[SnapshotEntry]:
    return json.loads(FIXTURE_ANS.read_text(encoding="utf-8"))


def run_classify(entries: list[TitleEntry]) -> list[SnapshotEntry]:
    results: list[SnapshotEntry] = []
    for entry in entries:
        info = classify_site(entry["site_id"], entry["title"])
        results.append(
            {
                "site_id": info.site_id,
                "title": info.raw_title,
                "year": info.year,
                "semester": info.semester,
                "course_name": info.course_name,
            }
        )
    return results


def print_results(results: list[SnapshotEntry]) -> None:
    for r in results:
        print(f"{r['year']:10s} {r['semester'] or '        ':8s} {r['course_name']}")
        print(f"    ID={r['site_id']} | title={r['title']}")


def test_classifier_snapshot() -> None:
    entries = load_titles()
    results = run_classify(entries)

    assert FIXTURE_ANS.exists(), f"期待値ファイルがありません: {FIXTURE_ANS}"
    expected = load_expected()
    expected_keys = {"site_id", "title", "year", "semester", "course_name"}

    assert len(results) == len(entries)
    assert len(expected) == len(entries)
    assert all(set(item) == expected_keys for item in expected)
    assert [item["site_id"] for item in entries] == [
        item["site_id"] for item in expected
    ]
    assert [item["title"] for item in entries] == [item["title"] for item in expected]
    assert results == expected


def test_supported_semester_formats() -> None:
    cases = [
        ("授業 (2025年度春3期/月2)", "春3期"),
        ("授業（2025年度秋学期/その他）", "秋学期"),
        ("授業 (2025年度通年)", "通年"),
        ("授業 (第1ターム)", "第1ターム"),
        ("授業 (春A)", "春A"),
        ("授業 (集中)", "集中"),
        ("授業【後期】", "後期"),
        ("授業［春B］", "春B"),
        ("授業[秋2期]", "秋2期"),
        ("授業 (2025年度未知の期/月2)", ""),
    ]

    for title, expected in cases:
        assert extract_semester(title) == expected


def test_course_name_removes_only_recognized_semester_block() -> None:
    assert classify_site("site", "2025年度 集中講義 (春A)").course_name == "集中講義"
    assert (
        classify_site("site", "2025年度 データ分析 (未知の期)").course_name
        == "データ分析 (未知の期)"
    )


if __name__ == "__main__":
    import pytest  # noqa: E402

    raise SystemExit(pytest.main([__file__, "-v"]))
