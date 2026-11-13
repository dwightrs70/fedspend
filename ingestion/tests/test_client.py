from unittest.mock import MagicMock

from ingestion.usaspending_client import USAspendingClient


def _client_with_response(payload):
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = payload
    session.post.return_value = response
    return USAspendingClient(session=session), session


def test_list_monthly_files_sends_expected_payload():
    client, session = _client_with_response({"monthly_files": []})
    client.list_monthly_files(agency=7, fiscal_year=2025, file_type="contracts")
    args, kwargs = session.post.call_args
    assert args[0] == "https://api.usaspending.gov/api/v2/bulk_download/list_monthly_files/"
    assert kwargs["json"] == {"agency": 7, "fiscal_year": 2025, "type": "contracts"}


def test_raise_for_status_is_called():
    client, session = _client_with_response({})
    client.list_agencies()
    session.post.return_value.raise_for_status.assert_called_once()


def test_head_content_length_returns_int():
    session = MagicMock()
    session.head.return_value.headers = {"Content-Length": "12345"}
    client = USAspendingClient(session=session)
    assert client.head_content_length("https://example.com/f.zip") == 12345


def test_head_content_length_returns_none_on_failure():
    import requests

    session = MagicMock()
    session.head.side_effect = requests.ConnectionError("boom")
    client = USAspendingClient(session=session)
    assert client.head_content_length("https://example.com/f.zip") is None
