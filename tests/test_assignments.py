"""課題APIと課題保存処理のテスト。"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from tact_downloader import downloader
from tact_downloader.classifier import classify_site
from tact_downloader.client import TACTClient


def test_client_parses_assignments_and_encodes_site_id() -> None:
    session = Mock()
    response = Mock()
    response.json.return_value = {
        "assignment_collection": [
            {
                "id": "assignment-id",
                "title": "レポート",
                "instructions": "<p>本文</p>",
                "dueTimeString": "2026-07-31",
                "attachments": [
                    {
                        "name": "説明.pdf",
                        "url": "https://tact.example.test/attachment",
                        "size": 10,
                        "type": "application/pdf",
                    }
                ],
                "submissions": [
                    {
                        "id": "submission-id",
                        "userSubmission": True,
                        "submittedText": "提出本文",
                        "submittedAttachments": [],
                    }
                ],
            }
        ]
    }
    response.status_code = 200
    response.is_redirect = False
    response.is_permanent_redirect = False
    session.get.return_value = response

    result = TACTClient(session, "https://tact.example.test").get_site_assignments(
        "site/id"
    )

    assert result[0]["title"] == "レポート"
    assert result[0]["attachments"][0]["name"] == "説明.pdf"
    assert result[0]["submissions"][0].get("submittedText") == "提出本文"
    assert session.get.call_args.args[0].endswith("/site/site%2Fid.json")


def test_download_assignments_writes_markdown_and_only_own_submission(
    tmp_path: Path,
) -> None:
    info = classify_site("site", "2025年度 課題科目 (春学期)")
    client = Mock()
    client.get_site_assignments.return_value = [
        {
            "id": "assignment-id",
            "title": "レポート",
            "instructions": "<p>課題本文</p>",
            "status": "Open",
            "draft": False,
            "openTimeString": "",
            "dueTimeString": "2026-07-31",
            "dropDeadTimeString": "",
            "closeTimeString": "",
            "submissionType": "TEXT_ONLY",
            "gradeScale": "Points",
            "maxGradePoint": 100,
            "attachments": [],
            "submissions": [
                {
                    "id": "own",
                    "userSubmission": True,
                    "submittedText": "自分の提出",
                    "returned": True,
                    "grade": "95",
                    "feedbackComment": "よくできています",
                    "submittedAttachments": [],
                    "feedbackAttachments": [],
                },
                {
                    "id": "other",
                    "userSubmission": False,
                    "submittedText": "他人の提出",
                    "submittedAttachments": [],
                    "feedbackAttachments": [],
                },
            ],
        }
    ]
    with (
        pytest.MonkeyPatch.context() as patch,
    ):
        patch.setattr(downloader, "VAULT_ROOT", str(tmp_path))
        result = downloader.download_assignment_sites(client, [info])

    assert result.succeeded == 3
    markdowns = [path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.md")]
    assert any("課題本文" in markdown for markdown in markdowns)
    assert any("自分の提出" in markdown for markdown in markdowns)
    assert all("他人の提出" not in markdown for markdown in markdowns)
    assert any("95" in markdown for markdown in markdowns)


def test_duplicate_assignment_titles_get_ids_on_both_directories(
    tmp_path: Path,
) -> None:
    assignments = [
        {"id": "first-id", "title": "同じ課題"},
        {"id": "second-id", "title": "同じ課題"},
    ]
    duplicate_titles = downloader.duplicate_assignment_titles(assignments)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(downloader, "VAULT_ROOT", str(tmp_path))
        paths = [
            downloader.assignment_directory(
                tmp_path,
                assignment,
                use_id=downloader.assignment_title_key(assignment) in duplicate_titles,
            )
            for assignment in assignments
        ]

    assert paths == [tmp_path / "同じ課題--first-id", tmp_path / "同じ課題--second-id"]


def test_assignment_dry_run_does_not_create_vault(tmp_path: Path) -> None:
    info = classify_site("site", "2025年度 課題科目 (春学期)")
    client = Mock()
    client.get_site_assignments.return_value = [
        {
            "id": "id",
            "title": "課題",
            "instructions": "",
            "status": "",
            "draft": False,
            "openTimeString": "",
            "dueTimeString": "",
            "dropDeadTimeString": "",
            "closeTimeString": "",
            "submissionType": "",
            "gradeScale": "",
            "maxGradePoint": None,
            "attachments": [],
            "submissions": [],
        }
    ]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(downloader, "VAULT_ROOT", str(tmp_path))
        result = downloader.download_assignment_sites(client, [info], dry_run=True)

    assert result.planned == 1
    assert list(tmp_path.iterdir()) == []


def test_assignment_attachment_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(downloader, "VAULT_ROOT", str(tmp_path))
        with pytest.raises(ValueError):
            downloader.safe_assignment_path(tmp_path, "attachments/../secret")


def test_assignment_datetime_is_converted_to_japan_time() -> None:
    assert (
        downloader.format_assignment_datetime("2026-06-14T15:00:00Z")
        == "2026-06-15 00:00 JST"
    )
    assert (
        downloader.format_assignment_datetime("2026-06-14T23:00:00+02:00")
        == "2026-06-15 06:00 JST"
    )


def test_assignment_datetime_without_timezone_is_kept() -> None:
    value = "2026-06-15T00:00:00"
    assert downloader.format_assignment_datetime(value) == value
