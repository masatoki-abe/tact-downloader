"""実際の TACT タイトルを用いて classifier をテストする。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tact_downloader.classifier import classify_site  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "titles.json"
FIXTURE_ANS = Path(__file__).parent / "fixtures" / "titles_ans.json"


def load_titles():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_expected():
    return json.loads(FIXTURE_ANS.read_text(encoding="utf-8"))


def run_classify(entries):
    results = []
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


def print_results(results):
    for r in results:
        print(f"{r['year']:10s} {r['semester'] or '        ':8s} {r['course_name']}")
        print(f"    ID={r['site_id']} | title={r['title']}")


def test_classifier_snapshot():
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


if __name__ == "__main__":
    import pytest  # noqa: E402

    raise SystemExit(pytest.main([__file__, "-v"]))
