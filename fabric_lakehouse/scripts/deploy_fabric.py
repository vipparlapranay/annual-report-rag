import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from uuid import UUID

API_ROOT = "https://api.fabric.microsoft.com/v1"


def request_json(url: str, token: str, method: str = "GET", payload: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, response.headers, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Fabric API returned HTTP {error.code}: {detail}"
        ) from error


def deploy(pipeline_id: str, source_stage_id: str, target_stage_id: str, note: str) -> None:
    token = os.environ.get("FABRIC_ACCESS_TOKEN")
    if not token:
        raise ValueError("Set FABRIC_ACCESS_TOKEN using a secure pipeline identity.")
    if source_stage_id == target_stage_id:
        raise ValueError("Source and target Fabric stage IDs must be different.")
    for label, value in (
        ("pipeline", pipeline_id),
        ("source stage", source_stage_id),
        ("target stage", target_stage_id),
    ):
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError(f"The Fabric {label} ID must be a UUID.") from error

    url = f"{API_ROOT}/deploymentPipelines/{pipeline_id}/deploy"
    status, headers, body = request_json(
        url,
        token,
        method="POST",
        payload={
            "sourceStageId": source_stage_id,
            "targetStageId": target_stage_id,
            "note": note,
        },
    )
    print(json.dumps({"http_status": status, "response": body}, indent=2))
    operation_url = headers.get("Location")
    if not operation_url:
        return
    parsed = urlparse(operation_url)
    if parsed.scheme != "https" or parsed.hostname != "api.fabric.microsoft.com":
        raise RuntimeError("Fabric returned an unexpected operation URL.")

    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        delay = int(headers.get("Retry-After", "5"))
        time.sleep(max(1, min(delay, 30, int(deadline - time.monotonic()))))
        status, headers, body = request_json(operation_url, token)
        operation_status = str(body.get("status", "")).lower()
        print(json.dumps(body, indent=2))
        if operation_status in {"succeeded", "completed"}:
            return
        if operation_status in {"failed", "cancelled", "canceled"}:
            raise RuntimeError(f"Fabric deployment operation ended: {operation_status}")
    raise TimeoutError("Fabric deployment did not finish within five minutes.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote items between Fabric stages.")
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--source-stage-id", required=True)
    parser.add_argument("--target-stage-id", required=True)
    parser.add_argument("--note", default="Automated Azure DevOps deployment")
    args = parser.parse_args()
    try:
        deploy(
            args.pipeline_id,
            args.source_stage_id,
            args.target_stage_id,
            args.note,
        )
    except (RuntimeError, ValueError, TimeoutError) as error:
        print(f"Fabric deployment failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
