import subprocess
import unittest
from unittest.mock import patch

from ace_studio import hardware
from ace_studio.models import RuntimeProfile


class HardwareTest(unittest.TestCase):
    def test_memory_detection_for_each_platform_and_failure(self):
        with (
            patch("ace_studio.hardware.sys.platform", "darwin"),
            patch("ace_studio.hardware.subprocess.check_output", return_value=str(16 * 1024**3)),
        ):
            self.assertEqual(hardware._memory_gb(), 16)
        with (
            patch("ace_studio.hardware.sys.platform", "win32"),
            patch("ace_studio.hardware.subprocess.check_output", return_value=str(8 * 1024**3)),
        ):
            self.assertEqual(hardware._memory_gb(), 8)
        with (
            patch("ace_studio.hardware.sys.platform", "linux"),
            patch("pathlib.Path.read_text", return_value="MemTotal:       4194304 kB\n"),
        ):
            self.assertEqual(hardware._memory_gb(), 4)
        with patch("ace_studio.hardware.subprocess.check_output", side_effect=subprocess.SubprocessError):
            self.assertIsNone(hardware._memory_gb())

    def test_gpu_detection_uses_platform_commands_and_cpu_fallback(self):
        with patch("ace_studio.hardware.sys.platform", "darwin"), patch("ace_studio.hardware.platform.processor", return_value="arm"):
            self.assertEqual(hardware._gpu_name(), "arm")
        with (
            patch("ace_studio.hardware.sys.platform", "linux"),
            patch("ace_studio.hardware.subprocess.check_output", side_effect=[OSError(), "NVIDIA RTX\n"]),
        ):
            self.assertEqual(hardware._gpu_name(), "NVIDIA RTX")
        with patch("ace_studio.hardware.sys.platform", "linux"), patch("ace_studio.hardware.subprocess.check_output", side_effect=OSError):
            self.assertEqual(hardware._gpu_name(), "CPU")

    def test_detect_hardware_selects_profiles(self):
        cases = [
            ("darwin", "arm64", "Apple", RuntimeProfile.MACOS_MLX),
            ("win32", "x86_64", "NVIDIA RTX", RuntimeProfile.WINDOWS_CUDA),
            ("win32", "x86_64", "AMD Radeon", RuntimeProfile.WINDOWS_ROCM),
            ("win32", "x86_64", "Intel Arc", RuntimeProfile.WINDOWS_XPU),
            ("win32", "x86_64", "CPU", RuntimeProfile.WINDOWS_CPU),
            ("linux", "x86_64", "NVIDIA RTX", RuntimeProfile.LINUX_CUDA),
            ("linux", "x86_64", "AMD Radeon", RuntimeProfile.LINUX_ROCM),
            ("linux", "x86_64", "Intel Graphics", RuntimeProfile.LINUX_XPU),
            ("linux", "x86_64", "CPU", RuntimeProfile.LINUX_CPU),
        ]
        for platform_name, machine, gpu, expected in cases:
            with (
                self.subTest(expected=expected),
                patch("ace_studio.hardware.sys.platform", platform_name),
                patch("ace_studio.hardware.platform.system", return_value=platform_name),
                patch("ace_studio.hardware.platform.machine", return_value=machine),
                patch("ace_studio.hardware.platform.processor", return_value="processor"),
                patch("ace_studio.hardware._gpu_name", return_value=gpu),
                patch("ace_studio.hardware._memory_gb", return_value=8),
            ):
                self.assertEqual(hardware.detect_hardware().profile, expected)


if __name__ == "__main__":
    unittest.main()
