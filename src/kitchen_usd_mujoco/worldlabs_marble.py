from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional


DEFAULT_BASE_URL = "https://api.worldlabs.ai"


class WorldLabsError(RuntimeError):
    pass


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    done: bool
    error: Optional[dict[str, Any]]
    metadata: Optional[dict[str, Any]]
    response: Optional[dict[str, Any]]
    raw: dict[str, Any]

    @property
    def world_id(self) -> Optional[str]:
        md = self.metadata or {}
        world_id = md.get("world_id")
        if isinstance(world_id, str) and world_id:
            return world_id
        return None


def _guess_mime_type(ext: str) -> str:
    e = ext.lower().lstrip(".")
    if e in ("jpg", "jpeg"):
        return "image/jpeg"
    if e == "png":
        return "image/png"
    if e == "webp":
        return "image/webp"
    if e == "mp4":
        return "video/mp4"
    if e == "mov":
        return "video/quicktime"
    if e == "mkv":
        return "video/x-matroska"
    return "application/octet-stream"


def _http_json(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Optional[dict[str, Any]] = None,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    data: Optional[bytes] = None
    req_headers = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url=url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err_body = None
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        msg = f"HTTP {e.code} calling {method} {url}"
        if err_body:
            msg += f": {err_body}"
        raise WorldLabsError(msg) from e
    except urllib.error.URLError as e:
        raise WorldLabsError(f"Network error calling {method} {url}: {e}") from e


def prepare_upload(
    *,
    api_key: str,
    file_name: str,
    kind: str,
    extension: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"file_name": file_name, "kind": kind}
    if extension is not None:
        payload["extension"] = extension
    if metadata is not None:
        payload["metadata"] = metadata

    return _http_json(
        method="POST",
        url=f"{base_url}/marble/v1/media-assets:prepare_upload",
        headers={"WLT-Api-Key": api_key},
        body=payload,
        timeout_s=timeout_s,
    )


def upload_bytes(
    *,
    upload_url: str,
    data: bytes,
    required_headers: Optional[Mapping[str, str]] = None,
    content_type: Optional[str] = None,
    timeout_s: float = 300.0,
) -> None:
    headers: MutableMapping[str, str] = {}
    if required_headers:
        headers.update({str(k): str(v) for k, v in required_headers.items()})
    if content_type and "Content-Type" not in headers:
        headers["Content-Type"] = content_type

    req = urllib.request.Request(url=upload_url, data=data, headers=dict(headers), method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            _ = resp.read()
    except urllib.error.HTTPError as e:
        err_body = None
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        msg = f"HTTP {e.code} uploading to signed URL"
        if err_body:
            msg += f": {err_body}"
        raise WorldLabsError(msg) from e
    except urllib.error.URLError as e:
        raise WorldLabsError(f"Network error uploading to signed URL: {e}") from e


def worlds_generate(
    *,
    api_key: str,
    world_prompt: dict[str, Any],
    display_name: Optional[str] = None,
    model: str = "Marble 0.1-plus",
    tags: Optional[list[str]] = None,
    seed: Optional[int] = None,
    public: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"world_prompt": world_prompt, "model": model, "permission": {"public": public}}
    if display_name is not None:
        payload["display_name"] = display_name
    if tags is not None:
        payload["tags"] = tags
    if seed is not None:
        payload["seed"] = seed

    return _http_json(
        method="POST",
        url=f"{base_url}/marble/v1/worlds:generate",
        headers={"WLT-Api-Key": api_key, "Content-Type": "application/json"},
        body=payload,
        timeout_s=timeout_s,
    )


def operations_get(
    *,
    api_key: str,
    operation_id: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    return _http_json(
        method="GET",
        url=f"{base_url}/marble/v1/operations/{operation_id}",
        headers={"WLT-Api-Key": api_key},
        body=None,
        timeout_s=timeout_s,
    )


def worlds_get(
    *,
    api_key: str,
    world_id: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    return _http_json(
        method="GET",
        url=f"{base_url}/marble/v1/worlds/{world_id}",
        headers={"WLT-Api-Key": api_key},
        body=None,
        timeout_s=timeout_s,
    )


def wait_for_operation(
    *,
    api_key: str,
    operation_id: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = 900.0,
    poll_s: float = 5.0,
    max_poll_s: float = 30.0,
) -> OperationResult:
    start = time.time()
    sleep_s = max(1.0, float(poll_s))

    while True:
        data = operations_get(api_key=api_key, operation_id=operation_id, base_url=base_url)
        done = bool(data.get("done", False))
        err = data.get("error")
        md = data.get("metadata")
        resp = data.get("response")
        result = OperationResult(
            operation_id=str(data.get("operation_id", operation_id)),
            done=done,
            error=err if isinstance(err, dict) else None,
            metadata=md if isinstance(md, dict) else None,
            response=resp if isinstance(resp, dict) else None,
            raw=data,
        )
        if done:
            if result.error:
                raise WorldLabsError(f"Operation failed: {json.dumps(result.error)}")
            return result

        if (time.time() - start) > timeout_s:
            raise WorldLabsError(f"Timed out waiting for operation {operation_id} after {timeout_s:.1f}s")

        time.sleep(sleep_s)
        sleep_s = min(max_poll_s, sleep_s * 1.2)


def encode_file_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


