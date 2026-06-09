import json
from urllib.parse import urljoin, urlparse, unquote

import requests

from tact_downloader import TACT_BASE_URL


class TACTClient:
    """TACT (Sakai LMS) の /direct/ API にアクセスするクライアント。"""

    def __init__(self, session: requests.Session, base_url: str = TACT_BASE_URL):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(self.base_url).netloc

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.netloc != self.domain:
            raise ValueError(
                f"URL {url} のドメインが {self.domain} と一致しません。"
            )

    def _get(self, url: str, **kwargs) -> requests.Response:
        """認証済みセッションでGETリクエストを送信する。
        セッション切れの場合は再認証を試みる。
        """
        self._validate_url(url)
        resp = self.session.get(url, **kwargs)
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
        url = f"{self.base_url}/direct/content/site/{site_id}.json"
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
                resources.append({
                    "url": url,
                    "name": unquote(url.rstrip("/").rsplit("/", 1)[-1]),
                    "type": item.get("type", "resource"),
                    "size": item.get("size"),
                })
        return resources

    def download_resource(self, resource_url: str, save_path: str) -> str:
        """指定したURLのリソースをダウンロードして保存する。

        Returns:
            保存したファイルの絶対パス
        """
        self._validate_url(resource_url)
        resp = self._get(resource_url, stream=True)
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    f.flush()
        return save_path
