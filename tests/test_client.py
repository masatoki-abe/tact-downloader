"""HTTPクライアントのエラー処理回帰テスト。"""

from unittest.mock import Mock

import pytest
import requests

from tact_downloader.client import TACTClient


def response_with_status(status):
    response = requests.Response()
    response.status_code = status
    response.url = "https://tact.example.test/api"
    response.request = requests.Request("GET", response.url).prepare()
    return response


@pytest.mark.parametrize("status", [404, 429, 500])
def test_http_errors_are_propagated_without_retry(status):
    session = Mock()
    session.get.return_value = response_with_status(status)
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(requests.HTTPError) as exc_info:
        client._get("https://tact.example.test/api")

    assert exc_info.value.response.status_code == status
    session.get.assert_called_once()


def test_401_is_reported_as_authentication_error():
    session = Mock()
    session.get.return_value = response_with_status(401)
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(RuntimeError, match="セッションが切れました"):
        client._get("https://tact.example.test/api")


def test_timeout_is_propagated():
    session = Mock()
    session.get.side_effect = requests.ConnectTimeout("timeout")
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(requests.ConnectTimeout):
        client.get_sites()


def test_invalid_json_is_not_treated_as_empty_response():
    response = Mock()
    response.status_code = 200
    response.is_redirect = False
    response.is_permanent_redirect = False
    response.json.side_effect = ValueError("invalid json")
    session = Mock()
    session.get.return_value = response
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(ValueError, match="invalid json"):
        client.get_sites()


def test_http_url_is_rejected_before_request():
    session = Mock()
    client = TACTClient(session, "https://tact.example.test")

    with pytest.raises(ValueError):
        client._get("http://tact.example.test/api")
    session.get.assert_not_called()
