"""通常CLIの主要分岐回帰テスト。"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from _pytest.capture import CaptureFixture

import main
from tact_downloader import downloader
from tact_downloader.exceptions import NetworkError


def fake_client(sites: list[dict[str, str]]) -> Mock:
    client = Mock()
    client.get_sites.return_value = sites
    client.get_site_resources.return_value = []
    client.get_site_assignments.return_value = []
    return client


def test_list_does_not_download() -> None:
    client = fake_client([{"entityId": "site", "entityTitle": "2025年度 A (春学期)"}])
    with (
        patch.object(main, "TACT_BASE_URL", "https://tact.example.test"),
        patch.object(main, "login", return_value=Mock()),
        patch.object(main, "TACTClient", return_value=client),
        patch.object(sys, "argv", ["main.py", "--list"]),
    ):
        assert main.main() == 0

    client.get_site_resources.assert_not_called()
    client.download_resource.assert_not_called()


def test_all_skips_sites_without_semester() -> None:
    client = fake_client(
        [
            {"entityId": "with", "entityTitle": "2025年度 A (春学期)"},
            {"entityId": "without", "entityTitle": "2025年度 B"},
        ]
    )
    with (
        patch.object(main, "TACT_BASE_URL", "https://tact.example.test"),
        patch.object(main, "login", return_value=Mock()),
        patch.object(main, "TACTClient", return_value=client),
        patch.object(sys, "argv", ["main.py", "--all"]),
    ):
        assert main.main() == 0

    client.get_site_resources.assert_called_once_with("with")


def test_dry_run_does_not_create_directory(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    client = fake_client([{"entityId": "site", "entityTitle": "2025年度 A (春学期)"}])
    client.get_site_resources.return_value = [
        {
            "url": "https://tact.example.test/file",
            "relative_path": "file.pdf",
            "size": 1,
        }
    ]
    with (
        patch.object(main, "TACT_BASE_URL", "https://tact.example.test"),
        patch.object(main, "login", return_value=Mock()),
        patch.object(main, "TACTClient", return_value=client),
        patch.object(main, "VAULT_ROOT", str(tmp_path), create=True),
        patch.object(downloader, "VAULT_ROOT", str(tmp_path)),
        patch.object(
            main, "build_download_path", return_value=tmp_path / "TACTリソース"
        ),
        patch.object(sys, "argv", ["main.py", "--all", "--dry-run"]),
    ):
        assert main.main() == 0

    assert not (tmp_path / "TACTリソース").exists()
    client.download_resource.assert_not_called()
    assert "1 件ダウンロード予定" in capsys.readouterr().out


def test_partial_download_failure_returns_nonzero_and_reports_failure(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    client = fake_client([{"entityId": "site", "entityTitle": "2025年度 A (春学期)"}])
    client.get_site_resources.return_value = [
        {
            "url": "https://tact.example.test/file",
            "relative_path": "file.pdf",
            "size": 1,
        }
    ]
    client.download_resource.side_effect = NetworkError("timeout")
    with (
        patch.object(main, "TACT_BASE_URL", "https://tact.example.test"),
        patch.object(main, "login", return_value=Mock()),
        patch.object(main, "TACTClient", return_value=client),
        patch.object(downloader, "VAULT_ROOT", str(tmp_path)),
        patch.object(main, "build_download_path", return_value=tmp_path / "大学"),
        patch.object(sys, "argv", ["main.py", "--all"]),
    ):
        assert main.main() == 1

    assert "1 件失敗" in capsys.readouterr().out
