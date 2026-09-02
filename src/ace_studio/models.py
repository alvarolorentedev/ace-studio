from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeProfile(StrEnum):
    MACOS_MLX = "macos-mlx"
    WINDOWS_CUDA = "windows-cuda"
    WINDOWS_ROCM = "windows-rocm"
    WINDOWS_XPU = "windows-xpu"
    WINDOWS_CPU = "windows-cpu"
    LINUX_CUDA = "linux-cuda"
    LINUX_ROCM = "linux-rocm"
    LINUX_XPU = "linux-xpu"
    LINUX_CPU = "linux-cpu"


class RuntimeState(StrEnum):
    MISSING = "missing"
    INSTALLING = "installing"
    READY = "ready"
    STARTING = "starting"
    ONLINE = "online"
    FAILED = "failed"


@dataclass(slots=True)
class HardwareReport:
    os_name: str
    architecture: str
    processor: str
    memory_gb: float | None
    gpu_name: str
    profile: RuntimeProfile
    driver_ready: bool
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        memory = f" · {self.memory_gb:.0f} GB memory" if self.memory_gb else ""
        return f"{self.gpu_name}{memory}"


@dataclass(slots=True)
class RuntimeManifest:
    commit: str
    profile: RuntimeProfile
    python_version: str
    source_url: str
    installed_at: str
    state: RuntimeState = RuntimeState.READY

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["profile"] = self.profile.value
        result["state"] = self.state.value
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeManifest":
        return cls(
            commit=value["commit"],
            profile=RuntimeProfile(value["profile"]),
            python_version=value["python_version"],
            source_url=value["source_url"],
            installed_at=value["installed_at"],
            state=RuntimeState(value.get("state", RuntimeState.READY)),
        )


@dataclass(slots=True)
class GenerationRequest:
    prompt: str
    lyrics: str = ""
    task_type: str = "text2music"
    duration: float = 120
    bpm: int | None = None
    key_scale: str = ""
    time_signature: str = ""
    instrumental: bool = False
    model: str | None = None
    thinking: bool = True
    batch_size: int = 2
    seed: int | None = None
    source_audio: str | None = None
    reference_audio: str | None = None
    repaint_start: float = 0
    repaint_end: float | None = None
    cover_strength: float = 1
    advanced: dict[str, Any] = field(default_factory=dict)

    def fields(self) -> dict[str, str]:
        values: dict[str, Any] = {
            "prompt": self.prompt,
            "lyrics": self.lyrics,
            "task_type": self.task_type,
            "audio_duration": self.duration,
            "vocal_language": "unknown" if self.instrumental else "en",
            "thinking": self.thinking,
            "batch_size": self.batch_size,
            "use_random_seed": self.seed is None,
            "seed": -1 if self.seed is None else self.seed,
            "audio_cover_strength": self.cover_strength,
            "repainting_start": self.repaint_start,
        }
        if self.bpm:
            values["bpm"] = self.bpm
        if self.key_scale:
            values["key_scale"] = self.key_scale
        if self.time_signature:
            values["time_signature"] = self.time_signature
        if self.model:
            values["model"] = self.model
        if self.repaint_end is not None:
            values["repainting_end"] = self.repaint_end
        values.update(self.advanced)
        return {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in values.items()}


@dataclass(slots=True)
class GenerationResult:
    task_id: str
    title: str
    audio_paths: list[str]
    prompt: str
    lyrics: str
    metadata: dict[str, Any]
    seed: str = ""

