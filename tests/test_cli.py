"""通常CLIの主要分岐回帰テスト。"""

import sys
from unittest.mock import Mock, patch

import main


def fake_client(sites):
    client = Mock()
    client.get_sites.return_value = sites
    client.get_site_resources.return_value = []
    return client


def test_list_does_not_download():
    client = fake_client([{"entityId": "site", "entityTitle": "2025年度 A (春学期)"}])
    with (
        patch.object(main, "TACT_BASE_URL", "https://tact.example.test"),
        patch.object(main, "login", return_value=Mock()),
        patch.object(main, "TACTClient", return_value=client),
        patch.object(sys, "argv", ["main.py", "--list"]),
    ):
        main.main()

    client.get_site_resources.assert_not_called()
    client.download_resource.assert_not_called()


def test_all_skips_sites_without_semester():
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
        main.main()

    client.get_site_resources.assert_called_once_with("with")


def test_dry_run_does_not_create_directory(tmp_path):
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
        patch.object(
            main, "build_download_path", return_value=tmp_path / "TACTリソース"
        ),
        patch.object(sys, "argv", ["main.py", "--all", "--dry-run"]),
    ):
        main.main()

    assert not (tmp_path / "TACTリソース").exists()
    client.download_resource.assert_not_called()
