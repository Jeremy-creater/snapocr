"""WI-8 unit-lane support: require_ollama fails loudly, never skips (matrix U1-U3, U5)."""

import json
import socket

import pytest

from support.fake_openai_server import Reply
from support.ollama_require import require_ollama

pytestmark = pytest.mark.usefixtures("loopback_guard")


def _models(*ids):
    return json.dumps({"object": "list", "data": [{"id": i} for i in ids]}).encode()


def _fails(base_url, **kw):
    with pytest.raises(pytest.fail.Exception) as info:
        require_ollama(base_url, **kw)
    assert not isinstance(info.value, pytest.skip.Exception)
    return str(info.value)


def test_require_passes_when_model_listed(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(Reply(body=_models("hy-mt2:7b", "qwen:7b")))
    require_ollama(fake.base_url)
    [rec] = fake.requests
    assert (rec.method, rec.path) == ("GET", "/v1/models")


@pytest.mark.parametrize("ids", [("qwen:7b",), ("hy-mt2:7b-q4",)])
def test_require_fails_when_model_missing(fake_server, ids):
    fake = fake_server
    fake.reset()
    fake.script(Reply(body=_models(*ids)))
    assert "ollama create hy-mt2:7b -f docs/hy-mt2-7b.Modelfile" in _fails(fake.base_url)


@pytest.mark.parametrize(
    "reply",
    [Reply(500, body=b"boom"), Reply(body=b"not json"), Reply(body=b'{"data": 5}'), Reply(body=b"[1]")],
    ids=["500", "not-json", "data-not-list", "json-array"],
)
def test_require_fails_on_bad_service(fake_server, reply):
    fake = fake_server
    fake.reset()
    fake.script(reply)
    assert fake.base_url in _fails(fake.base_url)


def test_require_fails_when_unreachable():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    message = _fails(base_url)
    assert "ollama serve" in message
    assert base_url in message
