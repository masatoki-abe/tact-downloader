"""優先度1（パス安全性、原子性、URL検証）の回帰テスト。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tact_downloader import downloader
from tact_downloader.classifier import classify_site
from tact_downloader.client import TACTClient


class DownloaderPathTests(unittest.TestCase):
    def test_rejects_traversal_and_absolute_resource_paths(self):
        for value in ("../outside/file.pdf", "/tmp/file.pdf", r"C:\tmp\file.pdf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                downloader.safe_relative_path(value)

    def test_build_path_stays_inside_vault_and_rejects_absolute_base(self):
        with tempfile.TemporaryDirectory() as temp:
            info = classify_site("site", "2025年度 安全な授業 (春学期)")
            with patch.object(downloader, "VAULT_ROOT", temp), patch.object(
                downloader, "DOWNLOAD_BASE", "大学"
            ):
                path = downloader.build_download_path(info)
                self.assertTrue(path.is_relative_to(Path(temp).resolve()))

            with patch.object(downloader, "VAULT_ROOT", temp), patch.object(
                downloader, "DOWNLOAD_BASE", "../outside"
            ), self.assertRaises(ValueError):
                downloader.build_download_path(info)

    def test_detects_sanitized_resource_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            resources = [
                {"relative_path": "a:b.txt"},
                {"relative_path": "a?b.txt"},
            ]
            with patch.object(downloader, "VAULT_ROOT", temp), self.assertRaises(ValueError):
                downloader.validate_resource_paths(directory, resources)

    def test_detects_sanitized_site_collision(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            downloader, "VAULT_ROOT", temp
        ):
            first = classify_site("site-1", "2025年度 A:B (春学期)")
            second = classify_site("site-2", "2025年度 A?B (春学期)")
            with self.assertRaises(ValueError):
                downloader.validate_site_paths([first, second])


class ClientTests(unittest.TestCase):
    def test_url_validation_requires_https_and_exact_host_port(self):
        client = TACTClient(Mock(), "https://tact.example.test")
        for url in (
            "http://tact.example.test/file",
            "https://evil.example.test/file",
            "https://tact.example.test:444/file",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                client._validate_url(url)

    def test_download_is_atomic_and_validates_size(self):
        session = Mock()
        response = Mock()
        response.status_code = 200
        response.is_redirect = False
        response.is_permanent_redirect = False
        response.iter_content.return_value = [b"new", b" data"]
        session.get.return_value = response
        client = TACTClient(session, "https://tact.example.test")

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "file.txt"
            target.write_bytes(b"old")
            client.download_resource(
                "https://tact.example.test/file", str(target), expected_size=8
            )
            self.assertEqual(target.read_bytes(), b"new data")
            self.assertEqual(list(Path(temp).glob(".*")), [])
            response.iter_content.return_value = [b"broken"]
            with self.assertRaises(IOError):
                client.download_resource(
                    "https://tact.example.test/file", str(target), expected_size=99
                )
            self.assertEqual(target.read_bytes(), b"new data")

    def test_external_redirect_is_rejected_before_following(self):
        session = Mock()
        response = Mock()
        response.status_code = 302
        response.is_redirect = True
        response.is_permanent_redirect = False
        response.headers = {"Location": "https://evil.example.test/file"}
        session.get.return_value = response
        client = TACTClient(session, "https://tact.example.test")

        with self.assertRaises(ValueError):
            client._get("https://tact.example.test/file")
        self.assertEqual(session.get.call_count, 1)

    def test_site_id_is_url_encoded(self):
        session = Mock()
        response = Mock()
        response.json.return_value = {"content_collection": []}
        response.status_code = 200
        response.is_redirect = False
        response.is_permanent_redirect = False
        session.get.return_value = response
        client = TACTClient(session, "https://tact.example.test")
        client.get_site_contents("site/id")
        self.assertIn("site%2Fid.json", session.get.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
