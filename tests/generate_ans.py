"""fixture から期待値ファイルを生成する。"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tact_downloader.classifier import classify_site

FIXTURE = Path(__file__).parent / "fixtures" / "titles.json"
FIXTURE_ANS = Path(__file__).parent / "fixtures" / "titles_ans.json"

entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
results = []
for entry in entries:
    info = classify_site(entry["site_id"], entry["title"])
    results.append({
        "site_id": info.site_id,
        "title": info.raw_title,
        "year": info.year,
        "semester": info.semester,
    })

FIXTURE_ANS.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Generated {len(results)} entries -> {FIXTURE_ANS}")
