"""優先度2のパス、ダウンロード、dry-run回帰テスト。"""

from unittest.mock import Mock, patch

import pytest
import requests

from tact_downloader import downloader
from tact_downloader.classifier import classify_site
from tact_downloader.client import TACTClient


def test_rejects_empty_and_invalid_resource_paths():
    for value in ("", ".", "..", "dir/../file", "/tmp/file", r"C:\tmp\file"):
        with pytest.raises(ValueError):
            downloader.safe_relative_path(value)


def test_sanitizes_names_and_keeps_vault_boundary(tmp_path):
    with patch.object(downloader, "VAULT_ROOT", str(tmp_path)):
        assert downloader.safe_relative_path("a:b?*.txt") == "a_b__.txt"
        assert downloader.safe_relative_path("   ") == "unnamed_file"
        directory = tmp_path / "大学"
        assert downloader.safe_resource_path(directory, "week/file.pdf").is_relative_to(
            tmp_path
        )


def test_rejects_symlink_outside_vault(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "大学"
    link.symlink_to(outside, target_is_directory=True)
    with patch.object(downloader, "VAULT_ROOT", str(tmp_path)):
        with pytest.raises(ValueError):
            downloader.safe_resource_path(link, "secret.txt")


def _client_with_response(response):
    session = Mock()
    session.get.return_value = response
    return TACTClient(session, "https://tact.example.test"), session


def _ok_response(chunks):
    response = Mock()
    response.status_code = 200
    response.is_redirect = False
    response.is_permanent_redirect = False
    response.iter_content.return_value = chunks
    return response


def test_interrupted_download_keeps_existing_file_and_removes_temp(tmp_path):
    def interrupted_chunks():
        yield b"partial"
        raise requests.ConnectionError("lost")

    response = _ok_response(interrupted_chunks())
    client, session = _client_with_response(response)
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")

    from tact_downloader.exceptions import NetworkError

    with pytest.raises(NetworkError):
        client.download_resource("https://tact.example.test/file", str(target))

    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob(".*")) == []
    response.close.assert_called_once()
    session.get.assert_called_once()


def test_replace_failure_removes_temp_and_preserves_existing_file(tmp_path):
    response = _ok_response([b"new"])
    client, _ = _client_with_response(response)
    target = tmp_path / "file.txt"
    target.write_bytes(b"old")

    with patch(
        "tact_downloader.client.os.replace", side_effect=OSError("replace failed")
    ):
        with pytest.raises(OSError):
            client.download_resource("https://tact.example.test/file", str(target))

    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob(".*")) == []


def test_download_rejects_external_url_without_request(tmp_path):
    session = Mock()
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(ValueError):
        client.download_resource(
            "https://evil.example.test/file", str(tmp_path / "file")
        )
    session.get.assert_not_called()


def test_dry_run_does_not_create_directories_in_obsidian(tmp_path):
    from tact_downloader import obsidian_cmd

    info = classify_site("site", "2025年度 安全な授業 (春学期)")
    client = Mock()
    client.get_site_resources.return_value = [
        {
            "url": "https://tact.example.test/file",
            "relative_path": "week/file.pdf",
            "size": 1,
        }
    ]
    with (
        patch.object(obsidian_cmd, "VAULT_ROOT", str(tmp_path)),
        patch.object(obsidian_cmd, "DOWNLOAD_BASE", "大学"),
        patch.object(downloader, "VAULT_ROOT", str(tmp_path)),
        patch.object(downloader, "DOWNLOAD_BASE", "大学"),
    ):
        assert obsidian_cmd.download_resources(client, info, dry_run=True) == (1, 0, 0)

    assert list(tmp_path.iterdir()) == []
    client.download_resource.assert_not_called()


def test_force_and_existing_file_behavior_in_obsidian(tmp_path):
    from tact_downloader import obsidian_cmd

    info = classify_site("site", "2025年度 安全な授業 (春学期)")
    client = Mock()
    client.get_site_resources.return_value = [
        {
            "url": "https://tact.example.test/file",
            "relative_path": "file.pdf",
            "size": 3,
        }
    ]
    with (
        patch.object(obsidian_cmd, "VAULT_ROOT", str(tmp_path)),
        patch.object(obsidian_cmd, "DOWNLOAD_BASE", "大学"),
        patch.object(downloader, "VAULT_ROOT", str(tmp_path)),
        patch.object(downloader, "DOWNLOAD_BASE", "大学"),
    ):
        target = downloader.build_download_path(info) / "file.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old")
        assert obsidian_cmd.download_resources(client, info) == (0, 1, 0)
        assert obsidian_cmd.download_resources(client, info, force=True) == (1, 0, 0)

    client.download_resource.assert_called_once_with(
        "https://tact.example.test/file", str(target), expected_size=3
    )
