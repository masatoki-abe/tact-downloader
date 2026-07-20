import json
import os
import re
import tempfile
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

from tact_downloader import TACT_BASE_URL


class TACTClient:
    """TACT (Sakai LMS) の /direct/ API にアクセスするクライアント。"""

    def __init__(self, session: requests.Session, base_url: str = TACT_BASE_URL):
        self.session = session
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("TACT_BASE_URLは認証情報を含まないHTTPS URLにしてください。")
        self.domain = parsed.hostname.lower() if parsed.hostname else ""
        try:
            self.port = parsed.port or 443
        except ValueError as exc:
            raise ValueError("TACT_BASE_URLのポートが不正です。") from exc
        if not self.domain:
            raise ValueError("TACT_BASE_URLにホスト名がありません。")

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError(f"URL {url} のポートが不正です。") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() != self.domain
            or port != self.port
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError(
                f"URL {url} は許可されたHTTPSホストではありません。"
            )

    def _get(self, url: str, **kwargs) -> requests.Response:
        """認証済みセッションでGETリクエストを送信する。
        セッション切れの場合は再認証を試みる。
        """
        self._validate_url(url)
        current_url = url
        for _ in range(5):
            self._validate_url(current_url)
            resp = self.session.get(current_url, allow_redirects=False, **kwargs)
            if resp.is_redirect or resp.is_permanent_redirect:
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise RuntimeError("リダイレクト先が指定されていません。")
                current_url = urljoin(current_url, location)
                continue
            break
        else:
            raise RuntimeError("リダイレクト回数が上限を超えました。")
        if resp.status_code == 401:
            raise RuntimeError(
                "セッションが切れました。login() を再実行してください。"
            )
        resp.raise_for_status()
        return resp

    def get_sites(self) -> list[dict]:
        """受講中の全講義サイト一覧を取得する。"""
        url = f"{self.base_url}/direct/site.json?_limit=1000000"
        resp = self._get(url)
        data = resp.json()
        return data.get("site_collection", [])

    def get_site_contents(self, site_id: str) -> dict:
        """指定したサイトのリソース一覧を取得する。"""
        encoded_site_id = quote(str(site_id), safe="")
        url = f"{self.base_url}/direct/content/site/{encoded_site_id}.json"
        resp = self._get(url)
        return resp.json()

    def get_site_resources(self, site_id: str) -> list[dict]:
        """指定したサイトのダウンロード可能なリソースURL一覧を取得する。"""
        data = self.get_site_contents(site_id)
        contents = data.get("content_collection", [])
        resources = []
        for item in contents:
            url = item.get("url", "")
            if url and not url.endswith("/"):
                parsed = urlparse(url)
                path = unquote(parsed.path.rstrip("/"))
                # URLから /group/{group_id}/... の相対パスを抽出
                match = re.search(r"/group/[^/]+/(.+)", path)
                if match:
                    relative_path = match.group(1)
                else:
                    relative_path = path.rsplit("/", 1)[-1]
                resources.append({
                    "url": url,
                    "name": relative_path.rsplit("/", 1)[-1],
                    "relative_path": relative_path,
                    "type": item.get("type", "resource"),
                    "size": item.get("size"),
                })
        return resources

    def download_resource(
        self, resource_url: str, save_path: str, expected_size: int | str | None = None
    ) -> str:
        """指定したURLのリソースをダウンロードして保存する。

        Returns:
            保存したファイルの絶対パス
        """
        self._validate_url(resource_url)
        resp = self._get(resource_url, stream=True)
        directory = os.path.dirname(os.path.abspath(save_path))
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=directory, prefix=f".{os.path.basename(save_path)}.", delete=False
            ) as f:
                temporary_path = f.name
                byte_count = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        byte_count += len(chunk)
                f.flush()
                os.fsync(f.fileno())

            if expected_size is not None:
                try:
                    expected = int(expected_size)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"APIのサイズ情報が不正です: {expected_size!r}") from exc
                if byte_count != expected:
                    raise IOError(
                        f"ダウンロードサイズが一致しません: {byte_count} bytes (期待値 {expected} bytes)"
                    )
            os.replace(temporary_path, save_path)
            temporary_path = None
        finally:
            resp.close()
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
        return save_path
