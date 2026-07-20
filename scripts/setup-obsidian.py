#!/usr/bin/env python3
"""Obsidian Shell Commands プラグインの自動セットアップ

tact-downloader の Obsidian 連携（フォルダ右クリック → TACTダウンロード）を
自動構成する。

Usage:
    python scripts/setup-obsidian.py
    python scripts/setup-obsidian.py /path/to/obsidian-vault
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

SC_VERSION = "0.23.0"
SC_DOWNLOAD_BASE = (
    f"https://github.com/Taitava/obsidian-shellcommands/releases/download/{SC_VERSION}"
)
PLUGIN_ID = "obsidian-shellcommands"
PLUGIN_FILES = ["main.js", "manifest.json", "styles.css"]

DATA_JSON_TEMPLATE = {
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
    env = {}
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
        if dest.exists():
            print(f"  [スキップ] {filename} (既存)")
            continue
        print(f"  [DL] {filename} ...", end="", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            print(" 完了")
        except Exception as e:
            print(f" 失敗: {e}")
            sys.exit(1)


def build_data_json(project_root: Path, vault_root: Path) -> dict:
    sc_path = project_root / "venv" / "bin" / "python"
    if not sc_path.exists():
        print(
            f"警告: {sc_path} が見つかりません。venv が正しくセットアップされていない可能性があります。"
        )
        # Try to find python in venv
        alt_path = project_root / ".venv" / "bin" / "python"
        if alt_path.exists():
            sc_path = alt_path

    command = f'{sc_path} -m tact_downloader.obsidian_cmd --path "{{!event_folder_path:absolute}}"'
    working_dir = str(project_root)

    data = dict(DATA_JSON_TEMPLATE)
    data["working_directory"] = working_dir
    data["shell_commands"] = [
        {
            "id": "tact-download-folder",
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


def write_data_json(plugin_dir: Path, data: dict) -> None:
    dest = plugin_dir / "data.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("  [作成] data.json")


def update_community_plugins(vault_root: Path) -> None:
    plugins_file = vault_root / ".obsidian" / "community-plugins.json"
    plugins: list[str] = []
    if plugins_file.exists():
        with open(plugins_file, encoding="utf-8") as f:
            plugins = json.load(f)

    if PLUGIN_ID not in plugins:
        plugins.append(PLUGIN_ID)
        with open(plugins_file, "w", encoding="utf-8") as f:
            json.dump(plugins, f, ensure_ascii=False, indent=2)
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
    write_data_json(plugin_dir, data)
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
