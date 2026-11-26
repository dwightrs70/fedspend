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


def _response(status_code, headers=None):
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    return response


def test_remote_size_uses_ranged_get_content_range():
    session = MagicMock()
    session.get.return_value = _response(206, {"Content-Range": "bytes 0-0/7382686"})
    client = USAspendingClient(session=session)
    assert client.remote_size("https://example.com/f.zip") == (7382686, "")
    session.head.assert_not_called()
    session.get.return_value.close.assert_called_once()
    assert session.get.call_args.kwargs["headers"]["Range"] == "bytes=0-0"
    assert session.get.call_args.kwargs["headers"]["Connection"] == "close"


def test_remote_size_falls_back_to_head_when_ranged_get_fails():
    import requests

    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("dropped")
    session.head.return_value = _response(200, {"Content-Length": "555"})
    client = USAspendingClient(session=session)
    assert client.remote_size("https://example.com/f.zip") == (555, "")


def test_remote_size_reports_reason_when_everything_fails():
    import requests

    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("Empty reply")
    session.head.side_effect = requests.ConnectionError("boom")
    client = USAspendingClient(session=session)
    size, note = client.remote_size("https://example.com/f.zip")
    assert size is None
    assert "ranged GET error ConnectionError" in note
    assert "HEAD error ConnectionError" in note
