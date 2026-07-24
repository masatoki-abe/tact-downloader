"""fixture から期待値ファイルを生成する。"""

import json
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent))

from tact_downloader.classifier import classify_site  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "titles.json"
FIXTURE_ANS = Path(__file__).parent / "fixtures" / "titles_ans.json"


class TitleEntry(TypedDict):
    site_id: str
    title: str


class SnapshotEntry(TitleEntry):
    year: str
    semester: str
    course_name: str


def build_snapshot(entries: list[TitleEntry]) -> list[SnapshotEntry]:
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


def main() -> None:
    entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results = build_snapshot(entries)
    payload = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    FIXTURE_ANS.write_text(payload, encoding="utf-8")
    print(f"Generated {len(results)} entries -> {FIXTURE_ANS}")


if __name__ == "__main__":
    main()
