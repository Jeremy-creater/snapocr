"""Integration-lane precondition: a running Ollama with the model imported (WI-8).

FAILS (never skips) when the service is down, is not Ollama-shaped, or lacks the
model, so a red integration lane always says how to fix it.
"""

from __future__ import annotations

import http.client
import json

import pytest

from snapocr.translators.config import DEFAULT_BASE_URL, DEFAULT_MODEL, parse_base_url

IMPORT_HINT = "ollama create hy-mt2:7b -f docs/hy-mt2-7b.Modelfile"


def require_ollama(base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL) -> None:
    endpoint = parse_base_url(base_url)
    problem = None
    status, body = 0, b""
    conn = http.client.HTTPConnection(endpoint.host, endpoint.port, timeout=10)
    try:
        conn.request("GET", "/v1/models")
        response = conn.getresponse()
        status, body = response.status, response.read()
    except OSError as exc:
        problem = f"Ollama 未在 {endpoint.url} 运行（{type(exc).__name__}）；启动 Ollama 或 `ollama serve`"
    finally:
        conn.close()
    if problem:
        pytest.fail(problem, pytrace=False)

    try:
        data = json.loads(body).get("data") if status == 200 else None
    except (ValueError, AttributeError):
        data = None
    if not isinstance(data, list):
        pytest.fail(
            f"{endpoint.url}/v1/models 没有返回 Ollama 形状的模型列表（HTTP {status}）；检查 base_url",
            pytrace=False,
        )
    ids = {item.get("id") for item in data if isinstance(item, dict)}
    if model not in ids:
        pytest.fail(f"模型 {model} 未导入 {endpoint.url}；`{IMPORT_HINT}`", pytrace=False)
