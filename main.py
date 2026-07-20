#!/usr/bin/env python3
"""TACTリソース自動ダウンロードツール。

Usage:
    python main.py                 対話的にサイト選択してダウンロード
    python main.py --list          講義サイト一覧を表示
    python main.py --all           全サイト一括ダウンロード
    python main.py --site SITE_ID  指定サイトのみダウンロード
    python main.py --dry-run       ダウンロードせずに内容のみ表示
"""

import argparse
import sys

from tact_downloader import TACT_BASE_URL
from tact_downloader.auth import login
from tact_downloader.classifier import SiteInfo, classify_site
from tact_downloader.client import TACTClient
from tact_downloader.downloader import (
    build_download_path,
    download_sites,
)
from tact_downloader.exceptions import TACTError


def check_config() -> None:
    """設定が正しいか検証する。"""
    if not TACT_BASE_URL:
        print("エラー: TACT_BASE_URL が設定されていません。")
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="TACTリソース自動ダウンロードツール")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="デバッグ用の詳細情報を表示"
    )
    parser.add_argument("--list", action="store_true", help="講義サイト一覧を表示")
    parser.add_argument("--all", action="store_true", help="全サイト一括ダウンロード")
    parser.add_argument("--site", type=str, help="指定したサイトIDのみダウンロード")
    parser.add_argument(
        "--dry-run", action="store_true", help="ダウンロードせず内容表示のみ"
    )
    parser.add_argument(
        "--force", action="store_true", help="ダウンロード済みでも再ダウンロード"
    )
    args = parser.parse_args()

    check_config()

    # ログイン
    print("TACT にログインしています...")
    try:
        session = login(TACT_BASE_URL, verbose=args.verbose)
        client = TACTClient(session)
    except TACTError as e:
        print(f"エラー: {e}")
        return 1

    # サイト一覧取得
    print("講義サイト一覧を取得しています...")
    try:
        sites = client.get_sites()
    except TACTError as e:
        print(f"エラー: 講義サイト一覧の取得に失敗しました - {e}")
        return 1
    if not sites:
        print("講義サイトが見つかりませんでした。")
        sys.exit(0)

    # サイト情報を分類
    site_infos: list[SiteInfo] = []
    for site in sites:
        site_id = site.get("entityId", site.get("id", ""))
        title = site.get("entityTitle", site.get("title", ""))
        if site_id and title:
            site_infos.append(classify_site(site_id, title))

    # --list: 一覧表示のみ
    if args.list:
        print(f"\n全 {len(site_infos)} 件の講義サイト:\n")
        for info in sorted(
            site_infos, key=lambda x: (x.year, x.semester, x.course_name)
        ):
            print(f"  [{info.site_id}]")
            print(f"    年度   : {info.year}")
            print(f"    学期   : {info.semester or '(未検出)'}")
            print(f"    授業名 : {info.course_name}")
            print(f"    DL先   : {build_download_path(info)}")
            print()
        return 0

    # ダウンロード対象の絞り込み
    if args.site:
        targets = [s for s in site_infos if s.site_id == args.site]
        if not targets:
            print(f"エラー: サイトID '{args.site}' が見つかりません。")
            sys.exit(1)
    elif args.all:
        targets = [s for s in site_infos if s.semester]
        if not targets:
            print("学期情報のある講義サイトが見つかりませんでした。")
            sys.exit(0)
        skipped = len(site_infos) - len(targets)
        if skipped > 0:
            print(f"学期情報なしのため {skipped} 件のサイトをスキップしました。")
    else:
        # 対話的に選択
        print(f"\n全 {len(site_infos)} 件の講義サイト:\n")
        for i, info in enumerate(
            sorted(site_infos, key=lambda x: (x.year, x.semester, x.course_name)), 1
        ):
            semester_str = f"[{info.semester}]" if info.semester else ""
            print(
                f"  {i:3d}. [{info.year}] {semester_str} {info.course_name}  ({info.site_id})"
            )
        print()
        while True:
            choice = input(
                "ダウンロードする番号を選択 (カンマ区切り複数可 / 'all'=全件 / 'q'=終了): "
            ).strip()
            if choice.lower() == "q":
                print("終了します。")
                sys.exit(0)
            if choice.lower() == "all":
                targets = site_infos
                break
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                targets = [
                    sorted(
                        site_infos, key=lambda x: (x.year, x.semester, x.course_name)
                    )[i]
                    for i in indices
                    if 0 <= i < len(site_infos)
                ]
                if targets:
                    break
                print("有効な番号を選択してください。")
            except ValueError:
                print("番号を数値で入力してください（例: 1,3,5）。")

    def show_site(info: SiteInfo) -> None:
        print(f"\n{'=' * 60}")
        print(f"  サイト: {info.course_name}")
        print(f"  年度  : {info.year} / 学期: {info.semester or '(未検出)'}")
        print(f"  ID    : {info.site_id}")
        print(f"{'=' * 60}")

        print(f"  DL先  : {build_download_path(info)}")

    def show_empty(_info: SiteInfo) -> None:
        print("  リソースが見つかりませんでした。")

    def show_resource(status: str, rel: str, detail: str | None) -> None:
        if status == "site_failed":
            print(f"  エラー: リソース一覧の取得に失敗しました - {detail}")
        elif status == "skipped":
            print(f"    [スキップ] {rel}")
        elif status == "dry_run":
            print(f"    [dry-run] {rel}")
        elif status == "succeeded":
            print(f"    [完了]     {rel} ({detail})")
        else:
            print(f"    [失敗]     {rel} - {detail}")

    # ダウンロード実行
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
        print(f"エラー: サイトの保存先パスが不正です - {e}")
        return 1

    print(f"\n{'=' * 60}")
    print(
        f"  結果: {result.succeeded} 件成功, {result.skipped} 件スキップ, {result.failed} 件失敗"
    )
    print(f"{'=' * 60}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
