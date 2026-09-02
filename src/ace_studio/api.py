from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .models import GenerationRequest, GenerationResult


class AceApiError(RuntimeError):
    pass


class AceClient:
    def __init__(self, port: int, token: str, timeout: float = 30) -> None:
        self.base_url = f"http://127.0.0.1:{port}"
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, data: bytes | None = None, content_type: str = "application/json") -> Any:
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise AceApiError(str(exc)) from exc
        if isinstance(payload, dict) and payload.get("code", 200) != 200:
            raise AceApiError(payload.get("error") or "ACE-Step request failed")
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """Call an authenticated ACE-Step endpoint not needing multipart data."""
        data = json.dumps(payload).encode() if payload is not None else None
        return self._request(method, path, data)

    def models(self) -> dict[str, Any]:
        return self._request("GET", "/v1/models")

    def initialize(self, model: str, lm_model: str | None) -> dict[str, Any]:
        data = json.dumps({"model": model, "init_llm": bool(lm_model), "lm_model_path": lm_model}).encode()
        return self._request("POST", "/v1/init", data)

    @staticmethod
    def _multipart(fields: dict[str, str], files: dict[str, str | None]) -> tuple[bytes, str]:
        boundary = f"ace-studio-{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        for name, filename in files.items():
            if not filename:
                continue
            path = Path(filename)
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            body.extend(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{path.name}\"\r\nContent-Type: {media_type}\r\n\r\n".encode()
            )
            body.extend(path.read_bytes())
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return bytes(body), f"multipart/form-data; boundary={boundary}"

    def generate(self, generation: GenerationRequest) -> str:
        body, content_type = self._multipart(
            generation.fields(),
            {"src_audio": generation.source_audio, "reference_audio": generation.reference_audio},
        )
        result = self._request("POST", "/release_task", body, content_type)
        return str(result["task_id"])

    def wait(self, task_id: str, poll_interval: float = 1, timeout: float = 3600) -> GenerationResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = json.dumps({"task_id_list": [task_id]}).encode()
            result = self._request("POST", "/query_result", data)
            item = result[0] if isinstance(result, list) else result
            status = int(item.get("status", 0))
            if status == 1:
                value = item.get("result") or item
                if isinstance(value, str):
                    value = json.loads(value)
                audio_paths = value.get("raw_audio_paths") or value.get("audio_paths") or []
                return GenerationResult(
                    task_id=task_id,
                    title=(value.get("metas") or {}).get("title") or "Untitled generation",
                    audio_paths=audio_paths,
                    prompt=value.get("prompt", ""),
                    lyrics=value.get("lyrics", ""),
                    metadata=value.get("metas") or {},
                    seed=value.get("seed_value", ""),
                )
            if status == 2:
                raise AceApiError(item.get("error") or "Generation failed")
            time.sleep(poll_interval)
        raise AceApiError("Generation timed out")

    def waveform(self, path: str, bins: int = 600) -> dict[str, Any]:
        query = urllib.parse.urlencode({"path": path, "bins": bins})
        return self._request("GET", f"/studio/v1/waveform?{query}")
