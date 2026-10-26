"""Positive control for the network guard (unit lane, no models).

Every "zero connection attempts" assertion in the engine lane is only as good
as this guard. These tests prove it actually refuses and records attempts.
"""

import socket
import urllib.error
import urllib.request

import pytest

from support.netguard import NetworkBlocked


def _blocked(exc: BaseException) -> bool:
    if isinstance(exc, NetworkBlocked):
        return True
    return isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, NetworkBlocked)


def test_netguard_positive_control(no_network):
    with pytest.raises(OSError) as by_url:  # URLError and NetworkBlocked are both OSError
        urllib.request.urlopen("http://127.0.0.1:9", timeout=1)
    assert _blocked(by_url.value), repr(by_url.value)

    with pytest.raises(OSError) as by_name:
        socket.getaddrinfo("example.com", 80)
    assert _blocked(by_name.value), repr(by_name.value)

    assert len(no_network.attempts) == 2
    assert ("getaddrinfo", ("example.com", 80)) in no_network.attempts


def test_netguard_blocks_raw_connect_and_connect_ex(no_network):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkBlocked):
            sock.connect(("127.0.0.1", 9))
        with pytest.raises(NetworkBlocked):
            sock.connect_ex(("127.0.0.1", 9))

    assert no_network.attempts == [
        ("connect", ("127.0.0.1", 9)),
        ("connect_ex", ("127.0.0.1", 9)),
    ]


# --- F4: LoopbackGuard (matrix S7, S8) ---------------------------------------------


def test_loopback_guard_allows_loopback(monkeypatch):
    import http.client

    from support.fake_openai_server import FakeOpenAIServer, Reply
    from support.netguard import LoopbackGuard

    with FakeOpenAIServer() as fake:
        guard = LoopbackGuard().install(monkeypatch)
        fake.script(Reply(200, body=b"ok"))
        conn = http.client.HTTPConnection("127.0.0.1", fake.port, timeout=5)
        try:
            conn.request("GET", "/x")
            assert conn.getresponse().read() == b"ok"
        finally:
            conn.close()
    assert ("connect", ("127.0.0.1", fake.port)) in guard.allowed
    assert guard.blocked == []


def test_loopback_guard_blocks_others(monkeypatch):
    from support.netguard import LoopbackGuard

    guard = LoopbackGuard().install(monkeypatch)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    attempts = [
        lambda: socket.getaddrinfo("example.com", 80),
        lambda: socket.getaddrinfo("localhost", 80),
        lambda: socket.getaddrinfo("::1", 80),
        lambda: tcp.connect(("10.255.255.1", 80)),
        lambda: tcp.connect_ex(("127.0.0.2", 80)),
        lambda: socket.gethostbyname("example.com"),
        lambda: socket.gethostbyname_ex("example.com"),
        lambda: socket.gethostbyaddr("8.8.8.8"),
        lambda: udp.sendto(b"x", ("10.255.255.1", 53)),
    ]
    try:
        for attempt in attempts:
            with pytest.raises(NetworkBlocked):
                attempt()
    finally:
        tcp.close()
        udp.close()
    assert [kind for kind, _ in guard.blocked] == [
        "getaddrinfo",
        "getaddrinfo",
        "getaddrinfo",
        "connect",
        "connect_ex",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "sendto",
    ]
    assert guard.allowed == []
