# Laine AI Reel Editor

A reel editor that runs on this Mac. The project skill is `laine-reel-editor`
(`.claude/skills/laine-reel-editor/`). Architecture: `docs/ARCHITECTURE.md`.
Dependencies: `DEPENDENCIES.md`. Customer guide: `docs/CUSTOMER-GUIDE.md`.

## Keep everything in this folder

- Reels go in `workspace/`, brand files in `brand/`, uploads in `assets/library/`.
- Skills stay in `.claude/skills/` here. Never install skills globally.
- Never change `~/.claude/` or `~/.claude.json`.
- **Never install, upgrade or download anything without asking the customer first.**
  - `./install.sh` is the only installer, and it asks before every step.
  - Use system/Homebrew `ffmpeg`, `ffprobe`, `node`, `python3` and `whisper-cli` as they are.
  - No `pip install`, no `npm install`, no global installs.
- If `config/settings.json` lists `protected_paths`, never read from or write to them.

## Updating ("Update my reel editor")

1. Run `git status --short`. Only the editor's own files can show changes. The customer's brand, uploads, reels, settings and models are git-ignored.
2. If editor files were changed locally, ask before discarding anything.
3. Run `git pull --ff-only`, then `./install.sh --check`.
4. Tell the customer what changed: the new entries in `CHANGELOG.md`.

## Engineering rules

- Python standard library only in `scripts/` (no pip dependencies).
- **Cutting:**
  - Never cut where `silencedetect` didn't measure silence. Whisper times are not trusted for cut points.
  - Cleanup cuts also start and end inside measured gaps (≥ 30 ms). If there is no clean gap, the words stay in.
  - Cleanup must never change meaning or leave an incomplete sentence. When unsure, leave it in.
- **Drawing:**
  - No `drawtext` / `subtitles` / `ass` filters. Text and graphics are drawn by headless Chrome (`tools/render_overlay.mjs`, with its own temporary profile) and composited with `overlay`.
  - Never place captions or graphics over the face (`layout.py`). Check frames before showing.
- **Caption sync is measured, not guessed:** `python3 tests/sync_bench.py`. Any change to transcription or alignment must keep its median within ±0.04 s.
- **Reviews and versions:**
  - Reviews write per-reel files only. Never change `brand/` from a review.
  - Keep every previous render.
  - Each reel keeps the brand it was made with (`brand.snapshot.json`).
- Never modify the customer's input clip or `source/original.*`.
- After code changes, run `python3 -m unittest discover -s tests` and `python3 tests/selftest.py`.
