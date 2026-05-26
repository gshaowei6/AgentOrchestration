import json

from src.sdk.client import OrchestratorClient


class _Response:
    def __init__(self, payload=b"", status=200):
        self._payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._payload


def _client():
    return OrchestratorClient(
        base_url="https://example.test",
        api_key="test-token",
    )


def test_request_returns_empty_result_for_204_no_content(monkeypatch):
    captured = {}

    def fake_urlopen(request):
        captured["method"] = request.get_method()
        captured["url"] = request.full_url
        return _Response(status=204)

    monkeypatch.setattr("src.sdk.client.urlopen", fake_urlopen)

    assert _client().delete_agent("agent-1") == {}
    assert captured == {
        "method": "DELETE",
        "url": "https://example.test/api/v2/agents/agent-1",
    }


def test_request_returns_empty_result_for_empty_success_body(monkeypatch):
    monkeypatch.setattr(
        "src.sdk.client.urlopen",
        lambda request: _Response(payload=b"", status=200),
    )

    assert _client().stop_agent("agent-1") == {}


def test_request_returns_empty_result_for_whitespace_success_body(monkeypatch):
    monkeypatch.setattr(
        "src.sdk.client.urlopen",
        lambda request: _Response(payload=b" \n\t ", status=202),
    )

    assert _client().stop_agent("agent-1") == {}


def test_request_still_decodes_json_success_body(monkeypatch):
    expected = {"id": "agent-1", "status": "stopped"}

    def fake_urlopen(request):
        return _Response(payload=json.dumps(expected).encode(), status=200)

    monkeypatch.setattr(
        "src.sdk.client.urlopen",
        fake_urlopen,
    )

    assert _client().stop_agent("agent-1") == expected
