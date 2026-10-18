# Laine AI Reel Editor

https://github.com/LaineCreates/laine-ai-reel-editor

Turn a raw talking-head video into a clean, branded vertical reel by talking to
Claude:

- It cuts dead air, repeats, "um"s and false starts.
- It adds captions in your brand style, a headline, zooms, graphics and sound effects, all kept clear of your face.
- You review it in your browser, ask for changes and download the final MP4.

Everything runs on your own Mac. Your videos never leave it.

## What you need

- An Apple silicon Mac (M1 or newer) with macOS 13 Ventura or newer.
- A Claude Pro (or Max) plan and the free Claude desktop app.
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

See [LICENSE](LICENSE).
