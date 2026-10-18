"""Paths, pacing presets and output defaults."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("LAINE_REELS_WORKSPACE", PROJECT_ROOT / "workspace"))
MODELS_DIR = PROJECT_ROOT / "models"
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"
ASSETS_DIR = PROJECT_ROOT / "assets"


def brand_dir():
    """Where this project's brand profile lives ($LAINE_BRAND_DIR for tests)."""
    return Path(os.environ.get("LAINE_BRAND_DIR", PROJECT_ROOT / "brand"))

# Preferred whisper.cpp models, best first. Looked up in models/ when no
# explicit path is configured.
MODEL_PREFERENCE = [
    "ggml-small.en.bin",
    "ggml-base.en.bin",
    "ggml-medium.en.bin",
    "ggml-small.bin",
    "ggml-base.bin",
    "ggml-tiny.en.bin",
]


@dataclass(frozen=True)
class Pacing:
    """How hard to tighten pauses.

    min_pause:  pauses shorter than this are left alone (natural rhythm).
    keep_pause: how much of a long pause survives the cut.
    lead_in:    silence kept before the first word.
    tail:       silence kept after the last word.
    """

    name: str
    min_pause: float
    keep_pause: float
    lead_in: float
    tail: float

    def to_dict(self):
        return asdict(self)


PACING = {
    "natural": Pacing("natural", min_pause=0.45, keep_pause=0.30, lead_in=0.15, tail=0.35),
    "tight": Pacing("tight", min_pause=0.30, keep_pause=0.20, lead_in=0.10, tail=0.25),
    "fast": Pacing("fast", min_pause=0.22, keep_pause=0.12, lead_in=0.06, tail=0.20),
}
DEFAULT_PACING = "natural"

OUTPUT = {
    "width": 1080,
    "height": 1920,
    "fps": 30,  # fallback only; output follows the source rate (output_fps)
    "loudness_lufs": -14.0,  # Instagram / TikTok / Shorts target
    "true_peak_db": -1.5,
}

# Output frame rates the editor snaps to. Keeping the source rate avoids the
# judder that 24 -> 30 fps conversion causes.
STANDARD_FPS = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60]


def output_fps(source_fps):
    """Nearest standard rate to the source, capped at 60. Returns an ffmpeg
    rate string ("24", "30000/1001") and its float value."""
    if not source_fps or source_fps <= 0:
        return str(OUTPUT["fps"]), float(OUTPUT["fps"])
    best = min(STANDARD_FPS, key=lambda r: abs(r - min(source_fps, 60)))
    exact = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001"}
    if best in exact:
        num, den = map(int, exact[best].split("/"))
        return exact[best], num / den
    return str(int(best)), float(best)


# Silence detection: threshold is derived from the clip's mean loudness and
# clamped to this range (dBFS).
SILENCE_FLOOR_DB = -50.0
SILENCE_CEIL_DB = -28.0
SILENCE_BELOW_MEAN_DB = 14.0
SILENCE_MIN_DETECT = 0.15  # shortest silence ffmpeg reports (s)
GAP_MIN_DETECT = 0.03  # shortest gap between words a content cut may use (s)

# Primes whisper to write speech verbatim (keeps "um", "I- I", cut-offs like
# "real-") instead of tidying it, so repeats and restarts can be found.
WHISPER_PROMPT = "Umm, so, uh, I- I was like, hmm. Okay, so, um, the the thing is, uh, you know."

FILLER_WORDS = {"um", "uh", "erm", "er", "ah", "hmm", "mm", "uhm", "umm"}


def load_settings():
    """Local, per-machine settings (config/settings.json, git-ignored)."""
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {}


def load_brand():
    """The customer's brand profile (brand/brand.json), or {} before onboarding."""
    f = brand_dir() / "brand.json"
    return json.loads(f.read_text()) if f.exists() else {}


def check_not_protected(path):
    """Refuse paths listed in settings.json "protected_paths" (e.g. another
    editor's workspace on this machine). Raises ValueError."""
    p = Path(os.path.expanduser(str(path))).resolve()
    for root in load_settings().get("protected_paths", []):
        r = Path(os.path.expanduser(root)).resolve()
        if p == r or r in p.parents:
            raise ValueError(f"{p} is inside a protected folder ({root}); "
                             "copy the file somewhere else first.")
    return p
