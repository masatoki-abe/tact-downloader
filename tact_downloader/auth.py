import json
from pathlib import Path

import requests

from tact_downloader import COOKIE_FILE


def login(
    base_url: str,
    silent: bool = False,
    verbose: bool = False,
) -> requests.Session:
    """TACTにログインし、認証済みセッションを返す。

    以下の優先順位で認証を試みる:
      1. 保存済み認証 Cookie の再利用
      2. ブラウザを開いてユーザーにログインしてもらい Cookie を保存

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
            with open(cookie_path) as f:
                saved_cookies = json.load(f)
            for c in saved_cookies:
                session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
            test_resp = session.get(f"{base_url}/portal", allow_redirects=True)
            if '"loggedIn": true' in test_resp.text:
                if not silent:
                    print("ログイン成功 (Cookie再利用)")
                return session
            if verbose:
                print("      保存 Cookie は期限切れです")
        except Exception as e:
            if verbose:
                print(f"      Cookie読み込みエラー: {e}")

    # ---- Phase B: ブラウザでログインしてもらい Cookie を保存 ----
    print()
    print("=" * 60)
    print("  TACT にログインしてください。")
    print("  ブラウザが開くので、ログイン後は自動的に処理が続行されます。")
    print("  Cookie は自動保存され、次回からは再利用されます。")
    print("=" * 60)
    print()

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = browser.new_context(
                no_viewport=True,
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(f"{base_url}/portal", wait_until="domcontentloaded", timeout=30000)

            import time
            for _ in range(300):
                time.sleep(1)
                try:
                    if '"loggedIn": true' in page.content():
                        cookies = context.cookies()
                        with open(cookie_path, "w") as f:
                            json.dump(cookies, f, ensure_ascii=False, indent=2)
                        if verbose:
                            print(f"      Cookie {len(cookies)} 個を保存: {COOKIE_FILE}")
                        for c in cookies:
                            session.cookies.set(
                                c["name"], c["value"],
                                domain=c["domain"], path=c["path"],
                            )
                        if not silent:
                            print("ログイン成功")
                        browser.close()
                        return session
                except Exception:
                    pass

            browser.close()
    except ImportError:
        print()
        print("  Playwright がインストールされていません。")
        print("  以下の手順で手動セットアップしてください:")
        print()
        print(f"  1. ブラウザで {base_url}/portal にアクセスしてログイン")
        print(f"  2. ブラウザ拡張機能で Cookie を JSON 形式でエクスポート")
        print(f"  3. {COOKIE_FILE} に保存")
        print(f"  4. このスクリプトを再実行")
        print()
    except Exception as e:
        raise RuntimeError(
            f"ブラウザログイン中にエラーが発生しました:\n  {e}\n"
        )

    raise RuntimeError("ログインに失敗しました。")
