"""Obsidian連携のスコープ判定回帰テスト。"""

from unittest.mock import patch

import pytest

from tact_downloader import obsidian_cmd
from tact_downloader.classifier import classify_site


@pytest.fixture
def vault(tmp_path):
    with (
        patch.object(obsidian_cmd, "VAULT_ROOT", str(tmp_path)),
        patch.object(obsidian_cmd, "DOWNLOAD_BASE", "大学"),
    ):
        yield tmp_path


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("大学", (None, None, None)),
        ("大学/2025年度", ("2025年度", None, None)),
        ("大学/2025年度/春学期", ("2025年度", "春学期", None)),
        ("大学/2025年度/春学期/授業", ("2025年度", "春学期", "授業")),
        (
            "大学/2025年度/春学期/授業/TACTリソース/week1",
            ("2025年度", "春学期", "授業"),
        ),
    ],
)
def test_parse_scope(vault, relative, expected):
    assert obsidian_cmd.parse_scope(str(vault / relative)) == expected


def test_parse_scope_rejects_vault_external_path(vault, tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        obsidian_cmd.parse_scope(str(tmp_path.parent / "outside"))
    assert exc_info.value.code == 1


def test_filter_sites_matches_each_scope_level():
    sites = [
        classify_site("1", "2025年度 A (春学期)"),
        classify_site("2", "2026年度 B (秋学期)"),
    ]
    assert obsidian_cmd.filter_sites(sites, None, None, None) == sites
    assert obsidian_cmd.filter_sites(sites, "2025年度", None, None) == sites[:1]
    assert obsidian_cmd.filter_sites(sites, "2025年度", "春学期", "A") == sites[:1]
    assert obsidian_cmd.filter_sites(sites, "2025年度", "秋学期", None) == []
