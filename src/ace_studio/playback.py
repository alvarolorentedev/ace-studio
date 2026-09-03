from __future__ import annotations

import asyncio
from pathlib import Path

import flet as ft
from flet_audio import AudioState


async def resume(studio) -> None:
    if not studio.audio:
        return
    if studio.audio_state == AudioState.COMPLETED:
        await studio.audio.play()
    else:
        await studio.audio.resume()


async def toggle(studio, _event: ft.Event | None = None) -> None:
    try:
        if studio.audio_state == AudioState.PLAYING and studio.audio:
            await studio.audio.pause()
        else:
            await studio._resume_audio()
    except Exception as exc:
        studio.notice(f"Could not play this track: {exc}", True)


def state_changed(studio, event) -> None:
    studio.audio_state = event.state
    button = getattr(studio, "play_pause_button", None)
    if button:
        button.icon = ft.Icons.PAUSE if event.state == AudioState.PLAYING else ft.Icons.PLAY_ARROW
        button.tooltip = "Pause" if event.state == AudioState.PLAYING else "Play"
    studio.now_meta.value = {
        AudioState.PLAYING: "Playing · ACE-Step 1.5",
        AudioState.PAUSED: "Paused",
        AudioState.COMPLETED: "Finished · Press play to replay",
    }.get(event.state, studio.now_meta.value)
    studio.page.update()
    if event.state == AudioState.COMPLETED:
        if studio.repeat_mode == "one":
            studio.page.run_task(studio._resume_audio)
        elif studio.repeat_mode == "all":
            studio.page.run_task(studio._skip_track, 1)


def loaded(studio, _event) -> None:
    studio.audio_loaded.set()


def duration_changed(studio, event) -> None:
    seconds = event.duration.in_seconds
    studio.progress.max = max(1, seconds)
    studio.total.value = studio._format_time(seconds)
    studio.page.update()


def position_changed(studio, event) -> None:
    if not studio.seeking:
        seconds = event.position / 1000
        studio.progress.value = seconds
        studio.elapsed.value = studio._format_time(seconds)
        studio.page.update()


async def skip(studio, offset: int) -> None:
    tracks = studio.storage.generations()
    if not tracks:
        studio.notice("Generate a song first.", True)
        return
    current = studio.current_audio_path
    index = next((i for i, track in enumerate(tracks) if str(Path(track["audio_path"]).resolve()) == current), -1 if offset > 0 else 0)
    track = tracks[(index + offset) % len(tracks)]
    await studio._play_track(track["audio_path"], track["title"])


async def play(studio, path: str, title: str, audio_factory) -> None:
    try:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError("The saved audio file is missing")
        source_path = str(source.resolve())
        source_changed = studio.audio is None or studio.audio.src != source_path
        if studio.audio is None:
            studio.audio_loaded.clear()
            studio.audio = audio_factory(
                src=source_path,
                volume=0.85,
                on_loaded=studio._audio_loaded,
                on_state_change=studio._audio_state_changed,
                on_duration_change=studio._audio_duration_changed,
                on_position_change=studio._audio_position_changed,
            )
            studio.page.services.append(studio.audio)
        elif source_changed:
            studio.audio_loaded.clear()
            studio.audio.src = source_path
        studio.now_title.value = title
        studio.now_meta.value = "Loading saved audio…"
        studio.current_audio_path = source_path
        studio.current_audio_title = title
        studio.progress.value = 0
        studio.elapsed.value = "0:00"
        studio.total.value = "—:—"
        studio.page.update()
        if source_changed:
            await asyncio.wait_for(studio.audio_loaded.wait(), timeout=15)
        await studio.audio.play()
    except Exception as exc:
        studio.now_meta.value = "Playback failed"
        studio.page.update()
        studio.notice(f"Could not play this track: {exc}", True)
