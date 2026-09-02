<h1 align="center"><img src="src/assets/icon.png" alt="ACE Studio logo" width="44" valign="middle"> ACE Studio</h1>

**Create music locally with [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5).**

ACE Studio is a desktop client for turning a musical idea, lyrics, and a few musical constraints into generated audio. It manages the ACE-Step runtime and models on your machine, chooses a suitable hardware profile, and keeps finished tracks in a searchable local library.

> Your prompts, runtime, models, and generated music stay on your computer. Internet access is needed only to download ACE-Step, its dependencies, and models.

## Download

Download the installer for your platform from [GitHub Releases](https://github.com/alvarolorentedev/ace-studio/releases):

- macOS: DMG
- Windows: installer EXE
- Debian/Ubuntu: `.deb` package

Release installers are unsigned. Your operating system may ask you to explicitly allow the app during installation.

## What you can do

- Generate songs from a text description, with optional lyrics.
- Set duration (30 seconds–10 minutes), BPM, key, time signature, instrumental mode, seed, guidance, and up to four versions per run.
- Use ACE-Step’s language model to improve a music prompt or lyric draft, develop a short idea, or start from a random prompt.
- Play generated tracks in the app, save a copy, search your library, rename tracks, and mark favorites.
- Let ACE Studio detect Apple Silicon, NVIDIA, AMD, Intel, or CPU-only hardware and install a matching ACE-Step runtime.
- Select and download alternate generation and language models from Settings, then check for ACE-Step updates without replacing a working runtime until the update passes a compatibility probe.

The **Edit** and **Train** areas are currently interface previews; audio editing and adapter training are not yet connected to executable workflows.

## First launch

1. Open ACE Studio and review the detected hardware profile and recommended models.
2. Select **Install ACE-Step**.
3. Wait while the app downloads the current ACE-Step release, creates an isolated runtime, installs dependencies, and downloads the recommended model(s).
4. Enter a music description (and optionally lyrics) on **Create**, then select **Generate**.

The first setup can take several minutes and multiple gigabytes, depending on the selected models and connection. Later launches reuse the installed runtime and models.

## A quick look

### Create with prompts, lyrics, and musical controls

![ACE Studio's Create workspace](docs/screenshots/create.jpg)

### Browse the local music library

![ACE Studio's empty Library workspace](docs/screenshots/library.jpg)

### Manage hardware, models, and updates

![ACE Studio's Settings workspace](docs/screenshots/settings.jpg)

### Prepare an audio edit

![ACE Studio's Edit workspace](docs/screenshots/edit.jpg)

### Prepare LoRA or LoKr adapter training

![ACE Studio's Train workspace](docs/screenshots/train.jpg)

## Using ACE Studio

### Create a track

Describe the sound, mood, instruments, and arrangement you want. Add structured lyrics if you want vocals, or switch on **Instrumental**. The inspector lets you shape the duration, tempo, key, time signature, number of versions, reproducible seed, and guidance. During generation, ACE Studio shows progress and lets you stop the run.

Use **Improve music**, **Improve lyrics**, or **Develop idea** when a language model is installed and you want help refining a starting draft.

### Manage your library

Every completed version is copied into the local library automatically. From **Library**, you can play tracks, search by title or prompt, favorite them, rename them, delete them, or save a copy through the player’s download button.

### Choose models and update ACE-Step

Open **Settings** to see the detected hardware, download supported models, choose active generation and language models, or check for an ACE-Step update. Updates are staged and probed before activation, so a failed update leaves the existing runtime active.

## Local data

ACE Studio stores its runtime, downloaded models, generated audio, library database, training data, and logs in the following location by default:

| Platform | Location |
| --- | --- |
| macOS | `~/Library/Application Support/ACE Studio` |
| Windows | `%LOCALAPPDATA%\\ACE Studio` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/ace-studio` |

Set `ACE_STUDIO_DATA_DIR` before launching the app to use a different location.

## Run from source

### Requirements

- macOS, Windows, or Linux
- [Python 3.12](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A supported accelerator is recommended. Apple Silicon uses MLX; Windows and Linux can use NVIDIA CUDA, AMD ROCm, or Intel XPU when detected. CPU fallback is available on Windows and Linux, but generation will be substantially slower.

Clone the repository, then install the app environment and start it:

```bash
git clone https://github.com/alvarolorentedev/ace-studio.git
cd ace-studio
make install
make run
```

`make install` creates a local `.venv` with Python 3.12 and installs ACE Studio. `make run` opens the desktop application.

If you already have the repository, the short path is:

```bash
make run
```

## Development commands

```bash
make help       # list available commands
make run-web    # run the development UI in a browser
make test       # run tests
make check      # run tests, compile checks, and diff whitespace checks
```

To build a local application bundle, first stage the packaged runtime and then use the platform target:

```bash
make build-macos
make build-windows
make build-linux
```

## Troubleshooting

- **Setup fails or is slow:** confirm that you have a working internet connection and enough free disk space for dependencies and models; retry **Install ACE-Step** from the setup screen.
- **Generation is slow:** use a supported GPU or Apple Silicon when possible. CPU mode works as a fallback but is intended for compatibility, not fast generation.
- **A model cannot be selected:** download it first in **Settings**; only installed models can become active.
- **Need a clean local install:** close ACE Studio, remove or rename its data directory above, then launch and install again. This also removes locally stored models and music unless you back them up first.

## Credits and licensing

ACE Studio is distributed under the [license in this repository](LICENSE). ACE-Step is downloaded from its [official repository](https://github.com/ace-step/ACE-Step-1.5) and retains its upstream license. Model downloads are subject to their respective licenses.
