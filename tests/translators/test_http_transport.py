"""F4 WI-6: loopback HTTP transport against a real in-process fake service (D3, D9, matrix Q2/Q13).

No Python object is mocked: requests go over real 127.0.0.1 sockets. The real
refused-connection branch is covered by WI-7 ``test_unreachable_end_to_end`` (Q13).
"""

import threading
import time
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from snapocr.translators.config import TranslatorConfig
from snapocr.translators.errors import ErrorContext, TranslationError, TranslationErrorKind
from snapocr.translators.http_transport import post_json
from snapocr.translators.protocol import ChatRequest, build_chat_request
from support.fake_openai_server import FakeOpenAIServer, Reply, echo_body
from support.leakcheck import no_leak
from support.tr_strategies import ok

pytestmark = pytest.mark.usefixtures("loopback_guard")

K = TranslationErrorKind
LIMIT = 1_048_576
CHAT_OK = ok("The weather is very nice today.")
M = "ZQXJ0f1e2d3c4b5a"


def _ctx(fake):
    return ErrorContext(fake.base_url, "hy-mt2:7b")


def _req(fake, text="你好"):
    return build_chat_request(TranslatorConfig(base_url=fake.base_url), "en", text)


def _post(fake, request=None, timeout_s=2.0, **kw):
    return post_json(fake.endpoint, request or _req(fake), timeout_s, ctx=_ctx(fake), **kw)


def _fails(fake, kind, **kw):
    with pytest.raises(TranslationError) as info:
        _post(fake, **kw)
    err = info.value
    assert err.kind is kind
    assert fake.base_url in str(err)
    assert "hy-mt2:7b" in str(err)
    return err


def test_roundtrip_bytes_and_request_shape(fake_server, loopback_guard):
    fake = fake_server
    fake.reset()
    fake.script(Reply(200, {"X-Test": "1"}, CHAT_OK))
    req = _req(fake)
    assert _post(fake, req) == (200, CHAT_OK)
    [rec] = fake.requests
    assert (rec.method, rec.path, rec.body) == ("POST", "/v1/chat/completions", req.body)
    assert set(rec.headers) == {"host", "accept-encoding", "content-length", "content-type", "accept"}
    assert rec.headers["host"] == f"127.0.0.1:{fake.port}"
    assert rec.headers["content-length"] == str(len(req.body))
    assert ("connect", ("127.0.0.1", fake.port)) in loopback_guard.allowed


@settings(max_examples=25, deadline=None)
@given(st.binary(max_size=4096), st.binary(max_size=4096), st.sampled_from([200, 404, 500, 307]))
def test_body_roundtrip_property(fake_server, req_body, resp_body, status):
    fake = fake_server
    fake.reset()
    fake.script(Reply(status, body=resp_body))
    req = ChatRequest("/v1/chat/completions", {"Content-Type": "application/json"}, req_body)
    assert _post(fake, req) == (status, resp_body)
    assert [r.body for r in fake.requests] == [req_body]


def test_connection_closed_after_each_call(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(Reply(body=CHAT_OK), Reply(body=CHAT_OK))
    _post(fake)
    assert fake.wait_closed() == 0
    _post(fake)
    assert fake.wait_closed() == 0
    first, second = fake.requests
    assert first.client[1] != second.client[1]


def test_concurrent_calls_isolated(fake_server):
    fake = fake_server
    fake.reset()
    fake.respond_with(echo_body())
    barrier = threading.Barrier(8)
    results: dict[int, tuple[int, bytes]] = {}

    def worker(i):
        req = ChatRequest("/v1/chat/completions", {}, f"body-{i}".encode() * (i + 1))
        barrier.wait()
        results[i] = _post(fake, req)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert {i: r for i, r in results.items()} == {
        i: (200, f"body-{i}".encode() * (i + 1)) for i in range(8)
    }
    assert len(fake.requests) == 8


def test_timeout_before_headers(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(Reply(body=CHAT_OK, delay_s=1.0))
    start = time.monotonic()
    err = _fails(fake, K.TIMEOUT, timeout_s=0.2)
    assert time.monotonic() - start < 0.9
    assert err.detail == "TimeoutError"


def test_timeout_mid_body(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(
        Reply(raw=b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + b"x" * 10,
              stall_after_chunks_s=1.0)
    )
    start = time.monotonic()
    _fails(fake, K.TIMEOUT, timeout_s=0.2)
    assert time.monotonic() - start < 0.9


def test_timeout_is_per_read_not_total(fake_server):
    fake = fake_server
    fake.reset()
    chunks = [b"aaaa", b"bbbb", b"cccc", b"dddd", b"eeee"]
    fake.script(Reply(chunks=chunks, chunk_gap_s=0.15))
    assert _post(fake, timeout_s=0.4) == (200, b"".join(chunks))


@pytest.mark.parametrize(
    ("reply", "detail"),
    [
        (Reply(close_after_request=True), "RemoteDisconnected"),
        (Reply(raw=M.encode() + b"\r\n\r\n"), "BadStatusLine"),
        (Reply(raw=b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort"), "IncompleteRead"),
        (Reply(reset_after_request=True), "ConnectionResetError"),
    ],
    ids=["disconnect", "bad-status-line", "incomplete-read", "reset"],
)
def test_connection_errors_map_to_connection(fake_server, reply, detail):
    fake = fake_server
    fake.reset()
    fake.script(reply)
    err = _fails(fake, K.CONNECTION)
    assert err.detail == detail
    no_leak(err, M)


def test_oversize_body(fake_server):
    fake = fake_server
    fake.reset()
    exact = b"x" * LIMIT
    fake.script(Reply(body=exact), Reply(body=exact + b"x"))
    assert _post(fake) == (200, exact)
    err = _fails(fake, K.BAD_RESPONSE)
    assert "1048576" in err.detail
    fake.script(Reply(raw=b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + exact + b"x"))
    _fails(fake, K.BAD_RESPONSE)
    fake.script(Reply(body=b"y" * 10), Reply(body=b"y" * 11))
    assert _post(fake, max_response_bytes=10) == (200, b"y" * 10)
    err = _fails(fake, K.BAD_RESPONSE, max_response_bytes=10)
    assert "10" in err.detail


def _stalled_oversize():
    head = b"HTTP/1.1 200 OK\r\nContent-Length: 4194304\r\n\r\n"
    return Reply(raw=head + b"x" * (LIMIT + 1), stall_after_chunks_s=30)


def test_oversize_stops_reading(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(_stalled_oversize())
    start = time.monotonic()
    _fails(fake, K.BAD_RESPONSE, timeout_s=10)
    assert time.monotonic() - start < 2


def test_connection_closed_after_errors(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(_stalled_oversize())
    _fails(fake, K.BAD_RESPONSE, timeout_s=10)
    assert fake.wait_closed() == 0
    fake.script(Reply(raw=b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort"))
    _fails(fake, K.CONNECTION)
    assert fake.wait_closed() == 0
    # Here the server keeps its side open, so only a client-side close ends it.
    fake.script(
        Reply(raw=b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort", stall_after_chunks_s=30)
    )
    _fails(fake, K.TIMEOUT, timeout_s=0.3)
    assert fake.wait_closed() == 0


def test_redirect_not_followed(fake_server, loopback_guard):
    fake = fake_server
    fake.reset()
    fake.script(Reply(307, {"Location": "http://example.com/"}, b"moved"))
    assert _post(fake) == (307, b"moved")
    assert len(fake.requests) == 1
    assert loopback_guard.blocked == []
    fake.reset()
    fake.script(Reply(302, {"Location": f"http://127.0.0.1:{fake.port}/elsewhere"}, b""))
    assert _post(fake) == (302, b"")
    assert len(fake.requests) == 1


def test_proxy_env_ignored(fake_server, monkeypatch):
    fake = fake_server
    fake.reset()
    fake.script(Reply(201, body=b"direct"))
    with FakeOpenAIServer() as proxy:
        proxy.script(Reply(200, body=b"via proxy"))
        for name in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
            monkeypatch.setenv(name, proxy.base_url)
            monkeypatch.setenv(name.lower(), proxy.base_url)
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        assert _post(fake) == (201, b"direct")
        assert len(proxy.requests) == 0
    assert len(fake.requests) == 1


def test_rejects_unvalidated_endpoint(fake_server, loopback_guard):
    fake = fake_server
    fake.reset()
    before = len(loopback_guard.allowed)
    fakes = [
        fake.base_url,
        SimpleNamespace(host="127.0.0.1", port=fake.port, url=fake.base_url),
    ]
    for endpoint in fakes:
        with pytest.raises(TypeError):
            post_json(endpoint, _req(fake), 2.0, ctx=_ctx(fake))  # type: ignore[arg-type]
    assert len(loopback_guard.allowed) == before
    assert fake.requests == []


def test_all_targets_loopback(loopback_guard):
    # Kept last in the module; the fixture's teardown checks again.
    assert loopback_guard.blocked == []
    assert loopback_guard.allowed
    for _kind, target in loopback_guard.allowed:
        host = target[0] if isinstance(target, tuple) else target
        assert host == "127.0.0.1"
