import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from tact_downloader import DOWNLOAD_BASE, VAULT_ROOT
from tact_downloader.classifier import SiteInfo
from tact_downloader.models import ResourceRecord


class DownloadClient(Protocol):
    def get_site_resources(self, site_id: str) -> list[ResourceRecord]: ...

    def download_resource(
        self,
        resource_url: str,
        save_path: str,
        expected_size: int | str | None = None,
    ) -> str: ...


@dataclass
class DownloadResult:
    """ダウンロード処理の集計結果。"""

    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    planned: int = 0

    def __add__(self, other: "DownloadResult") -> "DownloadResult":
        return DownloadResult(
            self.succeeded + other.succeeded,
            self.skipped + other.skipped,
            self.failed + other.failed,
            self.planned + other.planned,
        )


def format_file_size(size: int) -> str:
    """ファイルサイズをCLI表示用の文字列へ変換する。"""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def download_sites(
    client: DownloadClient,
    site_infos: list[SiteInfo],
    *,
    force: bool = False,
    dry_run: bool = False,
    on_site: Callable[[SiteInfo], None] | None = None,
    on_empty: Callable[[SiteInfo], None] | None = None,
    on_resource: Callable[[str, str, str | None], None] | None = None,
) -> DownloadResult:
    """複数サイトのリソースを取得し、結果を集計する。

    コールバックは表示などの呼び出し元固有の処理だけを担当する。
    ダウンロードの判定、保存先検証、例外処理、集計はこの関数で統一する。
    """
    validate_site_paths(site_infos)
    result = DownloadResult()

    for info in site_infos:
        if on_site:
            on_site(info)
        try:
            resources = client.get_site_resources(info.site_id)
        except Exception as exc:
            if on_resource:
                on_resource("site_failed", "", str(exc))
            result.failed += 1
            continue

        if not resources:
            if on_empty:
                on_empty(info)
            continue

        dl_dir = build_download_path(info)
        try:
            validate_resource_paths(dl_dir, resources)
        except ValueError as exc:
            if on_resource:
                on_resource("site_failed", "", str(exc))
            result.failed += 1
            continue

        for resource in resources:
            relative_path = resource["relative_path"]
            rel = safe_relative_path(relative_path)
            save_path = safe_resource_path(dl_dir, relative_path)

            if not force and save_path.exists():
                if on_resource:
                    on_resource("skipped", rel, None)
                result.skipped += 1
                continue

            if dry_run:
                if on_resource:
                    on_resource("dry_run", rel, None)
                result.planned += 1
                continue

            save_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                client.download_resource(
                    resource["url"], str(save_path), expected_size=resource.get("size")
                )
                size = (
                    format_file_size(save_path.stat().st_size)
                    if save_path.exists()
                    else None
                )
                if on_resource:
                    on_resource("succeeded", rel, size)
                result.succeeded += 1
            except Exception as exc:
                if on_resource:
                    on_resource("failed", rel, str(exc))
                result.failed += 1

    return result


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
    if segment in {".", ".."}:
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
    if not base:
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
    if not relative_path:
        raise ValueError("リソースパスが空です。")
    if relative_path.startswith(("/", "\\")) or re.match(
        r"^[A-Za-z]:[\\/]", relative_path
    ):
        raise ValueError(f"リソースパスに絶対パスは指定できません: {relative_path!r}")

    segments: list[str] = []
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


def validate_resource_paths(
    directory: Path, resources: Sequence[Mapping[str, object]]
) -> None:
    """サニタイズ後のリソース保存先の衝突を検出する。"""
    seen: dict[Path, str] = {}
    for resource in resources:
        relative_path = resource.get("relative_path", "")
        if not isinstance(relative_path, str):
            raise ValueError("リソースパスが不正です。")
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
