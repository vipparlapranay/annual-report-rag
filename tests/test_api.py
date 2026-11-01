from uuid import uuid4

from fastapi.testclient import TestClient

from app import api as api_module
from app.config import Settings
from app.vector_store import ReportStore


def _use_ephemeral_store(monkeypatch) -> None:
    config = Settings(collection_name=f"test-{uuid4().hex}")
    monkeypatch.setattr(
        api_module,
        "ReportStore",
        lambda: ReportStore(config, ephemeral=True),
    )


def test_health_ask_and_metrics(monkeypatch) -> None:
    _use_ephemeral_store(monkeypatch)
    with TestClient(api_module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        upload = client.post(
            "/documents",
            files={
                "file": (
                    "test.md",
                    b"Revenue for fiscal year 2024 was $2.4 billion.",
                    "text/markdown",
                )
            },
        )
        assert upload.status_code == 201
        assert upload.json()["chunks_indexed"] == 1

        answer = client.post(
            "/ask", json={"question": "What was revenue in fiscal year 2024?"}
        )
        assert answer.status_code == 200
        assert "$2.4 billion" in answer.json()["answer"]
        assert answer.json()["citations"][0]["document"] == "test.md"
        assert answer.json()["abstained"] is False
        assert answer.json()["latency_ms"] >= 0

        unsupported = client.post(
            "/ask", json={"question": "What is the company's climate target?"}
        )
        assert unsupported.status_code == 200
        assert unsupported.json()["abstained"] is True
        assert unsupported.json()["citations"] == []

        metrics = client.get("/metrics").json()
        assert metrics["requests"] == 2
        assert metrics["input_tokens"] > 0


def test_unsupported_format_returns_client_error(monkeypatch) -> None:
    _use_ephemeral_store(monkeypatch)
    with TestClient(api_module.app) as client:
        response = client.post(
            "/documents",
            files={"file": ("report.csv", b"nope", "text/csv")},
        )
        assert response.status_code == 400
