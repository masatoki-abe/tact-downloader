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

from tact_downloader import DOWNLOAD_BASE, TACT_BASE_URL, VAULT_ROOT
from tact_downloader.auth import login
from tact_downloader.classifier import SiteInfo, classify_site
from tact_downloader.client import TACTClient

# Re-exported for callers that previously patched this module-level helper.
from tact_downloader.downloader import build_download_path as _build_download_path
from tact_downloader.downloader import download_sites
from tact_downloader.exceptions import TACTError

__all__ = ["build_download_path", "download_sites"]


def build_download_path(info: SiteInfo) -> Path:
    """ダウンロード先構築関数を後方互換のため再公開する。"""
    return _build_download_path(info)


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
    result: list[SiteInfo] = []
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
) -> tuple[int, int, int]:
    """1サイトを共通ダウンロードサービスへ委譲する。"""
    result = download_sites(client, [info], force=force, dry_run=dry_run)
    return (result.succeeded, result.skipped, result.failed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Obsidian Shell Commands 連携 TACT ダウンロード"
    )
    parser.add_argument("--path", required=True, help="対象フォルダの絶対パス")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ダウンロード予定を表示（vault内は変更しない）",
    )
    parser.add_argument("--force", action="store_true", help="既存ファイルを上書き")
    args = parser.parse_args()

    year, semester, course_name = parse_scope(args.path)

    scope_parts = [s for s in [year, semester, course_name] if s]
    scope_label = "  ".join(scope_parts) if scope_parts else "全サイト"
    print(f"スコープ: {scope_label}")
    print()

    print("TACT にログインしています...")
    try:
        session = login(TACT_BASE_URL, verbose=False)
        client = TACTClient(session)
    except TACTError as e:
        print(f"エラー: {e}")
        return 1

    print("講義サイト一覧を取得しています...")
    try:
        sites = client.get_sites()
    except TACTError as e:
        print(f"エラー: 講義サイト一覧の取得に失敗しました - {e}")
        return 1

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
        return 0

    print(f"対象: {len(targets)} サイト")
    print()

    def show_site(info: SiteInfo) -> None:
        sem_str = f"[{info.semester}]" if info.semester else ""
        print(f"{info.year} {sem_str} {info.course_name}")

    def show_empty(_info: SiteInfo) -> None:
        print("  リソースなし")

    def show_resource(status: str, rel: str, detail: str | None) -> None:
        if status == "site_failed":
            print(f"  エラー: リソース取得失敗 - {detail}")
        elif status == "skipped":
            print(f"  [スキップ] {rel}")
        elif status == "dry_run":
            print(f"  [予定] {rel}")
        elif status == "succeeded":
            print(f"  [DL中] {rel} ... 完了 ({detail})")
        else:
            print(f"  [DL中] {rel} ... 失敗 - {detail}")

    try:
        result = download_sites(
            client,
            targets,
            force=args.force,
            dry_run=args.dry_run,
            on_site=show_site,
            on_empty=show_empty,
            on_resource=show_resource,
        )
    except ValueError as e:
        print(f"エラー: 保存先パスが不正です - {e}")
        return 1

    print()
    summary = (
        f"結果: {result.succeeded} 件成功 / {result.skipped} 件スキップ / "
        f"{result.failed} 件失敗"
    )
    if args.dry_run:
        summary += f" / {result.planned} 件ダウンロード予定"
    print(summary)
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
