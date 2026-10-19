#!/bin/bash
# Laine AI Reel Editor - installer for macOS (Apple silicon).
#
#   ./install.sh            check this Mac, install what's missing (asks first)
#   ./install.sh --check    only check; change nothing (used for updates)
#   ./install.sh --dry-run  show what would be installed or downloaded; change nothing
#
# Safe to run again: it skips anything already in place and never removes
# or reinstalls tools you already have. Everything it creates stays inside
# this folder, except the tools Homebrew installs (only after you say yes).

set -u
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

MODE="install"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --dry-run) MODE="dry-run" ;;
    --skip-selfcheck) SKIP_SELFCHECK=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $a (try --help)"; exit 2 ;;
  esac
done
[ "${LAINE_INSTALL_DRY_RUN:-}" = "1" ] && MODE="dry-run"

MODEL_NAME="ggml-small.en.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
MODEL_SHA256="c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
MODEL_MB=465

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
miss() { printf '  \033[33m•\033[0m %s\n' "$*"; }
fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*"; }

# ask "question" -> 0 for yes. LAINE_INSTALL_ANSWER=y|n answers for tests.
ask() {
  if [ -n "${LAINE_INSTALL_ANSWER:-}" ]; then
    echo "$1 [Y/n] ${LAINE_INSTALL_ANSWER} (automatic)"
    [ "${LAINE_INSTALL_ANSWER}" = "y" ]; return
  fi
  local reply
  printf '%s [Y/n] ' "$1"
  read -r reply </dev/tty || reply="n"
  case "$reply" in ""|y|Y|yes|Yes|YES) return 0 ;; *) return 1 ;; esac
}

# For testing the "missing" paths on a Mac that has everything: only in dry-run
# mode, LAINE_INSTALL_PRETEND_MISSING="brew ffmpeg whisper-cli node chrome model"
# makes the installer act as if those were missing. Nothing is removed.
pretend() { [ "$MODE" = "dry-run" ] && [[ " ${LAINE_INSTALL_PRETEND_MISSING:-} " == *" $1 "* ]]; }
have() { ! pretend "$1" && command -v "$1" >/dev/null 2>&1; }

# run a command that changes something - or just show it in dry-run mode
act() {
  if [ "$MODE" = "dry-run" ]; then echo "    [dry run] would run: $*"; return 0; fi
  "$@"
}

echo
bold "Laine AI Reel Editor - setup ($MODE)"
echo "Folder: $ROOT"
echo

# -- 1. this Mac -----------------------------------------------------------------
bold "1. Checking this Mac"
if [ "$(uname -s)" != "Darwin" ]; then
  fail "This editor needs a Mac. Windows support is planned for later."; exit 1
fi
if [ "$(uname -m)" != "arm64" ]; then
  fail "This version needs an Apple silicon Mac (M1 or newer). Apple menu > About This Mac shows your chip."; exit 1
fi
MACOS_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
if [ "$MACOS_MAJOR" -lt 13 ]; then
  fail "macOS 13 (Ventura) or newer is needed; this Mac has $(sw_vers -productVersion). Update in System Settings > General > Software Update."; exit 1
fi
ok "macOS $(sw_vers -productVersion) on Apple silicon"
FREE_GB=$(df -g "$ROOT" | awk 'NR==2 {print $4}')
if [ "${FREE_GB:-0}" -lt 5 ]; then
  miss "Only ${FREE_GB} GB free. About 4 GB is needed for setup, plus room for your reels."
else
  ok "${FREE_GB} GB free disk space"
fi

# -- 2. Homebrew, git and python3 --------------------------------------------------
BREW="$(command -v brew || true)"
[ -z "$BREW" ] && [ -x /opt/homebrew/bin/brew ] && BREW=/opt/homebrew/bin/brew
pretend brew && BREW=""
if [ -z "$BREW" ]; then
  fail "Homebrew isn't installed yet."
  echo "Install it first: open https://brew.sh, copy the command shown there, paste it"
  echo "into Terminal and press Return. Then run this installer again:"
  echo
  echo "    $ROOT/install.sh"
  exit 1
fi
eval "$("$BREW" shellenv)"     # puts Homebrew's tools on PATH for this run
ok "Homebrew ($BREW)"
if ! /usr/bin/xcrun --find python3 >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  fail "Apple's Command Line Tools (python3, git) are missing."
  echo "Run this, click Install in the window that appears, then run the installer again:"
  echo "    xcode-select --install"
  exit 1
fi
ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"

# -- 3. tools ----------------------------------------------------------------------
echo
bold "2. Checking the editing tools"
FORMULAS=()
if have ffmpeg && have ffprobe; then ok "FFmpeg"; else miss "FFmpeg (video and audio) - about 150 MB"; FORMULAS+=(ffmpeg); fi
if have whisper-cli; then ok "whisper.cpp"; else miss "whisper.cpp (speech to text) - about 10 MB"; FORMULAS+=(whisper-cpp); fi
NODE_MAJOR=""; have node && NODE_MAJOR="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"
# Node 22+ (the editor uses Node's built-in WebSocket). An older Node elsewhere on this Mac is
# left alone; Homebrew's Node is used when it's new enough.
BREW_NODE_MAJOR=""; [ -x "$($BREW --prefix)/bin/node" ] && BREW_NODE_MAJOR="$("$($BREW --prefix)/bin/node" --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"
pretend node && BREW_NODE_MAJOR=""
NODE_UPGRADE=0
if [ -n "$NODE_MAJOR" ] && [ "$NODE_MAJOR" -ge 22 ]; then ok "Node.js v$NODE_MAJOR"
elif [ -n "$BREW_NODE_MAJOR" ] && [ "$BREW_NODE_MAJOR" -ge 22 ]; then ok "Node.js v$BREW_NODE_MAJOR (Homebrew)"
elif [ -n "$BREW_NODE_MAJOR" ]; then miss "Node.js v$BREW_NODE_MAJOR is too old: version 22 or newer is needed (Homebrew will update it)"; NODE_UPGRADE=1
else
  [ -n "$NODE_MAJOR" ] && miss "Node.js v$NODE_MAJOR is too old: version 22 or newer is needed - about 100 MB" \
                       || miss "Node.js 22 or newer (draws captions) - about 100 MB"
  FORMULAS+=(node)
fi
CHROME=""
for c in "${LAINE_CHROME:-}" "/Applications/Google Chrome.app" "$HOME/Applications/Google Chrome.app"; do
  [ -n "$c" ] && [ -e "$c" ] && CHROME="$c" && break
done
pretend chrome && CHROME=""
if [ -n "$CHROME" ]; then ok "Google Chrome"; else miss "Google Chrome (draws captions, invisibly) - about 600 MB"; fi

NEED_TOOLS=0
[ ${#FORMULAS[@]} -gt 0 ] || [ -z "$CHROME" ] || [ "$NODE_UPGRADE" = "1" ] && NEED_TOOLS=1
if [ "$NEED_TOOLS" = "1" ]; then
  if [ "$MODE" = "check" ]; then
    miss "Run ./install.sh to install the missing tools."
  elif ask "Install the missing tools listed above with Homebrew now?"; then
    if [ ${#FORMULAS[@]} -gt 0 ]; then act "$BREW" install "${FORMULAS[@]}" || { fail "Homebrew couldn't install ${FORMULAS[*]}. Check your internet connection, then run ./install.sh again."; exit 1; }; fi
    if [ "$NODE_UPGRADE" = "1" ]; then act "$BREW" upgrade node || { fail "Homebrew couldn't update Node.js. Check your internet connection, then run ./install.sh again."; exit 1; }; fi
    if [ -z "$CHROME" ]; then act "$BREW" install --cask google-chrome || { fail "Chrome didn't install. You can download it from google.com/chrome instead, then run ./install.sh again."; exit 1; }; fi
  else
    fail "Setup stopped: the editor needs these tools. Run ./install.sh again when you're ready."; exit 1
  fi
fi

# -- 4. speech model ----------------------------------------------------------------
echo
bold "3. Speech model"
MODEL_OK="$(python3 - <<'EOF'
import json, subprocess, sys
rows = json.loads(subprocess.run([sys.executable, "scripts/reel.py", "doctor", "--json"],
                                 capture_output=True, text=True).stdout or "[]")
print(next((r["detail"] for r in rows if r["label"] == "whisper model" and r["ok"]), ""))
EOF
)"
pretend model && MODEL_OK=""
if [ -n "$MODEL_OK" ]; then
  ok "Found: $MODEL_OK"
elif [ "$MODE" = "check" ]; then
  miss "No speech model yet. Run ./install.sh to download it."
elif ask "Download the speech model ($MODEL_NAME, $MODEL_MB MB) into this folder now?"; then
  mkdir -p models
  act curl -L --fail --retry 3 -C - -o "models/$MODEL_NAME.part" "$MODEL_URL" || { fail "The download stopped. Run ./install.sh again to continue where it left off."; exit 1; }
  if [ "$MODE" != "dry-run" ]; then
    echo "  checking the download..."
    GOT="$(shasum -a 256 "models/$MODEL_NAME.part" | cut -d' ' -f1)"
    if [ "$GOT" != "$MODEL_SHA256" ]; then
      rm -f "models/$MODEL_NAME.part"
      fail "The downloaded model was damaged and has been removed. Run ./install.sh again."; exit 1
    fi
    mv "models/$MODEL_NAME.part" "models/$MODEL_NAME"
    ok "Speech model downloaded and checked"
  fi
else
  fail "Setup stopped: the editor needs the speech model. Run ./install.sh again when you're ready."; exit 1
fi

# -- 5. this folder ------------------------------------------------------------------
echo
bold "4. Setting up the editor folder"
if [ -f config/settings.json ]; then
  ok "config/settings.json (kept as it is)"
elif [ "$MODE" = "check" ]; then
  miss "config/settings.json not created yet"
else
  act cp config/settings.example.json config/settings.json && [ "$MODE" = "install" ] && ok "config/settings.json created"
fi
if [ "$MODE" = "install" ]; then
  python3 -c "import sys; sys.path.insert(0, 'scripts'); from laine_reel import sfx; sfx.ensure_pack()" \
    && ok "Sound effects ready" || miss "Sound effects will be made on first use"
fi
if [ -f brand/brand.json ]; then ok "Your brand profile (kept as it is)"; else ok "Neutral look ready (until you do brand onboarding)"; fi

# -- 6. final check -------------------------------------------------------------------
echo
bold "5. Final check"
if [ "$MODE" = "dry-run" ]; then
  echo "    [dry run] would run: python3 scripts/reel.py doctor, then a short test edit"
  echo; bold "Dry run finished. Nothing was changed."; exit 0
fi
if ! python3 scripts/reel.py doctor >/tmp/laine-doctor.$$ 2>&1; then
  grep -E "MISS" /tmp/laine-doctor.$$; rm -f /tmp/laine-doctor.$$
  fail "Something is still missing (listed above). Run ./install.sh again, or see docs/TROUBLESHOOTING.md."
  exit 1
fi
rm -f /tmp/laine-doctor.$$
ok "All tools found"
if [ "$MODE" = "install" ] && [ -z "${SKIP_SELFCHECK:-}" ]; then
  echo "  test edit on a short sample clip (about 30 seconds)..."
  T="$(mktemp -d -t laine-install-check)"
  if say -o "$T/voice.aiff" "Hello. This is a quick test of the reel editor. Everything works." \
     && ffmpeg -loglevel error -y -f lavfi -i color=c=0x808080:s=720x1280:r=30 -i "$T/voice.aiff" \
          -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac "$T/sample.mp4" \
     && LAINE_REELS_WORKSPACE="$T/work" python3 scripts/reel.py run "$T/sample.mp4" --name install-check >"$T/log" 2>&1 \
     && ls "$T"/work/*/output/*-vertical.mp4 >/dev/null 2>&1 \
     && python3 -c "import glob, json, sys; w = json.load(open(glob.glob(sys.argv[1])[0]))['words']; sys.exit(len(w) < 5)" "$T/work/*/transcript.json"; then
    ok "Test edit worked"
    rm -rf "$T"
  else
    tail -5 "$T/log" 2>/dev/null
    fail "The test edit didn't finish. The details are in $T/log - see docs/TROUBLESHOOTING.md."
    exit 1
  fi
fi

echo
if [ "$MODE" = "check" ]; then bold "Check finished."; else bold "✅ Ready."; fi
echo
echo "Next: open the Claude app, click the Code tab, choose this folder"
echo "($ROOT) and type:  Start my brand onboarding"
echo
