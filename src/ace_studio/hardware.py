from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

from .models import HardwareReport, RuntimeProfile


def _memory_gb() -> float | None:
    try:
        if sys.platform == "darwin":
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3)) / 1024**3
        if sys.platform == "win32":
            command = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"]
            return int(subprocess.check_output(command, text=True, timeout=5).strip()) / 1024**3
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024**2
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def _gpu_name() -> str:
    if sys.platform == "darwin":
        return platform.processor() or "Apple Silicon"
    commands = (
        [
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ', '",
            ]
        ]
        if sys.platform == "win32"
        else [["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], ["lspci"]]
    )
    for command in commands:
        try:
            if value := subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=5).strip():
                return value.splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            pass
    return "CPU"


def detect_hardware() -> HardwareReport:
    os_name = platform.system()
    architecture = platform.machine().lower()
    processor = platform.processor() or architecture
    gpu = _gpu_name()
    value = gpu.lower()
    notes: list[str] = []
    driver_ready = True
    if sys.platform == "darwin":
        profile = RuntimeProfile.MACOS_MLX
        driver_ready = architecture in {"arm64", "aarch64"}
        if not driver_ready:
            notes.append("ACE-Step's macOS acceleration requires Apple Silicon.")
    elif sys.platform == "win32":
        if "nvidia" in value:
            profile = RuntimeProfile.WINDOWS_CUDA
        elif "amd" in value or "radeon" in value:
            profile = RuntimeProfile.WINDOWS_ROCM
        elif "intel" in value and ("arc" in value or "iris" in value):
            profile = RuntimeProfile.WINDOWS_XPU
        else:
            profile = RuntimeProfile.WINDOWS_CPU
            notes.append("No supported GPU runtime was detected; CPU mode will be used.")
    else:
        if "nvidia" in value:
            profile = RuntimeProfile.LINUX_CUDA
        elif "amd" in value or "radeon" in value:
            profile = RuntimeProfile.LINUX_ROCM
        elif "intel" in value and ("arc" in value or "graphics" in value):
            profile = RuntimeProfile.LINUX_XPU
        else:
            profile = RuntimeProfile.LINUX_CPU
            notes.append("No supported GPU runtime was detected; CPU mode will be used.")
    return HardwareReport(os_name, architecture, processor, _memory_gb(), gpu, profile, driver_ready, notes)


def recommended_models(report: HardwareReport) -> tuple[str, str | None]:
    memory = report.memory_gb or 0
    if report.profile in {RuntimeProfile.WINDOWS_CPU, RuntimeProfile.LINUX_CPU} or memory <= 6:
        return "acestep-v15-turbo", None
    if report.profile == RuntimeProfile.MACOS_MLX and memory <= 16:
        return "acestep-v15-turbo", "acestep-5Hz-lm-0.6B"
    if memory < 24:
        return "acestep-v15-turbo", "acestep-5Hz-lm-1.7B"
    return "acestep-v15-xl-turbo", "acestep-5Hz-lm-1.7B"
