"""Stage native runtime helpers as Flet assets for the current build platform."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from uv import find_uv_bin

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "assets" / "bin"


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    uv = Path(find_uv_bin())
    shutil.copy2(uv, TARGET / uv.name)
    shutil.copy2(ROOT / "src" / "ace_studio_bridge.py", TARGET / "ace_studio_bridge.py")
    if sys.platform != "win32":
        (TARGET / uv.name).chmod((TARGET / uv.name).stat().st_mode | 0o111)


if __name__ == "__main__":
    main()
