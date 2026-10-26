"""In-process fake OpenAI-compatible service (stands in for the Ollama process).

A real ``ThreadingHTTPServer`` bound to ``127.0.0.1:0``: tests talk to it over
real loopback sockets, so timeouts, refused connections, truncated HTTP,
redirects and proxy settings behave as they do against Ollama. Replies are
scripted (FIFO); an unscripted request gets ``500 b"unscripted"`` so stray
requests surface as errors instead of passing silently.
"""

from __future__ import annotations

import json
import random
import select
import socket
import socketserver
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from snapocr.translators.config import Endpoint, parse_base_url
from support.tr_strategies import ok  # noqa: F401  (re-exported: OK(c) in the matrix)

__all__ = ["FakeOpenAIServer", "Recorded", "Reply", "echo", "echo_body", "ok"]


@dataclass(frozen=True)
class Recorded:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes
    client: tuple[str, int]


@dataclass
class Reply:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    delay_s: float = 0
    chunks: list[bytes] | None = None
    chunk_gap_s: float = 0
    stall_after_chunks_s: float = 0
    raw: bytes | None = None
    close_after_request: bool = False
    reset_after_request: bool = False


def echo(jitter_s: tuple[float, float] = (0, 0.03)) -> Callable[[Recorded], Reply]:
    """200 whose content is the request's ``messages[0].content``."""

    def reply(rec: Recorded) -> Reply:
        content = json.loads(rec.body)["messages"][0]["content"]
        return Reply(body=ok(content), delay_s=random.uniform(*jitter_s))

    return reply


def echo_body(jitter_s: tuple[float, float] = (0, 0.03)) -> Callable[[Recorded], Reply]:
    """200 whose body is the raw request body."""

    def reply(rec: Recorded) -> Reply:
        return Reply(body=rec.body, delay_s=random.uniform(*jitter_s))

    return reply


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        # Skip HTTPServer's socket.getfqdn(): a reverse lookup, slow on Windows.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class FakeOpenAIServer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[Reply] = []
        self._responder: Callable[[Recorded], Reply] | None = None
        self._requests: list[Recorded] = []
        self._open = 0
        self._stop = threading.Event()
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    # --- lifecycle -----------------------------------------------------------

    def __enter__(self) -> FakeOpenAIServer:
        self._server = _Server(("127.0.0.1", 0), _make_handler(self))
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def endpoint(self) -> Endpoint:
        return parse_base_url(self.base_url)

    # --- scripting -----------------------------------------------------------

    def script(self, *replies: Reply) -> None:
        with self._lock:
            self._queue.extend(replies)

    def respond_with(self, fn: Callable[[Recorded], Reply] | None) -> None:
        with self._lock:
            self._responder = fn

    def reset(self) -> None:
        with self._lock:
            self._queue.clear()
            self._responder = None
            self._requests.clear()

    @property
    def requests(self) -> list[Recorded]:
        with self._lock:
            return list(self._requests)

    @property
    def open_connections(self) -> int:
        with self._lock:
            return self._open

    def wait_closed(self, timeout_s: float = 1.0) -> int:
        """Poll until no connection is open (or the timeout passes); returns the count."""
        deadline = time.monotonic() + timeout_s
        while self.open_connections and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.open_connections

    # --- used by the handler --------------------------------------------------

    def _record(self, rec: Recorded) -> Reply:
        with self._lock:
            self._requests.append(rec)
            if self._responder is not None:
                fn = self._responder
            elif self._queue:
                return self._queue.pop(0)
            else:
                return Reply(500, body=b"unscripted")
        return fn(rec)

    def _connections(self, delta: int) -> None:
        with self._lock:
            self._open += delta

    def _stall(self, conn: socket.socket, seconds: float) -> bool:
        """Wait up to ``seconds``; False if the server is stopping or the client hung up."""
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            if self._stop.is_set():
                return False
            try:
                readable, _, _ = select.select([conn], [], [], min(left, 0.05))
                if readable and not conn.recv(1, socket.MSG_PEEK):
                    return False
            except OSError:
                return False
        return not self._stop.is_set()


def _make_handler(fake: FakeOpenAIServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            fake._connections(+1)
            super().setup()

        def finish(self) -> None:
            try:
                super().finish()
            except OSError:
                pass
            finally:
                fake._connections(-1)

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self._serve()

        def do_POST(self) -> None:
            self._serve()

        def _abort(self) -> None:
            self.close_connection = True

        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = Recorded(
                self.command,
                self.path,
                {k.lower(): v for k, v in self.headers.items()},
                body,
                self.client_address[:2],
            )
            reply = fake._record(rec)
            conn = self.connection
            if reply.delay_s and not fake._stall(conn, reply.delay_s):
                return self._abort()
            if reply.reset_after_request:
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                self.rfile.close()  # drops the last makefile() ref, so close() is real
                conn.close()
                return self._abort()
            if reply.close_after_request:
                return self._abort()
            if reply.raw is not None:
                self.wfile.write(reply.raw)
                if reply.stall_after_chunks_s:
                    fake._stall(conn, reply.stall_after_chunks_s)
                return self._abort()
            chunks = reply.chunks if reply.chunks is not None else [reply.body]
            self.send_response(reply.status)
            headers = dict(reply.headers)
            if not any(k.lower() == "content-length" for k in headers):
                headers["Content-Length"] = str(sum(len(c) for c in chunks))
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            for i, chunk in enumerate(chunks):
                if i and reply.chunk_gap_s and not fake._stall(conn, reply.chunk_gap_s):
                    return self._abort()
                self.wfile.write(chunk)
            if reply.stall_after_chunks_s:
                fake._stall(conn, reply.stall_after_chunks_s)
                return self._abort()

    return Handler
