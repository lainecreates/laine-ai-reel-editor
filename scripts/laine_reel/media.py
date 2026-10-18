"""Probing, audio extraction and silence detection with ffmpeg/ffprobe."""

import json
import re
from fractions import Fraction

from . import config
from .tools import ToolError, require, run


def probe(path):
    """Duration, display size (rotation applied), fps and stream info."""
    out = run([require("ffprobe"), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path]).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ToolError(f"No video stream in {path}")

    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(round(float(sd["rotation"])))
    if "rotate" in video.get("tags", {}):
        rotation = int(video["tags"]["rotate"])
    width, height = int(video["width"]), int(video["height"])
    if abs(rotation) % 180 == 90:
        width, height = height, width

    fps = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            f = Fraction(video.get(key, "0/1"))
            if f > 0:
                fps = float(f)
                break
        except (ValueError, ZeroDivisionError):
            continue

    return {
        "duration": float(data["format"].get("duration") or video.get("duration") or 0),
        "width": width,
        "height": height,
        "rotation": rotation,
        "fps": round(fps, 3),
        "video_codec": video.get("codec_name"),
        "has_audio": audio is not None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "sample_rate": int(audio["sample_rate"]) if audio else None,
    }


def duration(path):
    out = run([require("ffprobe"), "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path]).stdout.strip()
    return float(out or 0)


def extract_audio(src, dst):
    """16 kHz mono PCM: what whisper.cpp expects, also used for silence detection."""
    run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", src,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst])


def mean_volume(wav):
    err = run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", wav,
               "-af", "volumedetect", "-f", "null", "-"]).stderr
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", err)
    if not m or m.group(1) == "-inf":
        raise ToolError("Audio is completely silent.")
    return float(m.group(1))


def silence_threshold(mean_db):
    t = mean_db - config.SILENCE_BELOW_MEAN_DB
    return round(max(config.SILENCE_FLOOR_DB, min(config.SILENCE_CEIL_DB, t)), 1)


def detect_silences(wav, noise_db, min_dur=config.SILENCE_MIN_DETECT, duration=None):
    """List of {"start", "end"} silent ranges (seconds)."""
    err = run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", wav, "-af",
               f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"]).stderr
    silences, start = [], None
    for line in err.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and start is not None:
            silences.append({"start": round(start, 3), "end": round(float(m.group(1)), 3)})
            start = None
    if start is not None and duration:
        silences.append({"start": round(start, 3), "end": round(duration, 3)})
    return silences
