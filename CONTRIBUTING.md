# Contributing to ACE Studio

## Setup

Install Python 3.12 and `uv`, then run:

```bash
make install
make check
```

`make check` runs the unit and local HTTP integration tests with branch coverage, enforces the 80% project threshold, runs Ruff, compiles the Python modules, and checks the Git diff for whitespace errors.

## Project structure

- `src/ace_studio/app.py` constructs services and owns the application shell and navigation.
- `src/ace_studio/views/` contains one Flet view builder per screen. Views may update controls, but domain rules and upstream paths belong elsewhere.
- `src/ace_studio/services/` separates generation/edit orchestration from dataset/training/adapter orchestration.
- `src/ace_studio/api.py` owns the authenticated ACE-Step HTTP contract.
- `src/ace_studio/runtime.py` installs and runs the pinned ACE-Step runtime; `hardware.py` detects the local profile.
- `src/ace_studio/storage.py` owns SQLite and managed local files.
- `tests/` mirrors these responsibilities. Tests must not download models or require a GPU.

Prefer a direct function or concrete service over a new interface or framework. Add a dependency only when the standard library and installed packages cannot do the job.

## Updating ACE-Step

ACE Studio deliberately installs the commit in `ace_studio.runtime.SUPPORTED_COMMIT`. To update it:

1. Review upstream API and model changes.
2. Change the pinned commit.
3. Update the compatibility probe and request models if required.
4. Run `make check`.
5. Manually verify install, generation, one edit, short preprocessing/training, adapter loading, and packaged startup on supported hardware.

Do not replace the pin with a moving branch. A failed staged install must leave the previous runtime active.

## Releases

Release builds run the same quality gate before packaging. Update the project and About versions together, build the installer for each platform, and complete the manual runtime checklist before tagging.
