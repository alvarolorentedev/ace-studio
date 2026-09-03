"""Private ACE Studio routes layered onto the unmodified ACE-Step FastAPI app."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import uvicorn
from acestep.api.http.auth import verify_api_key
from acestep.api_server import create_app
from acestep.training.path_safety import set_safe_root
from fastapi import Depends, HTTPException

set_safe_root(str(Path.home()))
app = create_app()


@app.get("/studio/v1/waveform")
async def waveform(path: str, bins: int = 600, _: None = Depends(verify_api_key)):
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    bins = max(64, min(4000, bins))
    audio, sample_rate = sf.read(resolved, always_2d=True, dtype="float32")
    mono = np.max(np.abs(audio), axis=1)
    if len(mono) == 0:
        return {"duration": 0, "peaks": []}
    width = max(1, len(mono) // bins)
    peaks = [float(np.max(mono[index : index + width])) for index in range(0, len(mono), width)][:bins]
    return {"duration": len(audio) / sample_rate, "sample_rate": sample_rate, "peaks": peaks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, workers=1, log_level=os.getenv("ACESTEP_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
