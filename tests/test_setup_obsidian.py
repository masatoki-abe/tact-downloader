"""Obsidianセットアップの安全性回帰テスト。"""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "setup-obsidian.py"
SPEC = importlib.util.spec_from_file_location("setup_obsidian", SCRIPT_PATH)
setup_obsidian = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(setup_obsidian)


def test_build_updated_data_preserves_unrelated_settings_and_replaces_command(tmp_path):
    generated = setup_obsidian.build_data_json(
        tmp_path / "project with 'quote'", tmp_path / "vault"
    )
    existing = {
        "debug": True,
        "custom_variables": [{"name": "keep-me"}],
        "shell_commands": [
            {"id": "other-command", "alias": "Keep this"},
            {"id": setup_obsidian.COMMAND_ID, "alias": "Old command"},
        ],
    }

    updated = setup_obsidian.build_updated_data(existing, generated)

    assert updated["debug"] is True
    assert updated["custom_variables"] == [{"name": "keep-me"}]
    assert [command["id"] for command in updated["shell_commands"]] == [
        "other-command",
        setup_obsidian.COMMAND_ID,
    ]
    command = updated["shell_commands"][1]
    assert (
        "{{event_folder_path:absolute}}"
        in command["platform_specific_commands"]["default"]
    )
    assert (
        "{{!event_folder_path:absolute}}"
        not in command["platform_specific_commands"]["default"]
    )


def test_write_json_atomically_creates_backup_only_when_content_changes(tmp_path):
    destination = tmp_path / "data.json"
    destination.write_text('{"old": true}\n', encoding="utf-8")

    with patch.object(
        setup_obsidian.os, "replace", wraps=setup_obsidian.os.replace
    ) as replace:
        setup_obsidian.write_json_atomically(destination, {"new": True})

    assert json.loads(destination.read_text(encoding="utf-8")) == {"new": True}
    assert json.loads((tmp_path / "data.json.bak").read_text(encoding="utf-8")) == {
        "old": True
    }
    assert replace.call_count == 2
    assert not list(tmp_path.glob(".data.json.*"))

    (tmp_path / "data.json.bak").unlink()
    with patch.object(
        setup_obsidian.os, "replace", wraps=setup_obsidian.os.replace
    ) as replace:
        setup_obsidian.write_json_atomically(destination, {"new": True})
    assert replace.call_count == 0
    assert not (tmp_path / "data.json.bak").exists()


def test_update_data_json_rejects_invalid_existing_json(tmp_path):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    destination = plugin_dir / "data.json"
    destination.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError):
        setup_obsidian.update_data_json(plugin_dir, {"shell_commands": []})
    assert destination.read_text(encoding="utf-8") == "not json"


def test_download_plugin_skips_valid_file_and_atomically_replaces_invalid_file(
    tmp_path,
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    filename = "manifest.json"
    expected = b"verified plugin"
    digest = setup_obsidian.hashlib.sha256(expected).hexdigest()
    old_hash = setup_obsidian.PLUGIN_SHA256[filename]
    setup_obsidian.PLUGIN_SHA256[filename] = digest
    try:
        destination = plugin_dir / filename
        destination.write_bytes(b"old plugin")

        response = io.BytesIO(expected)
        response.__enter__ = lambda: response
        response.__exit__ = lambda *args: None
        with (
            patch.object(setup_obsidian, "PLUGIN_FILES", [filename]),
            patch.object(
                setup_obsidian.urllib.request, "urlopen", return_value=response
            ),
            patch.object(
                setup_obsidian.os, "replace", wraps=setup_obsidian.os.replace
            ) as replace,
        ):
            setup_obsidian.download_plugin(plugin_dir)

        assert destination.read_bytes() == expected
        assert replace.call_count == 1
        assert not list(plugin_dir.glob(f".{filename}.*"))
    finally:
        setup_obsidian.PLUGIN_SHA256[filename] = old_hash


def test_download_plugin_removes_unverified_temporary_file(tmp_path):
    plugin_dir = tmp_path / "plugin"
    response = io.BytesIO(b"tampered")
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None
    filename = "manifest.json"

    with (
        patch.object(setup_obsidian, "PLUGIN_FILES", [filename]),
        patch.object(setup_obsidian.urllib.request, "urlopen", return_value=response),
        pytest.raises(SystemExit),
    ):
        setup_obsidian.download_plugin(plugin_dir)

    assert not list(plugin_dir.glob(f".{filename}.*"))
    assert not (plugin_dir / filename).exists()


def test_update_community_plugins_preserves_existing_entries_and_backups(tmp_path):
    obsidian_dir = tmp_path / ".obsidian"
    obsidian_dir.mkdir()
    destination = obsidian_dir / "community-plugins.json"
    destination.write_text('["other-plugin"]\n', encoding="utf-8")

    setup_obsidian.update_community_plugins(tmp_path)

    assert json.loads(destination.read_text(encoding="utf-8")) == [
        "other-plugin",
        setup_obsidian.PLUGIN_ID,
    ]
    assert json.loads(
        (obsidian_dir / "community-plugins.json.bak").read_text(encoding="utf-8")
    ) == ["other-plugin"]
