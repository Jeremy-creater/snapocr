"""M3 WI-10: the model list for the settings window (PRD F11-7; M3 plan D12, D13).

Pinned here:
- ``parse_models_response(status, body, ctx=)``: 200 with ``{"data": [{"id": str}, ...]}``
  gives the ids, unique and sorted; entries that are not objects or have no
  string id are skipped. Any other status is ``HTTP_STATUS`` (with the
  status); a body that is not a JSON object with a ``data`` list is
  ``BAD_RESPONSE``. The body never appears in the error.
- ``get_json(endpoint, path, timeout_s, ctx=)`` sends a GET with no body over
  the same loopback transport as ``post_json`` and maps failures the same way.
- ``list_models(config)`` asks ``GET {base_url}/v1/models`` with a 3 s timeout:
  Windows reports a refused loopback connection only after about 2 s (plan D12).
"""

import json
import socket
import time

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.config import TranslatorConfig
from snapocr.translators.errors import ErrorContext, TranslationError, TranslationErrorKind
from snapocr.translators.http_transport import get_json
from snapocr.translators.openai_compat import MODEL_LIST_TIMEOUT_S, list_models
from snapocr.translators.protocol import MODELS_PATH, parse_models_response
from support.fake_openai_server import Reply
from support.leakcheck import no_leak

pytestmark = pytest.mark.usefixtures("loopback_guard")

K = TranslationErrorKind
CTX = ErrorContext("http://127.0.0.1:11434", "hy-mt2:7b")
M = "ZQXJ0f1e2d3c4b5a"


def models_body(*ids, extra=()):
    return json.dumps({"object": "list", "data": [{"id": i, "object": "model"} for i in ids] + list(extra)}).encode()


# --- parse ------------------------------------------------------------------------


def test_parse_gives_sorted_unique_ids():
    body = models_body("qwen3:8b", "hy-mt2:7b", "qwen3:8b", "bge-m3:latest")
    assert parse_models_response(200, body, ctx=CTX) == ("bge-m3:latest", "hy-mt2:7b", "qwen3:8b")


def test_parse_skips_entries_without_a_string_id():
    body = models_body("hy-mt2:7b", extra=[{"id": 3}, {"name": "x"}, "qwen3:8b", None, {"id": ""}])
    assert parse_models_response(200, body, ctx=CTX) == ("hy-mt2:7b",)


def test_parse_empty_list():
    assert parse_models_response(200, models_body(), ctx=CTX) == ()


@pytest.mark.parametrize("body", [
    b"not json " + M.encode(),
    b"\xff\xfe" + M.encode(),
    json.dumps([M]).encode(),
    json.dumps({"models": [{"name": M}]}).encode(),
    json.dumps({"data": M}).encode(),
], ids=["not-json", "not-utf8", "array", "no-data", "data-not-list"])
def test_parse_bad_shape_is_bad_response(body):
    with pytest.raises(TranslationError) as info:
        parse_models_response(200, body, ctx=CTX)
    assert info.value.kind is K.BAD_RESPONSE
    assert CTX.base_url in str(info.value)
    no_leak(info.value, M)


@pytest.mark.parametrize("status", [404, 500, 301])
def test_parse_other_status_is_http_status(status):
    with pytest.raises(TranslationError) as info:
        parse_models_response(status, models_body(M), ctx=CTX)
    assert info.value.kind is K.HTTP_STATUS
    assert info.value.status == status
    no_leak(info.value, M)


@given(st.lists(st.text(min_size=1, max_size=30), max_size=12))
def test_parse_property(ids):
    assert parse_models_response(200, models_body(*ids), ctx=CTX) == tuple(sorted(set(ids)))


# --- transport ----------------------------------------------------------------------


def test_get_json_sends_a_bodiless_get(fake_server, loopback_guard):
    fake = fake_server
    fake.reset()
    fake.script(Reply(200, {}, b'{"data": []}'))
    assert get_json(fake.endpoint, MODELS_PATH, 2.0, ctx=CTX) == (200, b'{"data": []}')
    [rec] = fake.requests
    assert (rec.method, rec.path, rec.body) == ("GET", "/v1/models", b"")
    assert rec.headers["accept"] == "application/json"
    assert ("connect", ("127.0.0.1", fake.port)) in loopback_guard.allowed


def test_get_json_timeout(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(Reply(200, {}, b"{}", delay_s=1.0))
    with pytest.raises(TranslationError) as info:
        get_json(fake.endpoint, MODELS_PATH, 0.2, ctx=CTX)
    assert info.value.kind is K.TIMEOUT


# --- list_models -------------------------------------------------------------------


def test_list_models_end_to_end(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(Reply(200, {}, models_body("qwen3:8b", "hy-mt2:7b")))
    assert list_models(TranslatorConfig(base_url=fake.base_url)) == ("hy-mt2:7b", "qwen3:8b")
    assert [(r.method, r.path) for r in fake.requests] == [("GET", "/v1/models")]


def test_list_models_error_names_the_service(fake_server):
    fake = fake_server
    fake.reset()
    fake.script(Reply(404, {}, b"404 page not found"))
    config = TranslatorConfig(base_url=fake.base_url, model="qwen3:8b")
    with pytest.raises(TranslationError) as info:
        list_models(config)
    assert info.value.kind is K.HTTP_STATUS
    assert fake.base_url in str(info.value) and "qwen3:8b" in str(info.value)


def test_list_models_timeout_is_three_seconds(fake_server):
    assert MODEL_LIST_TIMEOUT_S == 3.0
    fake = fake_server
    fake.reset()
    fake.script(Reply(200, {}, models_body("a"), delay_s=1.0))  # inside 3 s, even with timeout_s=0.1 configured
    assert list_models(TranslatorConfig(base_url=fake.base_url, timeout_s=0.1)) == ("a",)


def test_list_models_unreachable():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    start = time.monotonic()
    with pytest.raises(TranslationError) as info:
        list_models(TranslatorConfig(base_url=f"http://127.0.0.1:{port}"))
    assert info.value.kind is K.UNREACHABLE
    assert time.monotonic() - start < MODEL_LIST_TIMEOUT_S
