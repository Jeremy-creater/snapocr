"""Positive controls for the fake OpenAI-compatible service (matrix S1-S5).

Talks to it with plain ``http.client`` so these don't depend on the code under test.
"""

import http.client
import json
import threading
import time

import pytest

from support.fake_openai_server import FakeOpenAIServer, Reply, echo


def _request(port, method="POST", path="/x", body=b"abc", timeout=5):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def test_fake_server_scripted_reply(fake_server):
    fake_server.reset()
    fake_server.script(Reply(201, {"X-A": "1"}, b"zz"))
    status, headers, body = _request(fake_server.port)
    assert (status, headers["X-A"], body) == (201, "1", b"zz")
    [rec] = fake_server.requests
    assert (rec.method, rec.path, rec.body) == ("POST", "/x", b"abc")


def test_fake_server_raw_modes(fake_server):
    fake_server.reset()
    fake_server.script(
        Reply(raw=b"garbage\r\n"),
        Reply(close_after_request=True),
        Reply(raw=b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort"),
        Reply(reset_after_request=True),
    )
    with pytest.raises(http.client.BadStatusLine) as bad:
        _request(fake_server.port)
    assert not isinstance(bad.value, http.client.RemoteDisconnected)
    with pytest.raises(http.client.RemoteDisconnected):
        _request(fake_server.port)
    with pytest.raises(http.client.IncompleteRead):
        _request(fake_server.port)
    with pytest.raises(ConnectionResetError) as reset:
        _request(fake_server.port)
    assert not isinstance(reset.value, http.client.RemoteDisconnected)


def test_fake_server_delay_and_fast_teardown():
    with FakeOpenAIServer() as fake:
        fake.script(Reply(body=b"late", delay_s=0.3))
        start = time.monotonic()
        assert _request(fake.port)[2] == b"late"
        assert time.monotonic() - start >= 0.3

        fake.script(Reply(body=b"never", delay_s=30))
        errors = []

        def slow():
            try:
                _request(fake.port, timeout=10)
            except Exception as exc:  # the server goes away mid-request
                errors.append(exc)

        t = threading.Thread(target=slow, daemon=True)
        t.start()
        deadline = time.monotonic() + 2
        while len(fake.requests) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        start = time.monotonic()
    assert time.monotonic() - start < 0.5
    t.join(5)
    assert errors


def test_fake_server_unscripted_and_reset(fake_server):
    fake_server.reset()
    status, _, body = _request(fake_server.port)
    assert (status, body) == (500, b"unscripted")
    assert fake_server.wait_closed() == 0
    fake_server.script(Reply(body=b"queued"))
    fake_server.reset()
    assert fake_server.requests == []
    assert _request(fake_server.port)[2] == b"unscripted"


def test_fake_server_echo(fake_server):
    fake_server.reset()
    fake_server.respond_with(echo())
    payload = json.dumps({"messages": [{"role": "user", "content": "你好"}]}).encode()
    status, _, body = _request(fake_server.port, body=payload)
    assert status == 200
    assert json.loads(body)["choices"][0]["message"]["content"] == "你好"
