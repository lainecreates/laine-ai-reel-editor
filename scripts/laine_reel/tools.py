"""Locate and run the external tools: ffmpeg, ffprobe, whisper-cli.

Tools are used exactly as installed. Nothing here installs or changes them.
"""

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import config


class ToolError(RuntimeError):
    pass


def run(cmd, check=True):
    """Run a command, return CompletedProcess with text stdout/stderr."""
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise ToolError(f"{Path(str(cmd[0])).name} failed (exit {proc.returncode}):\n{tail}")
    return proc


NODE_MIN = 22      # captions are drawn with Node's built-in WebSocket (Node 22+)


def find_tool(name):
    """settings.json "tools": {"ffmpeg": "/path"} overrides PATH lookup.
    Node: the first one that is new enough (an older Node earlier on PATH is skipped)."""
    override = config.load_settings().get("tools", {}).get(name)
    if override:
        return override if Path(override).exists() else None
    if name == "node":
        seen = []
        for c in (shutil.which("node"), "/opt/homebrew/bin/node", "/usr/local/bin/node"):
            if c and c not in seen and Path(c).exists():
                seen.append(c)
                if (_version_major(c) or 0) >= NODE_MIN:
                    return c
        return seen[0] if seen else None
    return shutil.which(name)


def _version_major(node):
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def require(name):
    path = find_tool(name)
    if not path:
        raise ToolError(f"'{name}' not found. See DEPENDENCIES.md.")
    return path


@lru_cache(maxsize=None)
def ffmpeg_filters():
    out = run([require("ffmpeg"), "-hide_banner", "-filters"]).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and re.match(r"^[TSC.|]{2,3}$", parts[0]):
            names.add(parts[1])
    return names


@lru_cache(maxsize=None)
def ffmpeg_encoders():
    out = run([require("ffmpeg"), "-hide_banner", "-encoders"]).stdout
    return {p.split()[1] for p in out.splitlines() if len(p.split()) >= 2 and p.startswith(" ")}


def find_whisper_model(explicit=None):
    """Resolve a whisper.cpp model.

    Order: explicit path -> $LAINE_WHISPER_MODEL -> settings.json
    "whisper_model" -> models/ in this project (preferred names first).
    """
    candidates = [explicit, os.environ.get("LAINE_WHISPER_MODEL"),
                  config.load_settings().get("whisper_model")]
    for c in candidates:
        if c:
            p = Path(os.path.expanduser(c))
            if not p.is_absolute():
                p = config.PROJECT_ROOT / p
            if p.is_file():
                return p
    for name in config.MODEL_PREFERENCE:
        p = config.MODELS_DIR / name
        if p.is_file():
            return p
    found = sorted(config.MODELS_DIR.glob("ggml-*.bin"))
    return found[0] if found else None


def version_of(name):
    path = find_tool(name)
    if not path:
        return None
    if name == "whisper-cli":
        # whisper-cli has no --version; report the binary path.
        return path
    first = run([path, "-version"], check=False).stdout.splitlines()
    return first[0] if first else path


# filter -> (required in phase 1?, why)
FFMPEG_FILTERS = {
    "silencedetect": (True, "find pauses"),
    "volumedetect": (True, "adaptive silence threshold"),
    "trim": (True, "cut video"),
    "atrim": (True, "cut audio"),
    "concat": (True, "join kept segments"),
    "afade": (True, "click-free joins"),
    "split": (True, "fan out segments"),
    "asplit": (True, "fan out segments"),
    "scale": (True, "vertical reframe"),
    "crop": (True, "vertical reframe"),
    "fps": (True, "constant frame rate"),
    "loudnorm": (True, "-14 LUFS loudness"),
    "gblur": (False, "blurred-background framing"),
    "overlay": (False, "future: captions/graphics as image overlays"),
    "zoompan": (False, "future: punch-in zooms"),
    "amix": (False, "future: sound effects"),
    "adelay": (False, "future: sound effects"),
    "drawtext": (False, "not used - captions are rendered outside ffmpeg"),
    "subtitles": (False, "not used - captions are rendered outside ffmpeg"),
}


CHROME_PATHS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]


def find_chrome():
    """Same lookup as tools/render_overlay.mjs ($LAINE_CHROME first)."""
    for c in [os.environ.get("LAINE_CHROME")] + CHROME_PATHS:
        if c and Path(os.path.expanduser(c)).is_file():
            return str(Path(os.path.expanduser(c)))
    return None


def _node_major():
    node = find_tool("node")
    if not node:
        return None
    out = run([node, "--version"], check=False).stdout.strip().lstrip("v")
    try:
        return int(out.split(".")[0])
    except ValueError:
        return None


def _mac():
    """(macOS major version, chip) or (None, None) off macOS."""
    import platform
    if platform.system() != "Darwin":
        return None, None
    ver = platform.mac_ver()[0] or "0"
    return int(ver.split(".")[0]), platform.machine()


def doctor():
    """Return a list of (label, ok, detail, required)."""
    rows = []
    major, chip = _mac()
    if major is not None:
        rows.append(("macOS 13 or newer", major >= 13, f"macOS {major}", True))
        rows.append(("Apple silicon (M1 or newer)", chip == "arm64",
                     "arm64" if chip == "arm64" else f"{chip}: not supported yet", True))
    free_gb = shutil.disk_usage(str(config.PROJECT_ROOT)).free / 1e9
    rows.append(("free disk space", free_gb >= 5, f"{free_gb:.0f} GB free (5 GB or more recommended)",
                 False))
    for name, required in [("ffmpeg", True), ("ffprobe", True), ("whisper-cli", True),
                           ("python3", True)]:
        path = find_tool(name)
        rows.append((name, bool(path), version_of(name) if path else "missing", required))
    nm = _node_major()
    rows.append((f"node {NODE_MIN}+", bool(nm and nm >= NODE_MIN),
                 f"v{nm}" if nm else "missing - draws captions and graphics", True))
    chrome = find_chrome()
    rows.append(("Google Chrome", bool(chrome), chrome or "missing - draws captions and graphics",
                 True))

    model = find_whisper_model()
    small = bool(model) and model.stat().st_size < 50_000_000
    rows.append(("whisper model", bool(model) and not small,
                 (str(model) + (" (too small: incomplete download?)" if small else "")) if model else
                 "none - run ./install.sh to download it into models/",
                 True))

    if find_tool("ffmpeg"):
        filters = ffmpeg_filters()
        for f, (required, why) in FFMPEG_FILTERS.items():
            rows.append((f"ffmpeg filter {f}", f in filters, why, required))
        encoders = ffmpeg_encoders()
        for e in ("libx264", "aac"):
            rows.append((f"ffmpeg encoder {e}", e in encoders, "final MP4", True))
    return rows
