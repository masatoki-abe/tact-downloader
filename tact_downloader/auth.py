import json
import os
import tempfile
import time
from pathlib import Path

import requests

from tact_downloader import COOKIE_FILE
from tact_downloader.client import DEFAULT_TIMEOUT
from tact_downloader.exceptions import AuthenticationError, NetworkError


def _load_saved_cookies(cookie_path):
    """保存済みCookieを検証して返す。不正なファイルは明示的に失敗させる。"""
    try:
        os.chmod(cookie_path, 0o600)
        with open(cookie_path) as f:
            cookies = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"保存Cookieを読み込めません: {exc}") from exc

    if not isinstance(cookies, list):
        raise ValueError("保存Cookieの形式が不正です（配列が必要です）")
    for cookie in cookies:
        if (
            not isinstance(cookie, dict)
            or not isinstance(cookie.get("name"), str)
            or not isinstance(cookie.get("value"), str)
        ):
            raise ValueError("保存Cookieの形式が不正です")
    return cookies


def _save_cookies(cookie_path, cookies):
    """Cookieを所有者専用の一時ファイルへ保存して原子的に置換する。"""
    cookie_path = Path(cookie_path)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cookie_path.parent,
            prefix=f".{cookie_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.chmod(temporary.fileno(), 0o600)
            json.dump(cookies, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, cookie_path)
        os.chmod(cookie_path, 0o600)
    except OSError as exc:
        raise AuthenticationError(f"Cookieの保存に失敗しました: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def login(
    base_url: str,
    silent: bool = False,
    verbose: bool = False,
) -> requests.Session:
    """TACTにログインし、認証済みセッションを返す。

    以下の優先順位で認証を試みる:
      1. 保存済み認証 Cookie の再利用
      2. ブラウザを開いて自動ログイン（環境変数 THERS_EMAIL 等があれば自動入力）
      3. ブラウザを開いてユーザーに手動ログインしてもらう

    Args:
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

    if not silent:
        print("TACT にログインしています...")

    # ---- Phase A: 保存済み Cookie を試す ----
    cookie_path = Path(COOKIE_FILE)
    if cookie_path.exists():
        if not silent:
            print("保存済み Cookie を確認中...")
        try:
            saved_cookies = _load_saved_cookies(cookie_path)
            for c in saved_cookies:
                session.cookies.set(
                    c["name"],
                    c["value"],
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
            try:
                test_resp = session.get(
                    f"{base_url}/portal",
                    allow_redirects=True,
                    timeout=DEFAULT_TIMEOUT,
                )
            except requests.RequestException as exc:
                raise NetworkError(f"TACTへの通信に失敗しました: {exc}") from exc
            if '"loggedIn": true' in test_resp.text:
                test_resp.close()
                if not silent:
                    print("ログイン成功 (Cookie再利用)")
                return session
            test_resp.close()
            if verbose:
                print("      保存 Cookie は期限切れです")
        except NetworkError:
            raise
        except Exception as e:
            if verbose:
                print(f"      Cookie読み込みエラー: {e}")

    # ---- Phase B: ブラウザでログイン ----
    email = os.environ.get("THERS_EMAIL")
    password = os.environ.get("THERS_PASSWORD")
    totp_secret = os.environ.get("THERS_TOTP_SECRET")
    auto_mode = bool(email and password)

    if auto_mode:
        print()
        print("=" * 60)
        print("  TACT に自動ログインします...")
        if not totp_secret:
            print("  TOTPコードの手動入力を待機します。")
        print("=" * 60)
        print()
    else:
        print()
        print("=" * 60)
        print("  TACT にログインしてください。")
        print("  ブラウザが開くので、ログイン後は自動的に処理が続行されます。")
        print("  Cookie は自動保存され、次回からは再利用されます。")
        print("=" * 60)
        print()

    return _login_with_browser(
        session,
        base_url,
        cookie_path,
        email,
        password,
        totp_secret,
        auto_mode,
        silent,
        verbose,
    )


def _login_with_browser(
    session,
    base_url,
    cookie_path,
    email,
    password,
    totp_secret,
    auto_mode,
    silent,
    verbose,
):
    """Playwrightによるログイン処理。ログイン選択部分から分離している。"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                no_viewport=True,
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(
                f"{base_url}/portal", wait_until="domcontentloaded", timeout=30000
            )

            if auto_mode:
                try:
                    _auto_fill_login(page, email, password, totp_secret, silent)
                except Exception as e:
                    if not silent:
                        print(f"  自動入力中にエラーが発生しました: {e}")
                        print("  手動でログインを続行してください。")

            for _ in range(300):
                time.sleep(1)
                try:
                    if '"loggedIn": true' in page.content():
                        cookies = context.cookies(base_url)
                        _save_cookies(cookie_path, cookies)
                        if verbose:
                            print(
                                f"      Cookie {len(cookies)} 個を保存: {COOKIE_FILE}"
                            )
                        for c in cookies:
                            session.cookies.set(
                                c["name"],
                                c["value"],
                                domain=c["domain"],
                                path=c["path"],
                            )
                        if not silent:
                            print("ログイン成功")
                        browser.close()
                        return session
                except AuthenticationError:
                    raise
                except Exception:
                    pass

            browser.close()
    except ImportError:
        print()
        print("  Playwright がインストールされていません。")
        print("  以下の手順で手動セットアップしてください:")
        print()
        print(f"  1. ブラウザで {base_url}/portal にアクセスしてログイン")
        print("  2. ブラウザ拡張機能で Cookie を JSON 形式でエクスポート")
        print(f"  3. {COOKIE_FILE} に保存")
        print("  4. このスクリプトを再実行")
        print()
    except Exception as e:
        raise AuthenticationError(
            f"ブラウザログイン中にエラーが発生しました:\n  {e}\n"
        ) from e

    raise AuthenticationError("ログインに失敗しました。")


def _auto_fill_login(page, email, password, totp_secret, silent):
    """全ログインフローを順に実行。

    画面遷移:
      TACTポータル → MSメール → MSパスワード → MSTOTP
      → MSサインイン維持 → 機構同意 → TACTポータル(完了)
    """
    page.wait_for_load_state("domcontentloaded")

    _tact_portal_login(page)  # 1. TACTポータル → MS SSO
    _ms_email(page, email)  # 2. MS メールアドレス入力
    _ms_password(page, password)  # 3. MS パスワード入力
    if totp_secret:
        _ms_totp(page, totp_secret)  # 4. MS TOTP認証
    elif not silent:
        print("  認証アプリのコードを手動で入力してください...")
    _ms_stay_signed_in(page)  # 5. MS サインイン維持（いいえ）
    _thers_consent(page)  # 6. 機構同意画面（同意）


# ============================================================
#  1: TACT ポータル → Microsoft SSO リダイレクト
# ============================================================


def _tact_portal_login(page):
    """【1: TACTポータル】「Federation Login」リンクをクリック。"""
    with page.expect_navigation(timeout=30000):
        page.locator("a#loginLink1").first.click(timeout=5000)


# ============================================================
#  2: Microsoft メールアドレス入力
# ============================================================


def _ms_email(page, email):
    """【2: MS メールアドレス入力画面】"""
    page.locator('input[type="email"]').first.wait_for(timeout=30000)
    page.locator('input[type="email"]').first.fill(email)
    page.locator("#idSIButton9").first.wait_for(timeout=15000)
    page.locator("#idSIButton9").first.click()
    page.locator('input[type="password"]').first.wait_for(timeout=15000)


# ============================================================
#  3: Microsoft パスワード入力
# ============================================================


def _ms_password(page, password):
    """【3: MS パスワード入力画面】"""
    page.locator('input[type="password"]').first.wait_for(timeout=30000)
    page.locator('input[type="password"]').first.fill(password)
    page.locator("#idSIButton9").first.wait_for(timeout=15000)
    page.locator("#idSIButton9").first.click()


# ============================================================
#  4: Microsoft TOTP 認証
# ============================================================


def _ms_totp(page, totp_secret):
    """【4: MS TOTP認証画面】コード自動生成→Enter。

    プッシュ通知画面の場合は「別の方法」→ TOTP選択 を辿る。
    """
    import pyotp

    totp_input = page.locator('input#idTxtBx_SAOTCC_OTC, input[type="tel"]')
    try:
        totp_input.first.wait_for(timeout=5000)
    except Exception:
        try:
            page.locator("a#signInAnotherWay").first.click(timeout=5000)
            page.locator('div[data-value="PhoneAppOTP"]').first.wait_for(timeout=5000)
            page.locator('div[data-value="PhoneAppOTP"]').first.click(timeout=5000)
        except Exception:
            pass
        totp_input.first.wait_for(timeout=15000)

    code = pyotp.TOTP(totp_secret).now()
    totp_input.first.fill(code)
    page.keyboard.press("Enter")


# ============================================================
#  5: Microsoft サインイン維持画面
# ============================================================


def _ms_stay_signed_in(page):
    """【5: MS サインイン維持画面】→ いいえ"""
    try:
        page.locator("#KmsiCheckboxField").first.wait_for(timeout=10000)
        page.locator("#idBtn_Back").first.click(timeout=5000)
    except Exception:
        pass


# ============================================================
#  6: 機構同意画面
# ============================================================


def _thers_consent(page):
    """【6: 機構同意画面】→ 同意"""
    page.locator('input[value="同意"]').first.wait_for(timeout=60000)
    page.locator('input[value="同意"]').first.click(timeout=5000)
