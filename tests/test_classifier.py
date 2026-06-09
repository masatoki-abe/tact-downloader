"""実際の TACT タイトルを用いて classifier をテストする。"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tact_downloader.classifier import classify_site, SiteInfo

FIXTURE = Path(__file__).parent / "fixtures" / "titles.json"
FIXTURE_ANS = Path(__file__).parent / "fixtures" / "titles_ans.json"


def load_titles():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run_classify(entries):
    results = []
    for entry in entries:
        info = classify_site(entry["site_id"], entry["title"])
        results.append({
            "site_id": info.site_id,
            "title": info.raw_title,
            "year": info.year,
            "semester": info.semester,
            "course_name": info.course_name,
        })
    return results


def print_results(results):
    for r in results:
        print(f"{r['year']:10s} {r['semester'] or '        ':8s} {r['course_name']}")
        print(f"    ID={r['site_id']} | title={r['title']}")


def main():
    entries = load_titles()
    results = run_classify(entries)

    # 期待値ファイルが存在すれば検証、なければ出力のみ
    if FIXTURE_ANS.exists():
        expected = json.loads(FIXTURE_ANS.read_text(encoding="utf-8"))
        errors = []
        for r, e in zip(results, expected):
            if r["site_id"] != e["site_id"]:
                continue
            if r["year"] != e["year"] or r["semester"] != e.get("semester", ""):
                errors.append({
                    "site_id": r["site_id"],
                    "title": r["title"],
                    "got": {"year": r["year"], "semester": r["semester"]},
                    "expected": {"year": e["year"], "semester": e.get("semester", "")},
                })
        if errors:
            print(f"\n=== {len(errors)} MISMATCHES ===\n")
            for e in errors:
                print(f"  {e['title']}")
                print(f"    got:      year={e['got']['year']} semester={e['got']['semester']}")
                print(f"    expected: year={e['expected']['year']} semester={e['expected']['semester']}")
            sys.exit(1)
        print(f"\nAll {len(results)} entries matched expected values.")
    else:
        print(f"\n=== {len(results)} entries (no expected file) ===\n")
        print_results(results)
        # 出力を期待値ファイルとして保存するか尋ねる
        ans_path = FIXTURE_ANS.resolve()
        print(f"\nHint: run  python tests/generate_ans.py  to create {ans_path}")


if __name__ == "__main__":
    main()
