from __future__ import annotations

import json
import mimetypes
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
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

    def stats(self) -> dict[str, Any]:
        return self._request("GET", "/v1/stats")

    def initialize(self, model: str, lm_model: str | None) -> dict[str, Any]:
        data = json.dumps({"model": model, "init_llm": bool(lm_model), "lm_model_path": lm_model}).encode()
        return self._request("POST", "/v1/init", data)

    def improve_inputs(
        self,
        prompt: str,
        lyrics: str,
        *,
        duration: float | None = None,
        bpm: int | None = None,
        key_scale: str = "",
        time_signature: str = "",
    ) -> dict[str, Any]:
        parameters = {
            key: value
            for key, value in {
                "duration": duration,
                "bpm": bpm,
                "key_scale": key_scale,
                "time_signature": time_signature,
            }.items()
            if value not in (None, "")
        }
        return self.call(
            "POST",
            "/format_input",
            {"prompt": prompt, "lyrics": lyrics, "temperature": 0.85, "param_obj": parameters},
        )

    def create_sample(self, query: str, instrumental: bool = False) -> dict[str, Any]:
        return self.call(
            "POST",
            "/v1/create_sample",
            {"query": query, "instrumental": instrumental, "vocal_language": "unknown", "temperature": 0.85},
        )

    def random_sample(self, simple: bool = True) -> dict[str, Any]:
        return self.call("POST", "/create_random_sample", {"sample_type": "simple_mode" if simple else "custom_mode"})

    @staticmethod
    def audio_suffix(source: str) -> str:
        parsed = urllib.parse.urlsplit(source)
        filename = urllib.parse.parse_qs(parsed.query).get("path", [parsed.path])[0]
        return Path(filename).suffix or ".wav"

    def download_audio(self, source: str, target: Path) -> Path:
        url = urllib.parse.urljoin(f"{self.base_url}/", source)
        if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(self.base_url).netloc:
            raise AceApiError("ACE-Step returned an invalid audio URL")
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        temporary = target.with_suffix(f"{target.suffix}.part")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            temporary.replace(target)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            temporary.unlink(missing_ok=True)
            raise AceApiError(f"Could not save generated audio: {exc}") from exc
        return target

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

    def task_status(self, task_id: str) -> dict[str, Any]:
        result = self._request("POST", "/query_result", json.dumps({"task_id_list": [task_id]}).encode())
        item = result[0] if isinstance(result, list) else result
        detail = item.get("result") or []
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except ValueError:
                detail = []
        first = detail[0] if isinstance(detail, list) and detail else detail if isinstance(detail, dict) else {}
        return {
            "status": int(item.get("status", 0)),
            "progress": float(first.get("progress", 1 if int(item.get("status", 0)) == 1 else 0)),
            "stage": first.get("stage") or item.get("progress_text") or "Queued",
            "progress_text": item.get("progress_text") or "",
            "result": detail,
            "error": first.get("error") or item.get("error"),
        }

    def wait(
        self,
        task_id: str,
        poll_interval: float = 1,
        timeout: float = 3600,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> GenerationResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            update = self.task_status(task_id)
            if progress_callback:
                progress_callback(update)
            status = update["status"]
            if status == 1:
                value = update["result"]
                if isinstance(value, list):
                    first = value[0] if value else {}
                    audio_paths = [entry.get("file") for entry in value if entry.get("file")]
                else:
                    first = value
                    audio_paths = value.get("raw_audio_paths") or value.get("audio_paths") or []
                metadata = first.get("metas") or {}
                return GenerationResult(
                    task_id=task_id,
                    title=metadata.get("title") or "Untitled generation",
                    audio_paths=audio_paths,
                    prompt=first.get("prompt", ""),
                    lyrics=first.get("lyrics", ""),
                    metadata=metadata,
                    seed=first.get("seed_value", ""),
                )
            if status == 2:
                raise AceApiError(update["error"] or "Generation failed")
            time.sleep(poll_interval)
        raise AceApiError("Generation timed out")

    def waveform(self, path: str, bins: int = 600) -> dict[str, Any]:
        query = urllib.parse.urlencode({"path": path, "bins": bins})
        return self._request("GET", f"/studio/v1/waveform?{query}")
