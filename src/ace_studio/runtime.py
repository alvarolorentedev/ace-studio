from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .models import HardwareReport, RuntimeManifest, RuntimeProfile, RuntimeState
from .storage import Storage


ProgressCallback = Callable[[str, float | None], None]
GITHUB_COMMIT_API = "https://api.github.com/repos/ace-step/ACE-Step-1.5/commits/main"
GITHUB_ARCHIVE = "https://github.com/ace-step/ACE-Step-1.5/archive/{commit}.tar.gz"
DIT_MODELS = (
    "acestep-v15-turbo",
    "acestep-v15-base",
    "acestep-v15-sft",
    "acestep-v15-turbo-shift1",
    "acestep-v15-turbo-shift3",
    "acestep-v15-turbo-continuous",
    "acestep-v15-xl-base",
    "acestep-v15-xl-sft",
    "acestep-v15-xl-turbo",
)
LM_MODELS = ("acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-4B")


def _bundled_file(name: str) -> Path | None:
    """Find an executable staged into Flet assets for a packaged app."""
    roots = [Path(value) for value in [os.getenv("FLET_ASSETS_DIR")] if value]
    roots.extend([Path(__file__).resolve().parents[1] / "assets", Path(sys.executable).resolve().parent / "assets"])
    for root in roots:
        candidate = root / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def _memory_gb() -> float | None:
    try:
        if sys.platform == "darwin":
            value = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3)
            return int(value) / 1024**3
        if sys.platform == "win32":
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ]
            return int(subprocess.check_output(command, text=True, timeout=5).strip()) / 1024**3
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024 / 1024**3
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def _gpu_name() -> str:
    commands: list[list[str]] = []
    if sys.platform == "darwin":
        return platform.processor() or "Apple Silicon"
    if sys.platform == "win32":
        commands.append(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ', '",
            ]
        )
    else:
        commands.extend([["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], ["lspci"]])
    for command in commands:
        try:
            value = subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
            if value:
                return value.splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            continue
    return "CPU"


def detect_hardware() -> HardwareReport:
    os_name = platform.system()
    architecture = platform.machine().lower()
    processor = platform.processor() or architecture
    gpu = _gpu_name()
    gpu_lower = gpu.lower()
    notes: list[str] = []
    driver_ready = True

    if sys.platform == "darwin":
        profile = RuntimeProfile.MACOS_MLX
        driver_ready = architecture in {"arm64", "aarch64"}
        if not driver_ready:
            notes.append("ACE-Step's macOS acceleration requires Apple Silicon.")
    elif sys.platform == "win32":
        if "nvidia" in gpu_lower:
            profile = RuntimeProfile.WINDOWS_CUDA
        elif "amd" in gpu_lower or "radeon" in gpu_lower:
            profile = RuntimeProfile.WINDOWS_ROCM
        elif "intel" in gpu_lower and ("arc" in gpu_lower or "iris" in gpu_lower):
            profile = RuntimeProfile.WINDOWS_XPU
        else:
            profile = RuntimeProfile.WINDOWS_CPU
            notes.append("No supported GPU runtime was detected; CPU mode will be used.")
    else:
        if "nvidia" in gpu_lower:
            profile = RuntimeProfile.LINUX_CUDA
        elif "amd" in gpu_lower or "radeon" in gpu_lower:
            profile = RuntimeProfile.LINUX_ROCM
        elif "intel" in gpu_lower and ("arc" in gpu_lower or "graphics" in gpu_lower):
            profile = RuntimeProfile.LINUX_XPU
        else:
            profile = RuntimeProfile.LINUX_CPU
            notes.append("No supported GPU runtime was detected; CPU mode will be used.")

    return HardwareReport(
        os_name=os_name,
        architecture=architecture,
        processor=processor,
        memory_gb=_memory_gb(),
        gpu_name=gpu,
        profile=profile,
        driver_ready=driver_ready,
        notes=notes,
    )


def recommended_models(report: HardwareReport) -> tuple[str, str | None]:
    memory = report.memory_gb or 0
    if report.profile in {RuntimeProfile.WINDOWS_CPU, RuntimeProfile.LINUX_CPU} or memory <= 6:
        return "acestep-v15-turbo", None
    # Apple Silicon shares memory with macOS, the DiT, and the LM. Keep 16 GB
    # machines on the smaller LM to leave practical headroom during decoding.
    if report.profile == RuntimeProfile.MACOS_MLX and memory <= 16:
        return "acestep-v15-turbo", "acestep-5Hz-lm-0.6B"
    if memory < 16:
        return "acestep-v15-turbo", "acestep-5Hz-lm-0.6B"
    if memory < 24:
        return "acestep-v15-turbo", "acestep-5Hz-lm-1.7B"
    return "acestep-v15-xl-turbo", "acestep-5Hz-lm-1.7B"


class RuntimeManager:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.hardware = detect_hardware()
        self.state = RuntimeState.MISSING
        self.process: subprocess.Popen[str] | None = None
        self.port: int | None = None
        self.token: str | None = None
        self._lock = threading.Lock()
        if self.current_manifest():
            self.state = RuntimeState.READY

    @property
    def current_file(self) -> Path:
        return self.storage.runtime_dir / "current.json"

    def current_manifest(self) -> RuntimeManifest | None:
        try:
            return RuntimeManifest.from_dict(json.loads(self.current_file.read_text()))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @property
    def model_settings_file(self) -> Path:
        return self.storage.runtime_dir / "models.json"

    def selected_models(self) -> tuple[str, str | None]:
        recommended = recommended_models(self.hardware)
        try:
            saved = json.loads(self.model_settings_file.read_text())
            dit = saved["dit"]
            lm = saved.get("lm")
            if dit in DIT_MODELS and self.model_installed(dit) and lm in (*LM_MODELS, None) and (lm is None or self.model_installed(lm)):
                return dit, lm
        except (OSError, ValueError, KeyError, TypeError):
            pass
        dit = recommended[0] if self.model_installed(recommended[0]) else next((name for name in DIT_MODELS if self.model_installed(name)), recommended[0])
        lm = recommended[1] if recommended[1] and self.model_installed(recommended[1]) else next((name for name in LM_MODELS if self.model_installed(name)), None)
        return dit, lm

    def select_models(self, dit: str, lm: str | None) -> None:
        if dit not in DIT_MODELS or lm not in (*LM_MODELS, None):
            raise ValueError("Unsupported ACE-Step model selection")
        temporary = self.model_settings_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"dit": dit, "lm": lm}, indent=2))
        temporary.replace(self.model_settings_file)

    def model_installed(self, model: str) -> bool:
        return (self.storage.models_dir / model / "config.json").is_file()

    def download_model(self, model: str, progress: ProgressCallback = lambda _message, _value: None) -> None:
        if model not in (*DIT_MODELS, *LM_MODELS):
            raise ValueError("Unsupported ACE-Step model")
        manifest = self.current_manifest()
        if not manifest:
            raise RuntimeError("ACE-Step runtime is not installed")
        source = self.storage.runtime_dir / "versions" / manifest.commit
        target = "main" if model in {"acestep-v15-turbo", "acestep-5Hz-lm-1.7B"} else model
        self._run(
            [
                self._python(source),
                "-c",
                "import sys; sys.path.insert(0, sys.argv.pop(1)); from acestep.model_downloader import main; raise SystemExit(main())",
                str(source),
                "--model",
                target,
                "--dir",
                str(self.storage.models_dir),
                "--skip-main",
            ],
            source,
            progress,
        )

    def latest_commit(self) -> str:
        request = urllib.request.Request(GITHUB_COMMIT_API, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return str(json.load(response)["sha"])

    def _uv(self) -> str:
        try:
            from uv import find_uv_bin

            return find_uv_bin()
        except (ImportError, FileNotFoundError):
            pass
        bundled = _bundled_file("uv.exe" if sys.platform == "win32" else "uv")
        if bundled:
            return str(bundled)
        candidates = [
            Path(sys.executable).resolve().parent / "uv",
            Path(sys.executable).resolve().parent / "uv.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        found = shutil.which("uv")
        if found:
            return found
        raise RuntimeError("The bundled uv runtime helper was not found.")

    def _bridge(self) -> Path:
        bridge = _bundled_file("ace_studio_bridge.py") or Path(__file__).resolve().parents[1] / "ace_studio_bridge.py"
        if not bridge.is_file():
            raise RuntimeError("ACE Studio's packaged runtime bridge was not found.")
        return bridge

    def _run(self, command: list[str], cwd: Path, progress: ProgressCallback) -> None:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout
        for line in process.stdout:
            message = line.strip()
            if message:
                progress(message, None)
        if process.wait() != 0:
            raise RuntimeError(f"Runtime command failed with exit code {process.returncode}")

    def _specialized_install(self, source: Path, profile: RuntimeProfile, progress: ProgressCallback) -> None:
        uv = self._uv()
        environment = source / ".venv"
        self._run([uv, "venv", "--python", "3.12", str(environment)], source, progress)
        python = self._python(source)
        requirements = "requirements-xpu.txt"
        preinstall: list[str] = []
        if profile == RuntimeProfile.WINDOWS_ROCM:
            requirements = "requirements-rocm.txt"
            base = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2"
            preinstall = [
                f"{base}/rocm_sdk_core-7.2.0.dev0-py3-none-win_amd64.whl",
                f"{base}/rocm_sdk_devel-7.2.0.dev0-py3-none-win_amd64.whl",
                f"{base}/rocm_sdk_libraries_custom-7.2.0.dev0-py3-none-win_amd64.whl",
                f"{base}/rocm-7.2.0.dev0.tar.gz",
                f"{base}/torch-2.9.1+rocmsdk20260116-cp312-cp312-win_amd64.whl",
                f"{base}/torchaudio-2.9.1+rocmsdk20260116-cp312-cp312-win_amd64.whl",
                f"{base}/torchvision-0.24.1+rocmsdk20260116-cp312-cp312-win_amd64.whl",
            ]
        elif profile == RuntimeProfile.LINUX_ROCM:
            requirements = "requirements-rocm-linux.txt"
            preinstall = ["torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/rocm6.3"]
        elif profile == RuntimeProfile.LINUX_XPU:
            preinstall = ["torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/xpu"]
        if preinstall:
            self._run([uv, "pip", "install", "--python", python, *preinstall], source, progress)
        self._run([uv, "pip", "install", "--python", python, "-r", requirements], source, progress)
        self._run([uv, "pip", "install", "--python", python, "--no-deps", "-e", "."], source, progress)

    def install_latest(self, progress: ProgressCallback = lambda _message, _value: None) -> RuntimeManifest:
        with self._lock:
            self.state = RuntimeState.INSTALLING
            commit = self.latest_commit()
            versions = self.storage.runtime_dir / "versions"
            versions.mkdir(parents=True, exist_ok=True)
            destination = versions / commit
            if destination.exists() and self._probe(destination):
                return self._activate(commit, destination)
            if destination.exists():
                shutil.rmtree(destination)

            progress("Downloading ACE-Step source", 0.05)
            staging = Path(tempfile.mkdtemp(prefix=f"{commit[:8]}-", dir=self.storage.runtime_dir))
            archive = staging / "source.tar.gz"
            try:
                urllib.request.urlretrieve(GITHUB_ARCHIVE.format(commit=commit), archive)
                progress("Extracting ACE-Step", 0.15)
                with tarfile.open(archive) as bundle:
                    bundle.extractall(staging, filter="data")
                source = next(path for path in staging.iterdir() if path.is_dir())
                archive.unlink(missing_ok=True)
                profile = self.hardware.profile
                progress(f"Building {profile.value} runtime", 0.2)
                if profile in {
                    RuntimeProfile.WINDOWS_ROCM,
                    RuntimeProfile.WINDOWS_XPU,
                    RuntimeProfile.LINUX_ROCM,
                    RuntimeProfile.LINUX_XPU,
                }:
                    self._specialized_install(source, profile, progress)
                else:
                    self._run([self._uv(), "sync", "--frozen", "--no-dev", "--python", "3.12"], source, progress)
                if not self._probe(source):
                    raise RuntimeError("ACE-Step compatibility probe failed")
                shutil.copy2(self._bridge(), source / ".ace_studio_bridge.py")
                source.rename(destination)
                progress("Runtime ready", 1.0)
                return self._activate(commit, destination)
            except Exception:
                self.state = RuntimeState.FAILED
                raise
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)

    def _activate(self, commit: str, source: Path) -> RuntimeManifest:
        manifest = RuntimeManifest(
            commit=commit,
            profile=self.hardware.profile,
            python_version="3.12",
            source_url=GITHUB_ARCHIVE.format(commit=commit),
            installed_at=datetime.now(UTC).isoformat(),
        )
        temporary = self.current_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest.to_dict(), indent=2))
        temporary.replace(self.current_file)
        self.state = RuntimeState.READY
        return manifest

    def _python(self, source: Path) -> str:
        executable = source / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        return str(executable)

    def _probe(self, source: Path) -> bool:
        executable = self._python(source)
        if not Path(executable).exists():
            return False
        command = [executable, "-c", "from acestep.api_server import create_app; assert create_app().routes"]
        try:
            return subprocess.run(command, cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def start(self) -> tuple[int, str]:
        with self._lock:
            if self.process and self.process.poll() is None and self.port and self.token:
                return self.port, self.token
            manifest = self.current_manifest()
            if not manifest:
                raise RuntimeError("ACE-Step runtime is not installed")
            source = self.storage.runtime_dir / "versions" / manifest.commit
            self.state = RuntimeState.STARTING
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                self.port = reservation.getsockname()[1]
            self.token = secrets.token_urlsafe(32)
            environment = os.environ.copy()
            environment.update(
                {
                    "ACESTEP_API_KEY": self.token,
                    "ACESTEP_CHECKPOINTS_DIR": str(self.storage.models_dir),
                    "ACESTEP_TMPDIR": str(self.storage.runtime_dir / "tmp"),
                    "ACESTEP_NO_INIT": "true",
                    "ACESTEP_INIT_LLM": "true",
                    "PYTHONPATH": os.pathsep.join([str(source), environment.get("PYTHONPATH", "")]),
                }
            )
            model, lm_model = self.selected_models()
            environment["ACESTEP_CONFIG_PATH"] = model
            if lm_model:
                environment["ACESTEP_LM_MODEL_PATH"] = lm_model
            if manifest.profile == RuntimeProfile.MACOS_MLX:
                environment["ACESTEP_LM_BACKEND"] = "mlx"
                if (self.hardware.memory_gb or 0) <= 16:
                    environment["ACESTEP_SAVE_MEMORY"] = "1"
            if manifest.profile in {RuntimeProfile.WINDOWS_XPU, RuntimeProfile.LINUX_XPU}:
                environment.update({"PYTORCH_DEVICE": "xpu", "TORCH_COMPILE_BACKEND": "eager"})
            bridge = source / ".ace_studio_bridge.py"
            if not bridge.exists():
                shutil.copy2(self._bridge(), bridge)
            command = [self._python(source), str(bridge), "--host", "127.0.0.1", "--port", str(self.port)]
            log = (self.storage.logs_dir / "runtime.log").open("a", encoding="utf-8")
            self.process = subprocess.Popen(command, cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT, text=True)
            self.state = RuntimeState.ONLINE
            return self.port, self.token

    def stop(self) -> None:
        with self._lock:
            if not self.process or self.process.poll() is not None:
                return
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.state = RuntimeState.READY
