from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

TRACK_NAMES = (
    "woodwinds",
    "brass",
    "fx",
    "synth",
    "strings",
    "percussion",
    "keyboard",
    "guitar",
    "bass",
    "drums",
    "backing_vocals",
    "vocals",
)
EDIT_TASKS = ("cover", "repaint", "lego", "extract", "complete")


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
    def from_dict(cls, value: dict[str, Any]) -> RuntimeManifest:
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
    instruction: str = ""
    track_name: str | None = None
    track_classes: list[str] = field(default_factory=list)
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
            "instruction": self.instruction,
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
        if self.track_name:
            values["track_name"] = self.track_name
        if self.track_classes:
            # The multipart parser accepts lists through its JSON parameter object.
            values["param_obj"] = json.dumps({"track_classes": self.track_classes})
        values.update(self.advanced)
        values["audio_format"] = "wav"
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


@dataclass(slots=True)
class EditRequest:
    source_audio: str
    task_type: str
    prompt: str = ""
    lyrics: str = ""
    repaint_start: float = 0
    repaint_end: float | None = None
    cover_strength: float = 1
    track_name: str | None = None
    track_classes: list[str] = field(default_factory=list)
    parent_id: str | None = None

    def validate(self, duration: float | None = None) -> None:
        source = Path(self.source_audio)
        if source.suffix.lower() != ".wav" or not source.is_file():
            raise ValueError("Choose an existing WAV source file.")
        if self.task_type not in EDIT_TASKS:
            raise ValueError("Unsupported edit type.")
        if self.task_type in {"cover", "repaint"} and not self.prompt.strip():
            raise ValueError("Describe the requested edit.")
        if not 0 <= self.cover_strength <= 1:
            raise ValueError("Cover strength must be between 0 and 1.")
        if self.task_type == "repaint":
            if self.repaint_end is None or self.repaint_start < 0 or self.repaint_end <= self.repaint_start:
                raise ValueError("Repaint end must be after its start.")
            if duration is not None and self.repaint_end > duration:
                raise ValueError("Repaint range exceeds the source duration.")
        if self.task_type in {"lego", "extract"} and self.track_name not in TRACK_NAMES:
            raise ValueError("Choose an instrument track.")
        if self.task_type == "complete" and (not self.track_classes or any(track not in TRACK_NAMES for track in self.track_classes)):
            raise ValueError("Choose at least one supported track to complete.")

    def generation_request(self, model: str) -> GenerationRequest:
        self.validate()
        return GenerationRequest(
            prompt=self.prompt.strip(),
            lyrics=self.lyrics.strip(),
            task_type=self.task_type,
            model=model,
            source_audio=self.source_audio,
            repaint_start=self.repaint_start,
            repaint_end=self.repaint_end,
            cover_strength=self.cover_strength,
            track_name=self.track_name,
            track_classes=self.track_classes,
        )


@dataclass(slots=True)
class DatasetSample:
    index: int
    filename: str
    audio_path: str
    duration: float = 0
    caption: str = ""
    genre: str = ""
    prompt_override: str | None = None
    lyrics: str = "[Instrumental]"
    bpm: int | None = None
    keyscale: str = ""
    timesignature: str = ""
    language: str = "unknown"
    is_instrumental: bool = True
    labeled: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DatasetSample:
        return cls(**{key: value[key] for key in cls.__dataclass_fields__ if key in value})

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["sample_idx"] = value.pop("index")
        value.pop("filename")
        value.pop("audio_path")
        value.pop("duration")
        value.pop("labeled")
        return value


@dataclass(slots=True)
class TrainingRequest:
    kind: str
    tensor_dir: str
    output_dir: str
    learning_rate: float | None = None
    epochs: int | None = None
    rank: int = 64
    alpha: int = 128
    dropout: float = 0.1
    batch_size: int = 1
    gradient_accumulation: int = 4
    save_every: int = 5
    training_shift: float = 3
    seed: int = 42
    gradient_checkpointing: bool = False
    lokr_factor: int = -1

    def payload(self) -> dict[str, Any]:
        if self.kind not in {"lora", "lokr"}:
            raise ValueError("Adapter type must be LoRA or LoKr.")
        if not Path(self.tensor_dir).is_dir():
            raise ValueError("Preprocessed tensor directory does not exist.")
        if self.learning_rate is not None and self.learning_rate <= 0:
            raise ValueError("Learning rate must be greater than zero.")
        if self.epochs is not None and self.epochs <= 0:
            raise ValueError("Epochs must be greater than zero.")
        if not 1 <= self.rank <= 256 or not 1 <= self.alpha <= 512:
            raise ValueError("Adapter dimension or alpha is outside the supported range.")
        if not 0 <= self.dropout <= 1 or min(self.batch_size, self.gradient_accumulation, self.save_every) < 1:
            raise ValueError("Training batch, accumulation, save, or dropout values are invalid.")
        defaults: dict[str, Any] = {
            "tensor_dir": self.tensor_dir,
            "learning_rate": self.learning_rate or (1e-4 if self.kind == "lora" else 0.03),
            "train_epochs": self.epochs or (10 if self.kind == "lora" else 500),
            "train_batch_size": self.batch_size,
            "gradient_accumulation": self.gradient_accumulation,
            "save_every_n_epochs": self.save_every,
            "training_shift": self.training_shift,
            "training_seed": self.seed,
            "gradient_checkpointing": self.gradient_checkpointing,
        }
        if self.kind == "lora":
            defaults.update(
                {"lora_rank": self.rank, "lora_alpha": self.alpha, "lora_dropout": self.dropout, "lora_output_dir": self.output_dir}
            )
        else:
            defaults.update(
                {
                    "lokr_linear_dim": self.rank,
                    "lokr_linear_alpha": self.alpha,
                    "lokr_factor": self.lokr_factor,
                    "output_dir": self.output_dir,
                }
            )
        return defaults


@dataclass(slots=True)
class Adapter:
    id: str
    name: str
    path: str
    kind: str
    scale: float = 1
    active: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
