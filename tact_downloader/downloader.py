import re
from pathlib import Path

from tact_downloader import DOWNLOAD_BASE, VAULT_ROOT
from tact_downloader.classifier import SiteInfo


def build_download_path(site_info: SiteInfo) -> Path:
    """サイト情報からダウンロード先ディレクトリパスを構築する。"""
    vault = Path(VAULT_ROOT).expanduser().resolve()
    base_parts = _validate_relative_base(DOWNLOAD_BASE)
    parts = base_parts
    if site_info.year:
        parts.append(_sanitize_segment(site_info.year))
    if site_info.semester:
        parts.append(_sanitize_segment(site_info.semester))
    if site_info.course_name:
        parts.append(_sanitize_segment(site_info.course_name))
    else:
        parts.append(_sanitize_segment(site_info.raw_title))

    parts.append("TACTリソース")

    result = (vault / Path(*parts)).resolve()
    _ensure_inside_vault(result, vault)
    return result


def ensure_dir(path: Path) -> Path:
    """ディレクトリが存在しなければ作成する。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_segment(segment: str) -> str:
    """ファイル・ディレクトリ名の1セグメントをサニタイズする。"""
    if not isinstance(segment, str) or segment in {".", ".."}:
        raise ValueError(f"不正なパスセグメントです: {segment!r}")
    if "/" in segment or "\\" in segment:
        raise ValueError(f"パスセグメントに区切り文字を含められません: {segment!r}")
    invalid_chars = '<>:"\\|?*'
    for c in invalid_chars:
        segment = segment.replace(c, "_")
    segment = "".join(c for c in segment if ord(c) >= 32)
    segment = segment.strip(". ")
    return segment if segment else "unnamed_file"


def _validate_relative_base(base: str) -> list[str]:
    """DOWNLOAD_BASEをvaultからの相対パスとして検証する。"""
    if not isinstance(base, str) or not base:
        raise ValueError("DOWNLOAD_BASEはvault内の相対パスで指定してください。")
    base_path = Path(base)
    if base_path.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", base):
        raise ValueError("DOWNLOAD_BASEはvault内の相対パスで指定してください。")
    parts = list(base_path.parts)
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("DOWNLOAD_BASEに空要素、'.'、'..'は指定できません。")
    return [_sanitize_segment(part) for part in parts]


def _ensure_inside_vault(path: Path, vault: Path) -> None:
    try:
        path.relative_to(vault)
    except ValueError as exc:
        raise ValueError(f"保存先がvault外です: {path}") from exc


def safe_resource_path(directory: Path, relative_path: str) -> Path:
    """リソースの保存先を検証し、vault内の絶対パスとして返す。"""
    vault = Path(VAULT_ROOT).expanduser().resolve()
    path = (directory / Path(*safe_relative_path(relative_path).split("/"))).resolve()
    _ensure_inside_vault(path, vault)
    return path


def safe_relative_path(relative_path: str) -> str:
    """TACT上の相対パスを安全なファイルシステムパスに変換する。

    各セグメント（/区切り）を個別にサニタイズし、ディレクトリ階層を維持する。
    URLから抽出した相対パス（例: "week1/handout.pdf"）を想定。
    """
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("リソースパスが空です。")
    if relative_path.startswith(("/", "\\")) or re.match(
        r"^[A-Za-z]:[\\/]", relative_path
    ):
        raise ValueError(f"リソースパスに絶対パスは指定できません: {relative_path!r}")

    segments = []
    for seg in relative_path.split("/"):
        if seg == "":
            continue
        if seg in {".", ".."}:
            raise ValueError(
                f"リソースパスに不正なセグメントがあります: {relative_path!r}"
            )
        segments.append(_sanitize_segment(seg))
    if not segments:
        return "unnamed_file"
    return "/".join(segments)


def validate_resource_paths(directory: Path, resources: list[dict]) -> None:
    """サニタイズ後のリソース保存先の衝突を検出する。"""
    seen: dict[Path, str] = {}
    for resource in resources:
        relative_path = resource.get("relative_path", "")
        path = safe_resource_path(directory, relative_path)
        previous = seen.get(path)
        if previous is not None and previous != relative_path:
            raise ValueError(
                f"リソースの保存先が衝突します: {previous!r} と {relative_path!r}"
            )
        seen[path] = relative_path


def validate_site_paths(site_infos: list[SiteInfo]) -> None:
    """サイト情報のサニタイズ後の保存先の衝突を検出する。"""
    seen: dict[Path, SiteInfo] = {}
    for site_info in site_infos:
        path = build_download_path(site_info)
        previous = seen.get(path)
        if previous is not None and previous.site_id != site_info.site_id:
            raise ValueError(
                f"サイトの保存先が衝突します: {previous.site_id!r} と {site_info.site_id!r}"
            )
        seen[path] = site_info
