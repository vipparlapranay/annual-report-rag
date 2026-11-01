import pytest

from scripts import deploy_fabric

_PIPELINE = "0c614a75-1c49-43d9-9951-46ae1e15bd2a"
_SOURCE = "c1beed66-e981-4a6b-994e-80f30b6601af"
_TARGET = "2847f305-9067-48d9-b2d0-5679c36de80e"


def test_deployment_requires_access_token(monkeypatch) -> None:
    monkeypatch.delenv("FABRIC_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="FABRIC_ACCESS_TOKEN"):
        deploy_fabric.deploy(_PIPELINE, _SOURCE, _TARGET, "unit test")


def test_deployment_submits_stage_ids_without_exposing_token(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("FABRIC_ACCESS_TOKEN", "test-token")
    requests = []

    def fake_request(url, token, method="GET", payload=None):
        requests.append((url, token, method, payload))
        return 200, {}, {"status": "Succeeded"}

    monkeypatch.setattr(deploy_fabric, "request_json", fake_request)
    deploy_fabric.deploy(_PIPELINE, _SOURCE, _TARGET, "unit test")

    assert requests == [
        (
            f"{deploy_fabric.API_ROOT}/deploymentPipelines/{_PIPELINE}/deploy",
            "test-token",
            "POST",
            {
                "sourceStageId": _SOURCE,
                "targetStageId": _TARGET,
                "note": "unit test",
            },
        )
    ]
    assert "test-token" not in capsys.readouterr().out


def test_deployment_rejects_malformed_stage_id(monkeypatch) -> None:
    monkeypatch.setenv("FABRIC_ACCESS_TOKEN", "test-token")
    with pytest.raises(ValueError, match="source stage ID"):
        deploy_fabric.deploy(_PIPELINE, "not-a-uuid", _TARGET, "unit test")
