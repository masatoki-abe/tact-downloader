"""認証経路の回帰テスト。"""

import json
import os
from unittest.mock import Mock, patch

import pytest

from tact_downloader import auth
from tact_downloader.client import DEFAULT_TIMEOUT


def test_reuses_valid_saved_cookie(tmp_path):
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(json.dumps([{"name": "sid", "value": "value"}]))
    session = Mock()
    session.cookies = Mock()
    session.headers = {}
    response = Mock(text='{"loggedIn": true}')
    session.get.return_value = response

    with (
        patch.object(auth, "COOKIE_FILE", str(cookie_path)),
        patch.object(auth.requests, "Session", return_value=session),
        patch.object(auth, "_login_with_browser") as browser_login,
    ):
        result = auth.login("https://tact.example.test", silent=True)

    assert result is session
    session.cookies.set.assert_called_once_with("sid", "value", domain="", path="/")
    session.get.assert_called_once_with(
        "https://tact.example.test/portal",
        allow_redirects=True,
        timeout=DEFAULT_TIMEOUT,
    )
    browser_login.assert_not_called()


def test_expired_cookie_falls_back_to_browser_login(tmp_path):
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(json.dumps([]))
    session = Mock()
    session.cookies = Mock()
    session.headers = {}
    session.get.return_value = Mock(text="logged out")

    with (
        patch.object(auth, "COOKIE_FILE", str(cookie_path)),
        patch.object(auth.requests, "Session", return_value=session),
        patch.object(
            auth, "_login_with_browser", return_value=session
        ) as browser_login,
    ):
        result = auth.login("https://tact.example.test", silent=True)

    assert result is session
    browser_login.assert_called_once()


def test_auto_fill_login_calls_steps_in_order():
    page = Mock()
    calls = []
    with (
        patch.object(
            auth, "_tact_portal_login", side_effect=lambda *_: calls.append("portal")
        ),
        patch.object(auth, "_ms_email", side_effect=lambda *_: calls.append("email")),
        patch.object(
            auth, "_ms_password", side_effect=lambda *_: calls.append("password")
        ),
        patch.object(auth, "_ms_totp", side_effect=lambda *_: calls.append("totp")),
        patch.object(
            auth, "_ms_stay_signed_in", side_effect=lambda *_: calls.append("stay")
        ),
        patch.object(
            auth, "_thers_consent", side_effect=lambda *_: calls.append("consent")
        ),
    ):
        auth._auto_fill_login(page, "email", "password", "secret", silent=True)

    assert calls == ["portal", "email", "password", "totp", "stay", "consent"]


def test_saved_cookie_permissions_are_restricted(tmp_path):
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(json.dumps([]))
    cookie_path.chmod(0o644)

    assert auth._load_saved_cookies(cookie_path) == []
    assert os.stat(cookie_path).st_mode & 0o777 == 0o600


def test_save_cookies_is_atomic_and_restricts_permissions(tmp_path):
    cookie_path = tmp_path / "cookies.json"
    cookies = [{"name": "sid", "value": "value"}]

    with patch.object(auth.os, "replace", wraps=os.replace) as replace:
        auth._save_cookies(cookie_path, cookies)

    replace.assert_called_once()
    assert json.loads(cookie_path.read_text()) == cookies
    assert os.stat(cookie_path).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize(
    "contents",
    ["not json", json.dumps({"name": "sid", "value": "value"}), json.dumps([{}])],
)
def test_invalid_saved_cookie_falls_back_to_browser_login(tmp_path, contents):
    cookie_path = tmp_path / "cookies.json"
    cookie_path.write_text(contents)
    session = Mock()
    session.cookies = Mock()
    session.headers = {}
    session.get.return_value = Mock(text="logged out")

    with (
        patch.object(auth, "COOKIE_FILE", str(cookie_path)),
        patch.object(auth.requests, "Session", return_value=session),
        patch.object(
            auth, "_login_with_browser", return_value=session
        ) as browser_login,
    ):
        assert auth.login("https://tact.example.test", silent=True) is session

    browser_login.assert_called_once()


def test_save_cookie_failure_removes_temporary_file(tmp_path):
    cookie_path = tmp_path / "cookies.json"

    with (
        patch.object(auth.os, "replace", side_effect=OSError("disk full")),
        pytest.raises(auth.AuthenticationError, match="Cookieの保存に失敗しました"),
    ):
        auth._save_cookies(cookie_path, [{"name": "sid", "value": "value"}])

    assert list(tmp_path.glob("*.tmp")) == []
