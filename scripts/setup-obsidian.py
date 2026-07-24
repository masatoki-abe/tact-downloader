#!/usr/bin/env python3
"""Obsidian Shell Commands プラグインの自動セットアップ

tact-downloader の Obsidian 連携（フォルダ右クリック → TACTダウンロード）を
自動構成する。

Usage:
    python scripts/setup-obsidian.py
    python scripts/setup-obsidian.py /path/to/obsidian-vault
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import TypeAlias, cast

SC_VERSION = "0.23.0"
SC_DOWNLOAD_BASE = (
    f"https://github.com/Taitava/obsidian-shellcommands/releases/download/{SC_VERSION}"
)
PLUGIN_ID = "obsidian-shellcommands"
PLUGIN_FILES = ["main.js", "manifest.json", "styles.css"]
PLUGIN_SHA256 = {
    "main.js": "0c5e247a91c96c0af5f3e333ba43be4285469566c819d59b7de129ad33d14d8a",
    "manifest.json": "20ae8ccfa8972027d35b4457d21b6ab86aebc8e3b1dee5eba34dad19e46a2462",
    "styles.css": "3bd8380e5aa53fc447ea6a4c14ddfb94198f1a6d003e6e5f994b459cf9684c53",
}
COMMAND_ID = "tact-download-folder"

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

DATA_JSON_TEMPLATE: JsonObject = {
    "settings_version": SC_VERSION,
    "debug": False,
    "obsidian_command_palette_prefix": "Execute: ",
    "preview_variables_in_command_palette": True,
    "show_autocomplete_menu": True,
    "default_shells": {},
    "environment_variable_path_augmentations": {},
    "show_installation_warnings": True,
    "error_message_duration": 20,
    "notification_message_duration": 10,
    "execution_notification_mode": "disabled",
    "output_channel_clipboard_also_outputs_to_notification": True,
    "output_channel_notification_decorates_output": True,
    "enable_events": True,
    "approve_modals_by_pressing_enter_key": True,
    "command_palette": {
        "re_execute_last_shell_command": {"enabled": True, "prefix": "Re-execute: "}
    },
    "max_visible_lines_in_shell_command_fields": False,
    "prompts": [],
    "builtin_variables": {},
    "custom_variables": [],
    "custom_variables_notify_changes_via": {
        "obsidian_uri": True,
        "output_assignment": True,
    },
    "custom_shells": [],
    "output_wrappers": [],
}


def parse_env(project_root: Path) -> dict[str, str]:
    env_path = project_root / ".env"
    if not env_path.exists():
        return {}
    env: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def resolve_vault_path(project_root: Path, cli_arg: str | None) -> Path:
    if cli_arg:
        return Path(cli_arg).resolve()
    env = parse_env(project_root)
    vault_str = env.get("VAULT_ROOT")
    if vault_str:
        vault_path = Path(vault_str)
        if vault_path.is_dir():
            return vault_path.resolve()
        print(f"警告: .env の VAULT_ROOT ({vault_path}) が存在しません。")
    print("エラー: vault のパスを指定するか、.env に VAULT_ROOT を設定してください。")
    print(f"   Usage: python {__file__} /path/to/vault")
    sys.exit(1)


def download_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    for filename in PLUGIN_FILES:
        url = f"{SC_DOWNLOAD_BASE}/{filename}"
        dest = plugin_dir / filename
        if dest.exists() and sha256_file(dest) == PLUGIN_SHA256[filename]:
            print(f"  [スキップ] {filename} (既存)")
            continue
        print(f"  [DL] {filename} ...", end="", flush=True)
        temporary_path = None
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=plugin_dir, prefix=f".{filename}.", delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    shutil.copyfileobj(response, temporary)
                    temporary.flush()
                    os.fsync(temporary.fileno())
            if sha256_file(temporary_path) != PLUGIN_SHA256[filename]:
                raise ValueError(f"{filename} のSHA-256検証に失敗しました")
            os.replace(temporary_path, dest)
            temporary_path = None
            print(" 完了")
        except Exception as e:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            print(f" 失敗: {e}")
            sys.exit(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_data_json(project_root: Path, vault_root: Path) -> JsonObject:
    sc_path = project_root / ".venv" / "bin" / "python"
    if not sc_path.exists():
        print(
            f"警告: {sc_path} が見つかりません。.venv が正しくセットアップされていない可能性があります。"
        )

    command = (
        f"{shlex.quote(str(sc_path))} -m tact_downloader.obsidian_cmd --path "
        "{{event_folder_path:absolute}}"
    )
    working_dir = str(project_root)

    data: JsonObject = dict(DATA_JSON_TEMPLATE)
    data["working_directory"] = working_dir
    data["shell_commands"] = [
        {
            "id": COMMAND_ID,
            "platform_specific_commands": {"default": command},
            "shells": {},
            "alias": "TACT: 現在のフォルダをダウンロード",
            "icon": "download",
            "confirm_execution": False,
            "ignore_error_codes": [],
            "input_contents": {"stdin": None},
            "output_handlers": {
                "stdout": {"handler": "notification", "convert_ansi_code": True},
                "stderr": {"handler": "notification", "convert_ansi_code": True},
            },
            "output_wrappers": {"stdout": None, "stderr": None},
            "output_channel_order": "stdout-first",
            "output_handling_mode": "buffered",
            "execution_notification_mode": None,
            "events": {"folder-menu": {"enabled": True}},
            "debounce": None,
            "command_palette_availability": "enabled",
            "preactions": [],
            "variable_default_values": {},
        }
    ]
    return data


def write_data_json(plugin_dir: Path, data: JsonObject) -> None:
    dest = plugin_dir / "data.json"
    write_json_atomically(dest, data)
    print("  [更新] data.json")


def write_json_atomically(dest: Path, data: object) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    old_content = dest.read_text(encoding="utf-8") if dest.exists() else None
    if old_content == content:
        return
    if old_content is not None:
        write_text_atomically(dest.with_name(f"{dest.name}.bak"), old_content)
    write_text_atomically(dest, content)


def write_text_atomically(dest: Path, content: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=dest.parent,
            prefix=f".{dest.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, dest)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_updated_data(existing: JsonObject, generated: JsonObject) -> JsonObject:
    data: JsonObject = dict(existing)
    commands = data.get("shell_commands", [])
    if not isinstance(commands, list):
        raise ValueError("data.json の shell_commands は配列である必要があります")
    generated_commands = generated["shell_commands"]
    if not isinstance(generated_commands, list) or not generated_commands:
        raise ValueError("生成したshell_commandsが不正です")
    updated_command = generated_commands[0]
    data["shell_commands"] = []
    found = False
    for command in commands:
        if isinstance(command, dict) and command.get("id") == COMMAND_ID:
            if not found:
                data["shell_commands"].append(updated_command)
                found = True
        else:
            data["shell_commands"].append(command)
    if not found:
        data["shell_commands"].append(updated_command)
    data.setdefault("settings_version", SC_VERSION)
    return data


def update_data_json(plugin_dir: Path, generated: JsonObject) -> None:
    dest = plugin_dir / "data.json"
    if dest.exists():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"既存のdata.jsonを読み込めません: {exc}") from exc
        if not isinstance(existing, dict):
            raise ValueError(
                "data.jsonのトップレベルはオブジェクトである必要があります"
            )
        data = build_updated_data(cast(JsonObject, existing), generated)
    else:
        data = generated
    write_data_json(plugin_dir, data)


def update_community_plugins(vault_root: Path) -> None:
    plugins_file = vault_root / ".obsidian" / "community-plugins.json"
    plugins: list[str] = []
    if plugins_file.exists():
        try:
            with open(plugins_file, encoding="utf-8") as f:
                raw_plugins: object = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"community-plugins.jsonを読み込めません: {exc}") from exc
        if not isinstance(raw_plugins, list) or not all(
            isinstance(item, str) for item in cast(list[object], raw_plugins)
        ):
            raise ValueError("community-plugins.jsonは文字列配列である必要があります")
        plugins = [
            item for item in cast(list[object], raw_plugins) if isinstance(item, str)
        ]

    if PLUGIN_ID not in plugins:
        plugins.append(PLUGIN_ID)
        write_json_atomically(plugins_file, plugins)
        print(f"  [追加] community-plugins.json に {PLUGIN_ID} を追加")
    else:
        print(f"  [確認] {PLUGIN_ID} は既に community-plugins.json に登録済み")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Obsidian Shell Commands プラグインを自動セットアップ"
    )
    parser.add_argument(
        "vault_path",
        nargs="?",
        help="Obsidian vault のパス（省略時は .env の VAULT_ROOT を使用）",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    vault_root = resolve_vault_path(project_root, args.vault_path)

    print(f"プロジェクトルート: {project_root}")
    print(f"Obsidian vault:    {vault_root}")
    print()

    plugin_dir = vault_root / ".obsidian" / "plugins" / PLUGIN_ID

    # Step 1: download plugin files
    print("Step 1/3: Shell Commands プラグインをダウンロード")
    download_plugin(plugin_dir)
    print()

    # Step 2: write data.json
    print("Step 2/3: data.json を生成")
    data = build_data_json(project_root, vault_root)
    update_data_json(plugin_dir, data)
    print()

    # Step 3: update community-plugins.json
    print("Step 3/3: community-plugins.json を更新")
    update_community_plugins(vault_root)
    print()

    print("セットアップ完了。")
    print("Obsidian を再起動して、ファイルエクスプローラでフォルダを右クリック →")
    print("「TACT: 現在のフォルダをダウンロード」をお試しください。")


if __name__ == "__main__":
    main()
