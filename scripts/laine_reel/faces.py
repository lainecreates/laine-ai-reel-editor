"""Where is the speaker's face, over time, on the OUTPUT timeline?

Samples the clean vertical MP4 a few times per second and detects faces with
Apple's Vision framework through JavaScript for Automation
(tools/faces.js; built into macOS, nothing to install). On other systems, or
if detection fails, it falls back to the typical talking-head position and
marks the track as estimated, so placement still works.

faces.json: {"source": "vision"|"estimate", "fps": 2,
             "samples": [{"t": 0.0, "box": [x, y, w, h] | null}, ...]}
Boxes are normalised 0..1 on the 1080x1920 frame, origin top-left.
"""

import json
import platform
import shutil
import tempfile
from pathlib import Path

from . import config
from .tools import require, run

SAMPLE_FPS = 2
TYPICAL_FACE = [0.30, 0.30, 0.40, 0.24]  # centred, upper-middle: a typical selfie framing


def detect(video, duration):
    """Face track for a rendered (output-timeline) video."""
    script = config.PROJECT_ROOT / "tools" / "faces.js"
    if platform.system() == "Darwin" and shutil.which("osascript") and script.exists():
        tmp = Path(tempfile.mkdtemp(prefix="laine-faces-"))
        try:
            run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", video,
                 "-vf", f"fps={SAMPLE_FPS},scale=540:960", "-q:v", "3",
                 tmp / "frame_%05d.jpg"])
            out = run(["osascript", "-l", "JavaScript", script, tmp]).stdout
            boxes = json.loads(out)
            samples = []
            for name in sorted(boxes):
                n = int(name.split("_")[1].split(".")[0]) - 1
                faces = boxes[name]
                # The speaker = the biggest face in frame.
                box = max(faces, key=lambda b: b[2] * b[3]) if faces else None
                samples.append({"t": round(n / SAMPLE_FPS, 3), "box": box})
            if any(s["box"] for s in samples):
                return {"source": "vision", "fps": SAMPLE_FPS, "samples": fill_gaps(samples)}
        except Exception:  # noqa: BLE001 - fall back to the estimate below
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    n = int(duration * SAMPLE_FPS) + 1
    return {"source": "estimate", "fps": SAMPLE_FPS,
            "samples": [{"t": round(i / SAMPLE_FPS, 3), "box": list(TYPICAL_FACE)}
                        for i in range(n)]}


def fill_gaps(samples):
    """Frames where the face wasn't found (turned away, hand in front) take
    the nearest detected box."""
    known = [s for s in samples if s["box"]]
    for s in samples:
        if not s["box"]:
            s["box"] = min(known, key=lambda k: abs(k["t"] - s["t"]))["box"]
            s["filled"] = True
    return samples


def box_between(track, start, end):
    """Union of face boxes between two times (where the face could be)."""
    boxes = [s["box"] for s in track["samples"] if start - 0.5 <= s["t"] <= end + 0.5]
    if not boxes:
        boxes = [s["box"] for s in track["samples"]] or [TYPICAL_FACE]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def median_box(track):
    boxes = sorted((s["box"] for s in track["samples"]), key=lambda b: b[0] + b[2] / 2)
    return boxes[len(boxes) // 2] if boxes else TYPICAL_FACE
