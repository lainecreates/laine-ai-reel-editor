# Changelog

## 1.0.0-beta.2 (private beta)

Fixes from the first beta installation test:

- **The 24 included fonts are now part of the download.** In 1.0.0-beta.1 they were left out
  of the GitHub repository by mistake, with their licenses and catalog. Run "Update my reel
  editor" to get them.
- **Tools you already have are used as they are**: the installer recognises tool paths set in
  `config/settings.json` (whisper-cli, FFmpeg, Node.js), and only needs Homebrew when something
  is actually missing.
- **A plain note before Homebrew installs or updates anything** that other apps on your Mac may
  share. Nothing you have is removed.

## 1.0.0-beta.1 (private beta)

Everything in 0.9.0, plus:

- **Six styles**: Luxe, Playful, Magazine, Minimal, Bold and Energetic, with 76 designs across
  headlines, lists, statistics, quotes, comparisons, tips and calls to action. Classic keeps
  earlier reels exactly as they were.
- **Creative plan**: Claude decides what deserves a graphic, which words to highlight and where
  to zoom, from what you actually say, and leaves your face alone when that's stronger.
- **Your style in your own words**, exact HEX colours for headlines, captions and key words,
  always/never rules, and mixing styles. Reference reels teach the feel, never the content.
- **Design variety**: reels vary on purpose. **✨ Try another design** changes one graphic.
- **Composition per video**: placement is judged from your footage. Text can tuck over hair,
  never covers the face, and moves before it shrinks.
- **Image carousel**, **page-flip calendar**, and **custom effects** built for one reel.
- **Font library**: 24 included Google Fonts (open-source licenses), previews in Brand
  settings, for headlines, captions or graphics.
- **iPhone photos (HEIC)** convert automatically, upright and never cropped.
- **Repeated speech**: quote a phrase and which time to remove it. Repeats spoken without a
  pause can be cut at a measured quiet point, and every join is re-checked by listening again.
- **Fewer questions**: the headline is chosen from your words automatically (change it in
  review). Claude asks only when it needs your decision.
- Needs **Node.js 22 or newer** (the installer handles it).
- License covers invited beta testers and customers. The included fonts keep their own licenses.

## 0.9.0 (pre-release)

First customer package of Laine AI Reel Editor, for Apple silicon Macs.

- Cuts pauses, repeats, fillers and false starts from a talking-head video, and makes a vertical 1080x1920 MP4.
- Brand onboarding, one question at a time. A clean neutral look is used until it's done.
- Branded captions, headline, zooms, graphics and sound effects, kept clear of the face.
- Review page in your browser:
  - notes and cut, caption, headline and graphic edits
  - numbered versions, compare and restore
  - Finalize & Download
- Brand settings for "this reel only" or "my saved defaults", with a dated history and Restore.
- Each reel keeps the brand it was made with.
- Asset library for your own fonts, MP3/WAV sounds and PNG/JPG images.
- `install.sh` checks the Mac and asks before installing anything. `--check` and `--dry-run` change nothing.
- Customer license (LICENSE): use for your own and paying clients' videos and customize it for yourself; no reselling or redistributing.
