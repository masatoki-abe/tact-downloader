import json
import os
from datetime import datetime, timezone
from pathlib import Path

from tact_downloader import VAULT_ROOT, DOWNLOAD_BASE, HISTORY_FILE
from tact_downloader.classifier import SiteInfo


def load_history() -> dict[str, dict]:
    """ダウンロード履歴を読み込む。"""
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_history(history: dict[str, dict]) -> None:
    """ダウンロード履歴を保存する。"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def mark_downloaded(resource_url: str, save_path: str) -> None:
    """ダウンロード完了を履歴に記録する。"""
    history = load_history()
    history[resource_url] = {
        "path": save_path,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_history(history)


def is_downloaded(resource_url: str) -> bool:
    """指定したURLがダウンロード済みかどうかを返す。"""
    history = load_history()
    return resource_url in history


def build_download_path(site_info: SiteInfo) -> Path:
    """サイト情報からダウンロード先ディレクトリパスを構築する。"""
    vault = Path(VAULT_ROOT)
    parts = [DOWNLOAD_BASE]
    if site_info.year:
        parts.append(site_info.year)
    if site_info.semester:
        parts.append(site_info.semester)
    if site_info.course_name:
        parts.append(site_info.course_name)
    else:
        parts.append(site_info.raw_title)

    parts.append("TACTリソース")

    return vault / Path(*parts)


def ensure_dir(path: Path) -> Path:
    """ディレクトリが存在しなければ作成する。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_segment(segment: str) -> str:
    """ファイル・ディレクトリ名の1セグメントをサニタイズする。"""
    invalid_chars = '<>:"\\|?*'
    for c in invalid_chars:
        segment = segment.replace(c, "_")
    segment = "".join(c for c in segment if ord(c) >= 32)
    segment = segment.strip(". ")
    return segment if segment else "unnamed_file"


def safe_relative_path(relative_path: str) -> str:
    """TACT上の相対パスを安全なファイルシステムパスに変換する。

    各セグメント（/区切り）を個別にサニタイズし、ディレクトリ階層を維持する。
    URLから抽出した相対パス（例: "week1/handout.pdf"）を想定。
    """
    segments = []
    for seg in relative_path.split("/"):
        if seg == "" or seg == "..":
            continue
        segments.append(_sanitize_segment(seg))
    if not segments:
        return "unnamed_file"
    return "/".join(segments)


def safe_filename(name: str, url: str) -> str:
    """ファイル名として安全な文字列を生成する。

    URLからクエリパラメータを除去し、ファイル名として不適切な文字を置換する。
    後方互換性のため維持。新規コードでは safe_relative_path を使用すること。
    """
    # クエリ文字列とフラグメントを除去
    from urllib.parse import urlparse, unquote

    parsed = urlparse(url)
    path = parsed.path
    if path:
        name = unquote(path.rstrip("/").rsplit("/", 1)[-1])

    # ファイル名として不適切な文字を置換
    invalid_chars = '<>:"/\\|?*'
    for c in invalid_chars:
        name = name.replace(c, "_")
    # 制御文字を除去
    name = "".join(c for c in name if ord(c) >= 32)
    # 先頭と末尾の空白・ピリオドを除去
    name = name.strip(". ")
    # 空の場合はデフォルト名
    if not name:
        name = "unnamed_file"
    return name
