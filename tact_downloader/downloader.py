from pathlib import Path

from tact_downloader import VAULT_ROOT, DOWNLOAD_BASE
from tact_downloader.classifier import SiteInfo


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



