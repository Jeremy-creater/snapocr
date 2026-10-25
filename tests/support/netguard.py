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
