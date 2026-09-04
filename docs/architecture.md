# ACE Studio architecture

ACE Studio is a local desktop client around a separately installed, pinned ACE-Step runtime.

```text
Flet views
   │ user intent / presentation updates
   ▼
GenerationService ───── TrainingService
   │                         │
   ├──── AceClient ──────────┤ authenticated localhost HTTP
   ├──── RuntimeManager      │ staged install and process lifecycle
   └──── Storage ────────────┘ SQLite plus managed audio/training files
```

## Ownership

`app.py` is the composition root and shared shell. Screen-specific controls live in `views/`; playback events live in `playback.py`. Views call concrete services and never embed ACE-Step endpoint paths or parse upstream responses.

The `services/` package keeps the two workflows separate. `GenerationService` owns runtime readiness, model initialization, generation/edit polling, cancellation, downloads, and library persistence. `TrainingService` owns dataset scan/edit/save, optional labeling, preprocessing, LoRA/LoKr execution, export, and adapter activation. Its one-click pipeline reports progress to the view and is the only place that sequences those training stages. Both reuse `AceClient` and `Storage`.

`RuntimeManager` installs only `SUPPORTED_COMMIT`. Installation happens in a staging directory, the route compatibility probe runs before activation, and `current.json` changes only after success. The existing runtime therefore survives download, installation, or probe failures.

## State and failures

- Generated and edited audio is copied into the managed library before its database record is committed.
- Edited library tracks retain a parent relationship to their source.
- Dataset JSON, tensors, runs, and exported adapters live below the training directory.
- Adapter metadata persists in SQLite. A saved active adapter is restored after runtime initialization only when its files still exist.
- Cancellation stops polling and the local process; a later request starts a fresh authenticated client.
- Network, runtime, validation, and filesystem errors cross service boundaries as exceptions and are presented by the active view.
- Memory safety settings (`memory.json`) are persisted in the runtime directory and owned by `RuntimeManager`. The file controls generation and training caps (`MemoryMode`, batch, duration, checkpointing) and is read by `GenerationService` and `TrainingService` before work begins. A corrupt or missing file falls back to hardware-detected safe defaults.

Tests use temporary storage, mocked processes, fake services, and a localhost HTTP server. They never require external network access, downloaded models, or accelerator hardware.
