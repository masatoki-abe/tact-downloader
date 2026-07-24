import os
import re
import tempfile
import time
from typing import cast
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

from tact_downloader import TACT_BASE_URL
from tact_downloader.exceptions import AuthenticationError, DataError, NetworkError
from tact_downloader.models import ResourceRecord, SiteRecord

DEFAULT_TIMEOUT = (5, 30)
MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


class TACTClient:
    """TACT (Sakai LMS) の /direct/ API にアクセスするクライアント。"""

    def __init__(
        self, session: requests.Session, base_url: str = TACT_BASE_URL
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError(
                "TACT_BASE_URLは認証情報を含まないHTTPS URLにしてください。"
            )
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
            raise ValueError(f"URL {url} は許可されたHTTPSホストではありません。")

    @staticmethod
    def _close_response(resp: requests.Response) -> None:
        """実レスポンスと簡易モックのどちらも安全に解放する。"""
        try:
            resp.close()
        except AttributeError:
            pass

    def _get(self, url: str, *, stream: bool = False) -> requests.Response:
        """認証済みセッションでGETリクエストを送信する。
        セッション切れの場合は再認証を試みる。
        """
        self._validate_url(url)
        current_url = url
        retry_count = 0
        redirect_count = 0
        while True:
            self._validate_url(current_url)
            try:
                if stream:
                    resp = self.session.get(
                        current_url,
                        allow_redirects=False,
                        timeout=DEFAULT_TIMEOUT,
                        stream=True,
                    )
                else:
                    resp = self.session.get(
                        current_url,
                        allow_redirects=False,
                        timeout=DEFAULT_TIMEOUT,
                    )
            except requests.RequestException as exc:
                raise NetworkError(f"TACTへの通信に失敗しました: {exc}") from exc
            if resp.is_redirect or resp.is_permanent_redirect:
                location = resp.headers.get("Location")
                self._close_response(resp)
                if not location:
                    raise DataError("リダイレクト先が指定されていません。")
                current_url = urljoin(current_url, location)
                redirect_count += 1
                if redirect_count >= 5:
                    raise NetworkError("リダイレクト回数が上限を超えました。")
                continue
            if resp.status_code in RETRYABLE_STATUS_CODES and retry_count < MAX_RETRIES:
                self._close_response(resp)
                time.sleep(0.1 * (2**retry_count))
                retry_count += 1
                continue
            break
        if resp.status_code == 401:
            self._close_response(resp)
            raise AuthenticationError(
                "セッションが切れました。login() を再実行してください。"
            )
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            self._close_response(resp)
            raise NetworkError(f"TACT APIがHTTPエラーを返しました: {exc}") from exc
        return resp

    def get_sites(self) -> list[SiteRecord]:
        """受講中の全講義サイト一覧を取得する。"""
        url = f"{self.base_url}/direct/site.json?_limit=1000000"
        resp = self._get(url)
        try:
            data: object = resp.json()
        except (ValueError, TypeError) as exc:
            self._close_response(resp)
            raise DataError("サイト一覧のJSONが不正です。") from exc
        finally:
            self._close_response(resp)
        if not isinstance(data, dict):
            raise DataError("サイト一覧の形式が不正です。")
        typed_data = cast(dict[str, object], data)
        sites: object = typed_data.get("site_collection", [])
        if not isinstance(sites, list):
            raise DataError("サイト一覧項目の形式が不正です。")
        result: list[SiteRecord] = []
        for raw_site in cast(list[object], sites):
            if not isinstance(raw_site, dict):
                raise DataError("サイト一覧項目の形式が不正です。")
            site = cast(dict[str, object], raw_site)
            record: SiteRecord = {}
            for key in ("entityId", "id", "entityTitle", "title"):
                value = site.get(key)
                if value is not None:
                    if not isinstance(value, str):
                        raise DataError("サイト一覧項目の形式が不正です。")
                    record[key] = value
            result.append(record)
        return result

    def get_site_contents(self, site_id: str) -> dict[str, object]:
        """指定したサイトのリソース一覧を取得する。"""
        encoded_site_id = quote(str(site_id), safe="")
        url = f"{self.base_url}/direct/content/site/{encoded_site_id}.json"
        resp = self._get(url)
        try:
            data: object = resp.json()
        except (ValueError, TypeError) as exc:
            self._close_response(resp)
            raise DataError("サイトコンテンツのJSONが不正です。") from exc
        finally:
            self._close_response(resp)
        if not isinstance(data, dict):
            raise DataError("サイトコンテンツの形式が不正です。")
        return cast(dict[str, object], data)

    def get_site_resources(self, site_id: str) -> list[ResourceRecord]:
        """指定したサイトのダウンロード可能なリソースURL一覧を取得する。"""
        data = self.get_site_contents(site_id)
        contents: object = data.get("content_collection", [])
        if not isinstance(contents, list):
            raise DataError("サイトコンテンツ一覧の形式が不正です。")
        resources: list[ResourceRecord] = []
        for raw_item in cast(list[object], contents):
            if not isinstance(raw_item, dict):
                raise DataError("サイトコンテンツ項目の形式が不正です。")
            item = cast(dict[str, object], raw_item)
            url = item.get("url", "")
            if not isinstance(url, str):
                continue
            if url and not url.endswith("/"):
                parsed = urlparse(url)
                path = unquote(parsed.path.rstrip("/"))
                # URLから /group/{group_id}/... の相対パスを抽出
                match = re.search(r"/group/[^/]+/(.+)", path)
                if match:
                    relative_path = match.group(1)
                else:
                    relative_path = path.rsplit("/", 1)[-1]
                item_type = item.get("type", "resource")
                item_size = item.get("size")
                if not isinstance(item_type, str):
                    item_type = "resource"
                if not isinstance(item_size, (int, str)) and item_size is not None:
                    item_size = None
                resources.append(
                    {
                        "url": url,
                        "name": relative_path.rsplit("/", 1)[-1],
                        "relative_path": relative_path,
                        "type": item_type,
                        "size": item_size,
                    }
                )
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
                mode="wb",
                dir=directory,
                prefix=f".{os.path.basename(save_path)}.",
                delete=False,
            ) as f:
                temporary_path = f.name
                byte_count = 0
                try:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            byte_count += len(chunk)
                except requests.RequestException as exc:
                    raise NetworkError(f"リソースの受信に失敗しました: {exc}") from exc
                f.flush()
                os.fsync(f.fileno())

            if expected_size is not None:
                try:
                    expected = int(expected_size)
                except (TypeError, ValueError) as exc:
                    raise DataError(
                        f"APIのサイズ情報が不正です: {expected_size!r}"
                    ) from exc
                if byte_count != expected:
                    raise DataError(
                        f"ダウンロードサイズが一致しません: {byte_count} bytes (期待値 {expected} bytes)"
                    )
            os.replace(temporary_path, save_path)
            temporary_path = None
        finally:
            self._close_response(resp)
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
        return save_path
