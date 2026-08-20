import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from tact_downloader import DOWNLOAD_BASE, VAULT_ROOT
from tact_downloader.classifier import SiteInfo
from tact_downloader.models import AssignmentRecord, AttachmentRecord, ResourceRecord


class DownloadClient(Protocol):
    def get_site_resources(self, site_id: str) -> list[ResourceRecord]: ...

    def download_resource(
        self,
        resource_url: str,
        save_path: str,
        expected_size: int | str | None = None,
    ) -> str: ...

    def get_site_assignments(self, site_id: str) -> list[AssignmentRecord]: ...


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
            if not dry_run:
                build_download_path(info).mkdir(parents=True, exist_ok=True)
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


def download_assignment_sites(
    client: DownloadClient,
    site_infos: list[SiteInfo],
    *,
    force: bool = False,
    dry_run: bool = False,
    on_site: Callable[[SiteInfo], None] | None = None,
    on_empty: Callable[[SiteInfo], None] | None = None,
    on_resource: Callable[[str, str, str | None], None] | None = None,
) -> DownloadResult:
    """課題をMarkdownと添付ファイルとして保存し、結果を集計する。"""
    validate_assignment_site_paths(site_infos)
    result = DownloadResult()
    for info in site_infos:
        if on_site:
            on_site(info)
        try:
            assignments = client.get_site_assignments(info.site_id)
        except Exception as exc:
            if on_resource:
                on_resource("site_failed", "", str(exc))
            result.failed += 1
            continue
        if not assignments:
            if not dry_run:
                build_assignment_path(info).mkdir(parents=True, exist_ok=True)
            if on_empty:
                on_empty(info)
            continue
        assignment_dir = build_assignment_path(info)
        try:
            validate_assignment_paths(assignment_dir, assignments)
        except ValueError as exc:
            if on_resource:
                on_resource("site_failed", "", str(exc))
            result.failed += 1
            continue

        duplicate_titles = duplicate_assignment_titles(assignments)
        for assignment in assignments:
            folder = assignment_directory(
                assignment_dir,
                assignment,
                use_id=assignment_title_key(assignment) in duplicate_titles,
            )
            markdown_paths = assignment_markdown_paths(folder, assignment)
            if dry_run:
                if on_resource:
                    for path, _content in markdown_paths:
                        on_resource(
                            "dry_run",
                            str(path.relative_to(assignment_dir)),
                            None,
                        )
                result.planned += len(markdown_paths)
            else:
                for path, content in markdown_paths:
                    try:
                        _write_text_atomically(path, content)
                        if on_resource:
                            on_resource(
                                "succeeded",
                                str(path.relative_to(assignment_dir)),
                                None,
                            )
                        result.succeeded += 1
                    except Exception as exc:
                        if on_resource:
                            on_resource(
                                "failed",
                                str(path.relative_to(assignment_dir)),
                                str(exc),
                            )
                        result.failed += 1

            for category, attachments in assignment_attachments(assignment):
                for attachment in attachments:
                    try:
                        relative = attachment_relative_path(category, attachment)
                        save_path = safe_assignment_path(folder, relative)
                    except ValueError as exc:
                        if on_resource:
                            on_resource("failed", str(exc), str(exc))
                        result.failed += 1
                        continue
                    rel = str(save_path.relative_to(assignment_dir))
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
                            attachment["url"],
                            str(save_path),
                            expected_size=attachment.get("size"),
                        )
                        if on_resource:
                            on_resource("succeeded", rel, None)
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


def build_course_path(site_info: SiteInfo) -> Path:
    return build_download_path(site_info).parent


def build_assignment_path(site_info: SiteInfo) -> Path:
    result = (build_course_path(site_info) / "TACT課題").resolve()
    vault = Path(VAULT_ROOT).expanduser().resolve()
    _ensure_inside_vault(result, vault)
    return result


def assignment_directory(
    directory: Path, assignment: Mapping[str, object], *, use_id: bool = False
) -> Path:
    title = assignment.get("title")
    assignment_id = assignment.get("id")
    if not isinstance(title, str) or not isinstance(assignment_id, str):
        raise ValueError("課題のタイトルまたはIDが不正です。")
    folder_name = _sanitize_segment(title)
    if use_id:
        short_id = _sanitize_segment(assignment_id)[:12]
        folder_name = f"{folder_name}--{short_id}"
    return safe_assignment_path(directory, folder_name)


def safe_assignment_path(directory: Path, relative_path: str) -> Path:
    path = (directory / Path(*safe_relative_path(relative_path).split("/"))).resolve()
    vault = Path(VAULT_ROOT).expanduser().resolve()
    _ensure_inside_vault(path, vault)
    return path


def assignment_attachments(
    assignment: AssignmentRecord,
) -> list[tuple[str, list[AttachmentRecord]]]:
    attachments: list[tuple[str, list[AttachmentRecord]]] = [
        ("課題", assignment["attachments"])
    ]
    submissions = [
        submission
        for submission in assignment["submissions"]
        if submission.get("userSubmission") is True
    ]
    if submissions:
        submission = submissions[0]
        attachments.extend(
            [
                ("自分の提出", submission.get("submittedAttachments", [])),
                ("返却", submission.get("feedbackAttachments", [])),
            ]
        )
    return attachments


def attachment_relative_path(category: str, attachment: AttachmentRecord) -> str:
    name = attachment.get("name", "unnamed_file")
    return f"{category}/{name}" if category else name


def assignment_title_key(assignment: Mapping[str, object]) -> str:
    title = assignment.get("title")
    if not isinstance(title, str):
        raise ValueError("課題タイトルが不正です。")
    return _sanitize_segment(title)


def duplicate_assignment_titles(
    assignments: Sequence[Mapping[str, object]],
) -> set[str]:
    counts: dict[str, int] = {}
    for assignment in assignments:
        key = assignment_title_key(assignment)
        counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count > 1}


def validate_assignment_paths(
    directory: Path, assignments: Sequence[Mapping[str, object]]
) -> None:
    seen: dict[Path, str] = {}
    duplicate_titles = duplicate_assignment_titles(assignments)
    for assignment in assignments:
        path = assignment_directory(
            directory,
            assignment,
            use_id=assignment_title_key(assignment) in duplicate_titles,
        )
        assignment_id = assignment.get("id", "")
        if not isinstance(assignment_id, str):
            raise ValueError("課題IDが不正です。")
        previous = seen.get(path)
        if previous is not None and previous != assignment_id:
            raise ValueError(
                f"課題の保存先が衝突します: {previous!r} と {assignment_id!r}"
            )
        seen[path] = assignment_id


def validate_assignment_site_paths(site_infos: list[SiteInfo]) -> None:
    seen: dict[Path, str] = {}
    for info in site_infos:
        path = build_assignment_path(info)
        previous = seen.get(path)
        if previous is not None and previous != info.site_id:
            raise ValueError(
                f"課題の保存先が衝突します: {previous!r} と {info.site_id!r}"
            )
        seen[path] = info.site_id


def assignment_markdown_paths(
    folder: Path, assignment: AssignmentRecord
) -> list[tuple[Path, str]]:
    submission = next(
        (
            item
            for item in assignment["submissions"]
            if item.get("userSubmission") is True
        ),
        None,
    )
    lines = [f"# {assignment['title']}", "", f"- 課題ID: `{assignment['id']}`"]
    for label, key in (
        ("状態", "status"),
        ("公開日時", "openTimeString"),
        ("締切", "dueTimeString"),
        ("遅延提出期限", "dropDeadTimeString"),
        ("終了日時", "closeTimeString"),
        ("提出方式", "submissionType"),
        ("採点方式", "gradeScale"),
        ("満点", "maxGradePoint"),
    ):
        value = assignment.get(key)
        if value not in (None, ""):
            lines.append(f"- {label}: {format_assignment_datetime(value)}")
    lines.extend(["", assignment["instructions"] or "（なし）"])
    _append_attachment_links(lines, "添付ファイル", assignment["attachments"])
    paths = [(folder / "課題" / "本文.md", "\n".join(lines) + "\n")]
    if submission is not None:
        submission_lines: list[str] = [f"# {assignment['title']} の提出"]
        for label, key in (
            ("提出状態", "status"),
            ("提出日時", "dateSubmitted"),
            ("遅延提出", "late"),
            ("採点済み", "graded"),
            ("返却済み", "returned"),
            ("成績", "grade"),
        ):
            value = submission.get(key)
            if value not in (None, ""):
                submission_lines.append(
                    f"- {label}: {format_assignment_datetime(value)}"
                )
        submitted_text = submission.get("submittedText")
        if isinstance(submitted_text, str) and submitted_text:
            submission_lines.extend(["", submitted_text])
        _append_attachment_links(
            submission_lines,
            "添付ファイル",
            submission.get("submittedAttachments", []),
        )
        if isinstance(submitted_text, str) and submitted_text:
            paths.append(
                (folder / "自分の提出" / "本文.md", "\n".join(submission_lines) + "\n")
            )
        feedback_lines: list[str] = [f"# {assignment['title']} の返却"]
        for label, key in (("成績", "grade"), ("返却済み", "returned")):
            value = submission.get(key)
            if value not in (None, ""):
                feedback_lines.append(f"- {label}: {value}")
        feedback_text = submission.get("feedbackText")
        feedback_comment = submission.get("feedbackComment")
        if isinstance(feedback_text, str) and feedback_text:
            feedback_lines.extend(["", feedback_text])
        if isinstance(feedback_comment, str) and feedback_comment:
            feedback_lines.extend(["", feedback_comment])
        _append_attachment_links(
            feedback_lines,
            "添付ファイル",
            submission.get("feedbackAttachments", []),
        )
        if len(feedback_lines) > 1:
            paths.append(
                (folder / "返却" / "講評.md", "\n".join(feedback_lines) + "\n")
            )
    return paths


def format_assignment_datetime(value: object) -> str:
    """課題APIの日時を日本時間で表示する。"""
    if not isinstance(value, str):
        return str(value)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")


def _append_attachment_links(
    lines: list[str],
    heading: str,
    attachments: Sequence[AttachmentRecord],
) -> None:
    if not attachments:
        return
    lines.extend(["", f"### {heading}"])
    for attachment in attachments:
        name = attachment.get("name", "unnamed_file")
        safe_name = _sanitize_segment(name)
        lines.append(f"- [{name}](./{safe_name})")


def _write_text_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary_path = file.name
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


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
