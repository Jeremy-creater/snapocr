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
