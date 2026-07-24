"""HTTPクライアントのエラー処理回帰テスト。"""

from unittest.mock import Mock

import pytest
import requests

from tact_downloader.client import DEFAULT_TIMEOUT, TACTClient
from tact_downloader.exceptions import AuthenticationError, DataError, NetworkError


def response_with_status(status: int) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = "https://tact.example.test/api"
    response.request = requests.Request("GET", response.url).prepare()
    return response


@pytest.mark.parametrize("status", [404, 500])
def test_http_errors_are_propagated_without_retry(status: int) -> None:
    session = Mock()
    session.get.return_value = response_with_status(status)
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(NetworkError) as exc_info:
        client._get("https://tact.example.test/api")  # pyright: ignore[reportPrivateUsage]

    assert str(status) in str(exc_info.value)
    session.get.assert_called_once()


def test_401_is_reported_as_authentication_error() -> None:
    session = Mock()
    session.get.return_value = response_with_status(401)
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(AuthenticationError, match="セッションが切れました"):
        client._get("https://tact.example.test/api")  # pyright: ignore[reportPrivateUsage]


def test_timeout_is_propagated() -> None:
    session = Mock()
    session.get.side_effect = requests.ConnectTimeout("timeout")
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(NetworkError) as exc_info:
        client.get_sites()
    assert isinstance(exc_info.value.__cause__, requests.ConnectTimeout)


def test_invalid_json_is_not_treated_as_empty_response() -> None:
    response = Mock()
    response.status_code = 200
    response.is_redirect = False
    response.is_permanent_redirect = False
    response.json.side_effect = ValueError("invalid json")
    session = Mock()
    session.get.return_value = response
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(DataError, match="サイト一覧のJSONが不正"):
        client.get_sites()


def test_http_url_is_rejected_before_request() -> None:
    session = Mock()
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(ValueError):
        client._get("http://tact.example.test/api")  # pyright: ignore[reportPrivateUsage]
    session.get.assert_not_called()


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_retryable_status_is_retried_until_success(status: int) -> None:
    session = Mock()
    first = response_with_status(status)
    success = response_with_status(200)
    session.get.side_effect = [first, success]
    client = TACTClient(session, "https://tact.example.test")

    result = client._get(  # pyright: ignore[reportPrivateUsage]
        "https://tact.example.test/api"
    )

    assert result is success
    assert session.get.call_count == 2


def test_retryable_status_stops_after_retry_limit() -> None:
    session = Mock()
    responses = [response_with_status(503) for _ in range(3)]
    session.get.side_effect = responses
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(NetworkError):
        client._get("https://tact.example.test/api")  # pyright: ignore[reportPrivateUsage]

    assert session.get.call_count == 3


def test_default_timeout_is_applied() -> None:
    session = Mock()
    session.get.return_value = response_with_status(200)
    client = TACTClient(session, "https://tact.example.test")

    client._get("https://tact.example.test/api")  # pyright: ignore[reportPrivateUsage]

    session.get.assert_called_once_with(
        "https://tact.example.test/api",
        allow_redirects=False,
        timeout=DEFAULT_TIMEOUT,
    )
