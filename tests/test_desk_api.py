"""Desk FastAPI smoke — studio get/compile，不打真网。"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from quant_shell.desk.app import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["framework"] == "quant-shell"


def test_studio_get_empty(client: TestClient) -> None:
    r = client.get("/api/v1/studio/model")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "model" in body or "catalog" in body


def test_studio_compile_rules(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # 强制走规则编译，避免依赖 DeepSeek
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = client.post(
        "/api/v1/studio/compile",
        json={"idea": "用动量和低波买沪深300 ETF，回撤超过8%减仓"},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "model" in body or body.get("compiler") in ("rules", "llm", None)