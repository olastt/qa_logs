import httpx

from qa_release_bot.api_http import request_with_retry


class _FakeClient:
    def __init__(self, statuses: list[int]):
        self._statuses = statuses
        self.calls = 0

    def request(self, method: str, url: str, **kwargs):
        self.calls += 1
        status = self._statuses[min(self.calls - 1, len(self._statuses) - 1)]
        req = httpx.Request(method, url)
        return httpx.Response(status, request=req)


def test_retry_on_429_then_success():
    client = _FakeClient([429, 200])
    resp = request_with_retry(client, "GET", "/x", max_retries=3, retry_base_sec=0.01)
    assert resp.status_code == 200
    assert client.calls == 2
