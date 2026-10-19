# Laine AI Reel Editor

https://github.com/LaineCreates/laine-ai-reel-editor

Turn a raw talking-head video into a clean, branded vertical reel by talking to
Claude:

- It cuts dead air, repeats, "um"s and false starts. You can also quote any phrase to remove ("the first 'they started'").
- Claude listens to what you say and plans what deserves to be on screen, and why: headline, graphics, highlighted words and zooms.
- Six styles (Luxe, Playful, Magazine, Minimal, Bold, Energetic), each with several designs, in your exact colours and fonts. Reels vary on purpose.
- Image carousels, a page-flip calendar, and custom effects described in your own words.
- 24 included fonts with previews, plus your own uploads. iPhone (HEIC) photos are converted automatically.
- Everything is kept clear of your face and inside the platforms' safe areas.
- You review it in your browser, ask for changes and download the final MP4.

**Status: private beta (1.0.0-beta.1).** Testing is by invitation; see [LICENSE](LICENSE).

Everything runs on your own Mac. Your videos never leave it.

## What you need

- An Apple silicon Mac (M1 or newer) with macOS 13 Ventura or newer.
- A Claude Pro (or Max) plan and the free Claude desktop app.
- The installer sets up the free tools it needs (Homebrew, FFmpeg, whisper.cpp, Node.js 22+, Google Chrome), asking first.
- About 4 GB of free space for setup, plus room for your reels.

## Install

Follow **[INSTALL.md](INSTALL.md)**. It takes about 30–40 minutes, mostly
waiting for downloads, and needs no technical experience.

The short version, for people who've done this before:

```bash
git clone https://github.com/LaineCreates/laine-ai-reel-editor.git ~/laine-ai-reel-editor
~/laine-ai-reel-editor/install.sh
```

Then open the Claude app, go to the **Code** tab, choose the
`laine-ai-reel-editor` folder and type **Start my brand onboarding**.

## Using it

See **[docs/CUSTOMER-GUIDE.md](docs/CUSTOMER-GUIDE.md)**. You mostly say three things:

- **Start my brand onboarding**: set up your colours, fonts, captions and style.
- **Edit my reel**: give it a video, then review it in your browser.
- **Update my reel editor**: get the latest version. Your brand, uploads and reels stay as they are.

Problems? See **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**.

## Privacy

- Your brand, uploads and reels stay in this folder on your Mac. They're never part of updates.
- The editor installs nothing without asking.
- Captions are drawn by a hidden copy of Chrome with its own temporary profile. Your own browsing and logins are never touched.

## License

The editor: see [LICENSE](LICENSE) (invited beta testers and customers).
The 24 included fonts have their own open-source licenses (SIL Open Font License 1.1;
Apache 2.0 for Permanent Marker): see [assets/fonts/included/README.md](assets/fonts/included/README.md).
