"""Network guard for tests: blocks and records every connection attempt.

Replaces ``socket.socket.connect``, ``socket.socket.connect_ex`` and
``socket.getaddrinfo``. It only observes and refuses; it never serves data.
Its own effectiveness is proven by a positive-control test (WI-7).
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field


class NetworkBlocked(OSError):
    """Raised instead of opening a connection or resolving a name."""


@dataclass
class NetGuard:
    attempts: list[tuple[str, object]] = field(default_factory=list)

    def _block(self, kind: str, target: object) -> NetworkBlocked:
        self.attempts.append((kind, target))
        return NetworkBlocked(f"network access blocked in tests: {kind} {target!r}")

    def install(self, monkeypatch) -> NetGuard:
        guard = self

        def connect(sock, address):
            raise guard._block("connect", address)

        def connect_ex(sock, address):
            raise guard._block("connect_ex", address)

        def getaddrinfo(host, port, *args, **kwargs):
            raise guard._block("getaddrinfo", (host, port))

        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        return self


@dataclass
class LoopbackGuard:
    """Allows exactly host ``127.0.0.1`` and blocks and records everything else (F4, Q18).

    Unlike ``NetGuard`` it delegates allowed calls to the real socket functions,
    so tests can talk to the in-process fake service. ``localhost`` and ``::1``
    are blocked too: the translator must only ever use the literal address.
    """

    allowed: list[tuple[str, object]] = field(default_factory=list)
    blocked: list[tuple[str, object]] = field(default_factory=list)

    def _check(self, kind: str, host: object, target: object) -> None:
        if host == "127.0.0.1":
            self.allowed.append((kind, target))
            return
        self.blocked.append((kind, target))
        raise NetworkBlocked(f"non-loopback network access blocked in tests: {kind} {target!r}")

    def install(self, monkeypatch) -> LoopbackGuard:
        guard = self
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
        real_sendto = socket.socket.sendto
        real_getaddrinfo = socket.getaddrinfo
        real_gethostbyname = socket.gethostbyname
        real_gethostbyname_ex = socket.gethostbyname_ex
        real_gethostbyaddr = socket.gethostbyaddr

        def _host(address):
            return address[0] if isinstance(address, tuple) and address else address

        def connect(sock, address):
            guard._check("connect", _host(address), address)
            return real_connect(sock, address)

        def connect_ex(sock, address):
            guard._check("connect_ex", _host(address), address)
            return real_connect_ex(sock, address)

        def sendto(sock, data, *args):
            address = args[-1] if args else None
            guard._check("sendto", _host(address), address)
            return real_sendto(sock, data, *args)

        def getaddrinfo(host, port, *args, **kwargs):
            guard._check("getaddrinfo", host, (host, port))
            return real_getaddrinfo(host, port, *args, **kwargs)

        def gethostbyname(host):
            guard._check("gethostbyname", host, host)
            return real_gethostbyname(host)

        def gethostbyname_ex(host):
            guard._check("gethostbyname_ex", host, host)
            return real_gethostbyname_ex(host)

        def gethostbyaddr(host):
            guard._check("gethostbyaddr", host, host)
            return real_gethostbyaddr(host)

        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
        monkeypatch.setattr(socket.socket, "sendto", sendto)
        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
        monkeypatch.setattr(socket, "gethostbyname_ex", gethostbyname_ex)
        monkeypatch.setattr(socket, "gethostbyaddr", gethostbyaddr)
        return self
