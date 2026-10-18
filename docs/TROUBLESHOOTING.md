# Troubleshooting

For anything not covered here, ask Claude in the Code tab: *"Check my reel editor setup"*.
It runs `python3 scripts/reel.py doctor` and explains what it finds.

## During installation

**"zsh: command not found: brew"**, or the installer says Homebrew isn't installed
: Homebrew didn't finish installing. Do step 6 of INSTALL.md again, and wait for
  "Installation successful!". Then run `~/laine-ai-reel-editor/install.sh`.

**"fatal: destination path ... already exists"**
: The editor is already downloaded. Just run `~/laine-ai-reel-editor/install.sh`.

**"xcrun: error" or "Command Line Tools are missing"**
: Run `xcode-select --install`, click **Install** in the window that appears, wait, then run the installer again.

**The speech model download stopped**
: Run `~/laine-ai-reel-editor/install.sh` again. It continues where it stopped and checks the file at the end.

**"This version needs an Apple silicon Mac"**
: Intel Macs aren't supported in this first version.

**"macOS 13 (Ventura) or newer is needed"**
: Update macOS in System Settings → General → Software Update.

**Homebrew couldn't install a tool**
: Check your internet connection and run the installer again. If it still fails, run `brew doctor` in Terminal and follow what it says, or send the message to support.

**Chrome didn't install**
: Download it from google.com/chrome, drag it to Applications, then run the installer again.

**"The test edit didn't finish"**
: The installer prints where the log is. Run `~/laine-ai-reel-editor/install.sh --check` to see which part is missing.

## While editing

**Claude says it can't find or read my video**
: Drag the video file straight into the chat. If macOS asks whether Claude can access Downloads or Desktop, click **OK**.

**The review page didn't open**
: Ask Claude: *"Open the review page for my reel"*. The address is http://127.0.0.1:8765/. It works only on your own Mac.

**"A brand font isn't installed: drawn in ... instead"**
: Upload the font's .ttf/.otf file in the 📁 Library tab, then choose it in Brand settings. Google Fonts are free to download.

**My captions don't look like my brand**
: If you haven't done onboarding, reels use the neutral look. Say **Start my brand onboarding**.
  If you changed your saved defaults after making the reel, the reel keeps its original look. In Brand settings, press **Use my current saved defaults for this reel**.

**It's slow**
: A one-minute reel usually takes a few minutes to render. Close other heavy apps. The first edit after installing is slower.

## Check-only mode

```bash
~/laine-ai-reel-editor/install.sh --check
```

This changes nothing. It lists what's installed and what's missing.
