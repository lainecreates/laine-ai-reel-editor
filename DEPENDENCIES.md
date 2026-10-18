# Dependencies

Everything Laine AI Reel Editor needs on a Mac. `./install.sh` checks all of
it and installs what's missing (it asks first). To check without changing anything:

```bash
./install.sh --check            # or: python3 scripts/reel.py doctor
```

## Supported Macs

| Requirement | Why |
|---|---|
| **Apple silicon (M1 or newer)** | The only chip tested and supported in this version |
| **macOS 13 Ventura or newer** | Needed by Homebrew's current tools and Apple Vision face detection |
| **About 4 GB free** for setup, plus about 1 GB per 10 reels | Tools, speech model, reels and versions |

## Required

| # | Dependency | Tested version | Used for | How it's installed | Size |
|---|---|---|---|---|---|
| 1 | **Claude Pro or Max** plan + **Claude desktop app** (Code tab) | 2026 | Runs the editor: onboarding, "Edit my reel", reviews | The customer, from claude.ai and claude.ai/download | ~300 MB |
| 2 | **Homebrew** | 4.x | Installs the tools below | The customer, one command from brew.sh (needs the Mac password) | ~500 MB |
| 3 | **Xcode Command Line Tools** (`git`, `python3` 3.9+) | git 2.39, Python 3.9.6 | `git`: download and update the editor. `python3`: the editor itself (standard library only) | Automatically with Homebrew; or `xcode-select --install` | ~1–2 GB |
| 4 | **FFmpeg** (with `ffprobe`) | 9.0 | Cutting, silence detection, audio, zooms, final MP4 | `install.sh` → `brew install ffmpeg` | ~150 MB |
| 5 | **whisper.cpp** (`whisper-cli`) | 1.9 | Speech to text with word timings | `install.sh` → `brew install whisper-cpp` | ~10 MB |
| 6 | **Speech model** `ggml-small.en.bin` | – | The model whisper.cpp uses | `install.sh` downloads it into `models/` (SHA-256 checked) | 465 MB |
| 7 | **Node.js 18+** | 26 | Drives Chrome to draw captions and graphics (no npm packages) | `install.sh` → `brew install node` | ~100 MB |
| 8 | **Google Chrome** (or Chromium) | 2026 stable | Draws captions, headline and graphics in a hidden window with its own temporary profile | Existing Chrome is reused; otherwise `install.sh` → `brew install --cask google-chrome` | ~600 MB |

## Built into macOS (nothing to install)

| What | Used for |
|---|---|
| Apple Vision via `osascript` (JavaScript for Automation) | Finding the face, so captions and graphics never cover it |
| `say` | Only the installer's test edit and the self-test |
| Safari (or any browser) | The review page at http://127.0.0.1:8765/ (local only) |

## FFmpeg features used

Any Homebrew FFmpeg has these, and `doctor` checks each one:

- **Filters:**
  - `silencedetect`, `volumedetect`, `trim`, `atrim`, `concat`, `afade`
  - `split`, `asplit`, `scale`, `crop`, `fps`, `loudnorm`, `gblur`, `overlay`
  - `zoompan`, `adelay`, `amix`, `volume`, `alimiter`, `sidechaincompress`
  - sound-pack generators: `anoisesrc`, `aevalsrc`, `bandpass`, `highpass`, `lowpass`, `aecho`
- **Encoders:** `libx264`, `aac`.
- **Not needed:** `drawtext`, `subtitles`, `ass`, `libass`, `libfreetype`.

## Not needed

- Python or npm packages.
- Paid APIs or API keys.
- A GitHub account.
- Fonts or sound packs. Brand fonts are optional uploads, and the sound pack is generated on the Mac.

## Licences of what customers install

The editor doesn't ship any of these tools. Each customer installs them from their official sources:

- FFmpeg: LGPL/GPL
- whisper.cpp and the Whisper model: MIT
- Node.js: MIT
- Chrome: Google's terms
- Homebrew: BSD-2

## Per-machine settings

`install.sh` creates `config/settings.json` from `config/settings.example.json`.
It's never part of updates. You only need to edit it if a tool lives somewhere
unusual (`"tools": {"ffmpeg": "/path/to/ffmpeg"}`) or the speech model is
elsewhere (`"whisper_model": "/path/to/model.bin"`).
