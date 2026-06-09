import re
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import pyotp
import requests

from tact_downloader import parse_totp_seed


class FormParser(HTMLParser):
    """CASログインフォームから input 要素を抽出するパーサー。"""

    def __init__(self):
        super().__init__()
        self.params: dict[str, str] = {}
        self.form_action: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = dict(attrs)
        if tag == "form":
            self.form_action = attr_dict.get("action", "")
        if tag == "input":
            name = attr_dict.get("name", "")
            value = attr_dict.get("value", "")
            if name:
                self.params[name] = value


def extract_cas_url(html: str, base_url: str) -> Optional[str]:
    """ログインページのHTMLからCAS認証URLを抽出する。"""
    # form action から取得
    match = re.search(r'<form[^>]+action="([^"]+)"', html)
    if match:
        action = match.group(1)
        if "cas" in action.lower() or "login" in action.lower():
            return urljoin(base_url, action)
    # meta refresh / JavaScript redirect から取得
    match = re.search(r'window\.location\s*=\s*"([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'window\.location\.replace\("([^"]+)"\)', html)
    if match:
        return match.group(1)
    # XML の場合
    match = re.search(r'form[=\s]+"([^"]*cas[^"]*)"', html, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def get_totp_token(seed: str) -> str:
    """TOTPシード値から現在のトークンを生成する。"""
    seed = parse_totp_seed(seed)
    totp = pyotp.TOTP(seed)
    return totp.now()


def login(
    username: str,
    password: str,
    seed: str,
    base_url: str,
    silent: bool = False,
    verbose: bool = False,
) -> requests.Session:
    """TACTにCAS + 多要素認証でログインし、認証済みセッションを返す。

    Args:
        username: THERSアカウントのUPN
        password: パスワード
        seed: 多要素認証のTOTPシード値
        base_url: TACTのベースURL
        silent: Trueの場合、進行状況の出力を抑制する
        verbose: Trueの場合、デバッグ用の詳細情報を出力する

    Returns:
        認証済みCookieを持つ requests.Session
    """
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    portal_login = f"{base_url}/portal/login"

    # Step 1: ポータルログインページにアクセス
    if not silent:
        print("[1/4] ポータルログインページに接続中...")
    resp = session.get(portal_login, allow_redirects=True)
    resp.raise_for_status()

    # リダイレクト先のURLをCAS URLとして使用
    cas_url = None
    if resp.history:
        if verbose:
            print(f"      リダイレクト履歴:")
            for i, r in enumerate(resp.history):
                print(f"        [{i}] {r.status_code} → {r.url}")
        # "cas" を含むURLを最優先、なければ "login" を含むURLで代用
        for r in resp.history:
            if "cas" in r.url.lower():
                cas_url = r.url
                break
        if not cas_url:
            for r in resp.history:
                if "login" in r.url.lower() and "portal" not in r.url.lower():
                    cas_url = r.url
                    break
    if not cas_url:
        cas_url = extract_cas_url(resp.text, base_url)
    if not cas_url:
        # フォールバック: よく使われるパターン
        domain = urlparse(base_url).netloc
        parts = domain.split(".")
        if len(parts) >= 3:
            auth_domain = "auth-mfa." + ".".join(parts[-2:])
        else:
            auth_domain = "auth-mfa." + domain
        cas_url = (
            f"https://{auth_domain}/cas/login"
            f"?service={base_url}%2Fsakai-login-tool%2Fcontainer"
        )

    if verbose:
        print(f"      検出されたCAS URL: {cas_url}")

    # Step 2: ユーザー名・パスワードをPOST
    if not silent:
        print(f"[2/4] CAS認証 ({cas_url[:60]}...)")
    parser = FormParser()
    parser.feed(resp.text)
    payload = parser.params.copy()
    payload.update({"username": username, "password": password})

    if verbose:
        print(f"      POST → {cas_url}")
        sanitized = {k: ("***" if k in ("password", "token") else v) for k, v in payload.items()}
        print(f"      パラメータ: {sanitized}")

    resp = session.post(cas_url, data=payload, allow_redirects=False)
    if verbose:
        print(f"      応答: {resp.status_code}")
        if resp.headers.get("Location"):
            print(f"      Location: {resp.headers['Location'][:100]}")

    if resp.status_code in (302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        if verbose:
            print(f"      リダイレクト先: {location[:80]}...")
        resp = session.get(location, allow_redirects=False)
    elif resp.status_code == 401:
        pass  # MFA入力画面
    else:
        resp.raise_for_status()

    # Step 3: MFAトークン画面を解析してトークンをPOST
    if not silent:
        print("[3/4] 多要素認証トークンを生成・送信中...")

    # トークンPOST先を決定
    token_post_url = cas_url
    if resp.status_code in (302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        if location:
            if verbose:
                print(f"      リダイレクト: {location[:80]}...")
            resp = session.get(location, allow_redirects=False)

    parser = FormParser()
    parser.feed(resp.text)

    # Form action属性を優先してPOST先URLを決定
    if parser.form_action:
        token_post_url = urljoin(resp.url, parser.form_action)
    elif resp.status_code in (200, 401):
        cas_url2 = extract_cas_url(resp.text, base_url)
        if cas_url2:
            token_post_url = cas_url2

    token_payload = parser.params.copy()
    token_payload["token"] = get_totp_token(seed)

    if verbose:
        print(f"      POST先: {token_post_url}")
        sanitized = {k: (v if k not in ("password", "token") else "***") for k, v in token_payload.items()}
        print(f"      パラメータ: {sanitized}")

    # 数回リトライ（TOTPの時間ずれ対策）
    max_retries = 3
    for attempt in range(max_retries):
        if verbose:
            print(f"      POST試行 {attempt + 1}/{max_retries} → {token_post_url}")
        resp = session.post(
            token_post_url,
            data=token_payload,
            allow_redirects=False,
            timeout=(10.0, 30.0),
        )
        if verbose:
            print(f"      応答: {resp.status_code}")
            if resp.headers.get("Location"):
                print(f"      Location: {resp.headers['Location'][:100]}")
            print(f"      応答ボディ (先頭200文字): {resp.text[:200]}")

        if resp.status_code in (302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not silent or verbose:
                print(f"      リダイレクト: {location[:80]}...")
            resp = session.get(
                location if location.startswith("http") else urljoin(base_url, location),
                allow_redirects=True,
            )
            break
        elif resp.status_code == 401:
            if not silent or verbose:
                print(f"      認証失敗 (試行 {attempt + 1}/{max_retries})、トークン再生成...")
            token_payload["token"] = get_totp_token(seed)
            continue
        else:
            resp.raise_for_status()
    else:
        raise RuntimeError(
            "多要素認証に失敗しました。TOTPシード値を確認してください。\n"
            "詳細を確認するには --verbose オプションを付けて再実行してください。"
        )

    # Step 4: セッション有効性確認
    if not silent:
        print("[4/4] セッション確認中...")

    # portal にアクセスしてログイン状態を確認
    check_resp = session.get(f"{base_url}/portal", allow_redirects=True)
    if "loggedIn" not in check_resp.text and "site" not in check_resp.text.lower():
        raise RuntimeError(
            "ログインに失敗しました。アカウント情報を確認してください。"
        )

    if not silent:
        print("ログイン成功")
    return session
