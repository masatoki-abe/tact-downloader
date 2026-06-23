#!/usr/bin/env python3
"""Obsidian Shell Commands 連携用 TACT ダウンロードコマンド。

フォルダパスから自動的にスコープを判定し、該当する講義サイトをダウンロードする。

Usage:
    python tact_downloader/obsidian_cmd.py --path <vault_folder_path>
    python tact_downloader/obsidian_cmd.py --path <path> --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from tact_downloader import TACT_BASE_URL, VAULT_ROOT, DOWNLOAD_BASE
from tact_downloader.auth import login
from tact_downloader.classifier import classify_site, SiteInfo
from tact_downloader.client import TACTClient
from tact_downloader.downloader import build_download_path, ensure_dir, safe_relative_path


def parse_scope(folder_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """フォルダパスから (year, semester, course_name) のスコープを抽出する。"""
    vault = Path(VAULT_ROOT).resolve()
    base = Path(DOWNLOAD_BASE)
    target = Path(folder_path).resolve()

    vault_base = (vault / base).resolve()
    try:
        relative = target.relative_to(vault_base)
    except ValueError:
        if target == vault_base:
            return (None, None, None)
        print(f"エラー: パス '{target}' は大学/ 以下ではありません。")
        print(f"  VAULT_ROOT = {vault}")
        print(f"  DOWNLOAD_BASE = {base}")
        print(f"  期待されるベースパス = {vault_base}")
        sys.exit(1)

    parts = [p for p in relative.parts if p not in {"TACTリソース"}]
    parts = parts[:3]

    year: Optional[str] = parts[0] if len(parts) >= 1 else None
    semester: Optional[str] = parts[1] if len(parts) >= 2 else None
    course_name: Optional[str] = parts[2] if len(parts) >= 3 else None

    return (year, semester, course_name)


def filter_sites(
    site_infos: list[SiteInfo],
    year: Optional[str],
    semester: Optional[str],
    course_name: Optional[str],
) -> list[SiteInfo]:
    """スコープに合致するサイトのみを返す。"""
    result = []
    for info in site_infos:
        if year and info.year != year:
            continue
        if semester and info.semester != semester:
            continue
        if course_name and info.course_name != course_name:
            continue
        result.append(info)
    return result


def download_resources(
    client: TACTClient,
    info: SiteInfo,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """1サイトのリソースをダウンロードする。戻り値は (新規, スキップ) の件数。"""
    try:
        resources = client.get_site_resources(info.site_id)
    except Exception as e:
        print(f"  エラー: リソース取得失敗 - {e}")
        return (0, 0)

    dl_dir = ensure_dir(build_download_path(info))
    new_count = 0
    skipped_count = 0

    if not resources:
        print(f"  リソースなし")
        return (0, 0)

    for res in resources:
        url = res["url"]
        rel = safe_relative_path(res["relative_path"])
        save_path = dl_dir / rel

        if not force and save_path.exists():
            skipped_count += 1
            continue

        if dry_run:
            print(f"  [DL対象] {rel}")
            new_count += 1
            continue

        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            print(f"  [DL中] {rel} ...", end="", flush=True)
            client.download_resource(url, str(save_path))
            size_str = ""
            if save_path.exists():
                size = save_path.stat().st_size
                if size < 1024:
                    size_str = f"({size} B)"
                elif size < 1024 * 1024:
                    size_str = f"({size / 1024:.1f} KB)"
                else:
                    size_str = f"({size / (1024 * 1024):.1f} MB)"
            print(f" 完了 {size_str}")
            new_count += 1
        except Exception as e:
            print(f" 失敗 - {e}")

    return (new_count, skipped_count)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Obsidian Shell Commands 連携 TACT ダウンロード"
    )
    parser.add_argument("--path", required=True, help="対象フォルダの絶対パス")
    parser.add_argument("--dry-run", action="store_true", help="ダウンロードせず表示のみ")
    parser.add_argument("--force", action="store_true", help="既存ファイルを上書き")
    args = parser.parse_args()

    year, semester, course_name = parse_scope(args.path)

    scope_parts = [s for s in [year, semester, course_name] if s]
    scope_label = "  ".join(scope_parts) if scope_parts else "全サイト"
    print(f"スコープ: {scope_label}")
    print()

    print("TACT にログインしています...")
    session = login(TACT_BASE_URL, verbose=False)
    client = TACTClient(session)

    print("講義サイト一覧を取得しています...")
    sites = client.get_sites()

    site_infos: list[SiteInfo] = []
    for site in sites:
        site_id = site.get("entityId", site.get("id", ""))
        title = site.get("entityTitle", site.get("title", ""))
        if site_id and title:
            site_infos.append(classify_site(site_id, title))

    targets = filter_sites(site_infos, year, semester, course_name)

    if semester is None:
        valid = [t for t in targets if t.semester]
        skipped_nosem = len(targets) - len(valid)
        if skipped_nosem > 0:
            print(f"学期情報なしのため {skipped_nosem} 件スキップしました。")
        targets = valid

    if not targets:
        print("該当する講義サイトが見つかりませんでした。")
        return

    print(f"対象: {len(targets)} サイト")
    print()

    total_new = 0
    total_skipped = 0
    for info in targets:
        sem_str = f"[{info.semester}]" if info.semester else ""
        print(f"{info.year} {sem_str} {info.course_name}")
        n, s = download_resources(client, info, force=args.force, dry_run=args.dry_run)
        total_new += n
        total_skipped += s

    print()
    print(f"完了: {total_new} 件ダウンロード / {total_skipped} 件スキップ")


if __name__ == "__main__":
    main()
