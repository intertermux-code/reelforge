# ReelForge

A desktop app for bulk-creating short vertical videos (Reels/Shorts/TikTok) from a folder of photos and a folder of music — plus a one-click audio extractor. Point it at your media, hit start, and get a batch of finished clips.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)

## Contents

- [Screenshots](#screenshots)
- [What it does](#what-it-does)
- [Install](#install)
- [AI text overlay (optional)](#ai-text-overlay-optional)
- [Building a standalone binary](#building-a-standalone-binary)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [License](#license)

## Screenshots

> Screenshots coming soon — the app in action speaks louder than words.

<!--
To add screenshots:
1. Drop PNGs into docs/screenshots/
2. Reference them here, e.g.:
   ![Photo Weaver tab](docs/screenshots/weaver-tab.png)
   ![Audio Extractor tab](docs/screenshots/extractor-tab.png)
-->

## What it does

**Photo Weaver tab** — batch video generator:
- Randomly pairs one photo with one song per video
- 9:16 (Reels), 1:1, 16:9, or original aspect ratio
- Optional sticker overlay, black-and-white filter, text overlay with custom font/size/color
- Reference-image matching: hide a watermark/logo wherever it appears (OpenCV template matching)
- Optional AI-generated text overlay (see below)
- Runs in a background thread — the UI never freezes, and you can cancel mid-batch

**Audio Extractor tab** — point it at a folder of videos, get the audio tracks out as MP3/WAV/M4A.

## Install

**1. Install ffmpeg** (required — it does the actual encoding):

| OS | Command |
|---|---|
| macOS | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows | Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH |

**2. Set up Python** (3.9+):

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate.bat
pip install -r requirements.txt
```

**3. Run:**

```bash
python main.py
```

Optional: copy `config.example.json` to `config.json` to preset your folders. Settings are also saved automatically when you close the app.

## AI text overlay (optional)

Tick "Generate AI text overlay" and each video gets a unique AI-written line burned into the frame. It tries three sources in order and degrades gracefully:

1. **Gemini API** — set the `GEMINI_API_KEY` environment variable
2. **Local `gemini` CLI** — if installed on your PATH (uses the same env var for auth)
3. **Built-in fallback list** — always works, no key needed

The prompt is configurable via the `weaver_ai_prompt` setting (empty = sensible generic default). Generated lines are deduplicated against a persistent history log, so you won't get repeats across batches.

```bash
export GEMINI_API_KEY="your-key-here"
python main.py
```

> Never hardcode API keys in source. The app only reads the key from the environment.

## Building a standalone binary

A PyInstaller spec is included:

```bash
pip install pyinstaller
pyinstaller build.spec
```

The binary lands in `dist/`.

## Project layout

```
main.py           # entry point: logging + app launch
app.py            # main window, tab container, save-on-close
weaver_tab.py     # Photo Weaver UI
extractor_tab.py  # Audio Extractor UI
processor.py      # background workers: video rendering, AI text, extraction
utils.py          # file discovery, OpenCV helpers, text rendering
settings.py       # config.json load/save with safe defaults
config.example.json  # template for your own config.json (git-ignored)
```

## Contributing

Pull requests are welcome. A few ground rules:

- Keep it dependency-light — think twice before adding a new package.
- No secrets in code, ever. API keys come from the environment.
- No hardcoded paths. Everything user-specific belongs in settings.
- Match the existing style: docstrings, type hints, background threads for anything slow.

## License

MIT
