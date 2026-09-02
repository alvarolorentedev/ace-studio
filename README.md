# ACE Studio

ACE Studio is a Spotify-inspired desktop client for [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5). It installs and updates ACE-Step inside the app, selects a backend from the detected hardware, and stores generated music in its library.

## Run from source

Python 3.11 or 3.12 is required.

```bash
make run
```

Run `make help` for tests, browser development, builds, and cleanup commands.

On first launch, choose **Install ACE-Step**. The app downloads the current upstream `main` commit, builds an isolated runtime, performs a compatibility probe, and only then activates it. Failed updates leave the previous runtime active.

## Build installers

```bash
uv run flet build macos src
uv run flet build windows src
uv run flet build linux src
```

Release automation produces an unsigned macOS DMG, Windows installer EXE, and Debian package.

ACE-Step is downloaded from its official repository and retains its upstream license. Model downloads are subject to their respective licenses.
