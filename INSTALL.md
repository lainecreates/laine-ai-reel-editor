# Installing Laine AI Reel Editor

This guide assumes you've never used Terminal or Claude Code before. Take it one
step at a time. It takes about **30–40 minutes**, and most of that is waiting
for downloads.

> **Beta testers:** you need Laine's invitation (see LICENSE). The steps are the
> same for everyone.

**You need:**
- An Apple silicon Mac (M1 or newer) with macOS 13 Ventura or newer.
  - To check, open the Apple menu → **About This Mac**. "Chip" should say Apple M1, M2, M3 or later.
- About 4 GB of free space.
- Your Mac password (the one you use to log in).
- An internet connection.

---

## Part A: Claude (about 10 minutes)

1. **Create a Claude account.** Go to **claude.ai** and sign up, or log in if you already have one.
2. **Get Claude Pro.** On claude.ai, open your profile menu (bottom left) → **Upgrade** → choose **Pro**. The editor needs Pro or Max, because it uses Claude Code.
3. **Install the Claude app.** Go to **claude.ai/download** and download the Mac app.
   - Open the downloaded file and drag **Claude** into **Applications**.
   - Open Claude from Applications and sign in.
4. **Find the Code tab.** At the top of the Claude app you'll see **Chat** and **Code**. You'll use **Code** in Part C. Nothing to do yet.

---

## Part B: Install the editor (about 20–30 minutes)

### 5. Open Terminal

Press **⌘ Command + Space**, type **Terminal** and press **Return**. A window
with text appears. This is where you paste the two commands below.

> To paste: click in the Terminal window, press **⌘ Command + V**, then press **Return**.

### 6. Install Homebrew (skip this if you already have it)

Homebrew is a free, widely used installer for Mac tools.

- Go to **brew.sh**, copy the command under "Install Homebrew", paste it into Terminal and press **Return**. At the time of writing it's:

  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

- When it asks for your **Password**, type your Mac password and press **Return**.
  - **Nothing appears while you type.** That's normal; it's still listening.
- If it says "Press RETURN to continue", press **Return**.
- If a window asks to install **Command Line Tools**, click **Install**.
- Wait until it says **Installation successful!** This can take 5–15 minutes.
- At the end, Homebrew shows "Next steps" with a couple of commands. **You can skip them.** The editor's installer finds Homebrew by itself.

### 7. Download and set up the editor

Copy this whole line, paste it into Terminal and press **Return**:

```bash
git clone https://github.com/LaineCreates/laine-ai-reel-editor.git ~/laine-ai-reel-editor && ~/laine-ai-reel-editor/install.sh
```

This puts the editor in a folder called **laine-ai-reel-editor** in your home
folder, then starts the installer. The installer:

1. **Checks your Mac**: the chip, macOS version and free space.
2. **Lists the tools it needs** that you don't have yet: FFmpeg, whisper.cpp, Node.js 22 or newer, and Google Chrome if missing. (If you already have an older Node.js, it's left alone and a newer one is added.) It then asks:
   **"Install the missing tools listed above with Homebrew now? [Y/n]"**
   → Press **Return** for yes.
3. **Asks to download the speech model** (465 MB):
   → Press **Return** for yes.
4. **Sets up the folder and runs a short test edit** of a sample clip.
5. **Shows ✅ Ready.**

**If anything goes wrong or you close the window:** paste the same line from
step 7 again. If the folder already exists, use this instead:

```bash
~/laine-ai-reel-editor/install.sh
```

It carries on from where it stopped and never reinstalls what you already have.

You can close Terminal now. You won't need it again for normal use.

---

## Part C: First use (about 10 minutes)

8. **Open the editor in Claude.** Open the Claude app and click **Code**.
   - Choose the folder: click the folder picker, open your home folder (the one with the house icon) and select **laine-ai-reel-editor**.
   - If asked where to run, choose **Local**.
9. **Set up your brand.** Type:

   > **Start my brand onboarding**

   Claude asks about your colours, fonts, captions and style, one question at
   a time. You can stop and continue later. Until you finish, reels use a
   clean neutral look.
10. **Edit your first reel.** Type:

    > **Edit my reel**

    When Claude asks for the video, **drag the video file into the chat**.
    Claude cuts it, plans what goes on screen, picks a headline from your own
    words, and renders it. After a few minutes, a review page opens in your
    browser. Watch it, leave notes, press **Save feedback**, then tell Claude
    **apply my review**. When you're happy, press **Finalize & Download**.
    The full guide is **[docs/CUSTOMER-GUIDE.md](docs/CUSTOMER-GUIDE.md)**.

### What Claude may ask you to allow

- **"Allow Claude to run this command?"**: Claude Code asks before running editor commands. Click **Allow**. You can choose to allow a command for the whole session.
- **"Claude would like to access files in your Downloads (or Desktop) folder"**: click **OK**, so it can read the video you chose. Your original video is only read, never changed.

---

## Updating

In the Code tab, with the **laine-ai-reel-editor** folder open, type:

> **Update my reel editor**

Your brand, uploads and reels stay exactly as they are.

## Uninstalling

Delete the **laine-ai-reel-editor** folder from your home folder. This also
deletes your reels and brand inside it, so copy out any videos you want to keep first.

The tools Homebrew installed are shared with other apps, so they're left alone.
To remove them too, run `brew uninstall ffmpeg whisper-cpp node` in Terminal.

## Help

See **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**, or ask Claude in the
Code tab: *"Check my reel editor setup"*.
