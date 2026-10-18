"""Word-level transcription with whisper.cpp (whisper-cli)."""

import json
import os
import re
from pathlib import Path

from . import config
from .tools import ToolError, require, run

_NON_SPEECH = re.compile(r"^\s*[\[(].*[\])]\s*$")  # [BLANK_AUDIO], (music) ...
_SPECIAL = re.compile(r"^(\[_.*\]|<\|.*\|>)$")  # [_BEG_], [_TT_123], <|endoftext|>
_PUNCT = re.compile(r"^[^\w\s]+$")

# whisper.cpp's DTW word time lands ~0.3 s after the word really starts
# (closer to its middle). Measured with tests/sync_bench.py against speech with
# known word starts: small.en median +0.27 to +0.31 s, spread ~0.09 s. The
# correction removes the bias; align.refine_starts then finds each word's
# real onset in the audio.
DTW_LAG = {"default": 0.28}

# whisper.cpp DTW alignment presets (must match the model's architecture).
_DTW_PRESETS = {"tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
                "medium.en", "large.v1", "large.v2", "large.v3", "large.v3.turbo"}


def dtw_preset(model):
    """ggml-small.en-q5_0.bin -> "small.en"; None if not a known model."""
    name = re.sub(r"^ggml-|\.bin$", "", Path(model).name)
    name = re.sub(r"-q\d.*$", "", name).replace("large-v", "large.v").replace("-turbo", ".turbo")
    return name if name in _DTW_PRESETS else None


def transcribe(wav, model, out_prefix, language="en"):
    """Run whisper-cli and return {"words": [...], "text": ...}.

    -ojf writes token-level timestamps; tokens are joined into words. Raw
    whisper JSON is kept at <out_prefix>.json. Times are whisper's own and
    drift - pipeline.stage_align snaps them onto real speech.
    """
    out_prefix = Path(out_prefix)
    threads = max(1, min(8, (os.cpu_count() or 4)))
    cmd = [require("whisper-cli"), "-m", model, "-f", wav, "-l", language,
           "-t", threads, "-ojf", "-of", out_prefix, "-np",
           "--prompt", config.WHISPER_PROMPT]
    preset = dtw_preset(model)
    if preset:
        # DTW gives far better word starts; it needs flash attention off.
        cmd += ["-dtw", preset, "-nfa"]
    run(cmd)
    raw_path = out_prefix.with_suffix(".json")
    if not raw_path.exists():
        raise ToolError("whisper-cli produced no JSON output.")
    raw = json.loads(raw_path.read_text(encoding="utf-8", errors="replace"))
    words = parse_whisper_json(raw)
    if preset:
        lag = DTW_LAG.get(preset, DTW_LAG["default"])
        prev = 0.0
        for w in words:
            w["start"] = round(max(prev, w["start"] - lag), 3)
            w["end"] = round(max(w["start"] + 0.02, w["end"] - lag), 3)
            prev = w["start"]
    return {
        "engine": "whisper.cpp",
        "model": Path(model).name,
        "dtw": preset,
        "language": language,
        "words": words,
        "text": " ".join(w["text"] for w in words),
    }


def parse_whisper_json(raw):
    """Turn whisper-cli -ojf tokens into clean words.

    A token with a leading space starts a new word; other tokens continue it
    ("don" + "'t"). Punctuation is glued on but never extends the word's end
    time - whisper gives "." the whole pause that follows it.

    When DTW ran (t_dtw >= 0, in 10 ms units) it sets the word start, and a
    word ends no later than the next word starts.
    """
    words = []
    for seg in raw.get("transcription", []):
        if _NON_SPEECH.match(seg.get("text", "")):
            continue
        tokens = seg.get("tokens") or [{"text": seg.get("text", ""), "offsets": seg["offsets"]}]
        for tok in tokens:
            text = tok.get("text", "")
            if not text.strip() or _SPECIAL.match(text.strip()) or _NON_SPEECH.match(text):
                continue
            start = tok["offsets"]["from"] / 1000.0
            end = tok["offsets"]["to"] / 1000.0
            if tok.get("t_dtw", -1) >= 0:
                # DTW moves the start; keep whisper's token length.
                start, end = tok["t_dtw"] / 100.0, tok["t_dtw"] / 100.0 + (end - start)
            punct = _PUNCT.match(text.strip())
            if words and (punct or not text.startswith(" ")):
                words[-1]["text"] += text.strip()
                if not punct:
                    words[-1]["end"] = round(max(words[-1]["end"], end), 3)
                continue
            if punct:
                continue
            words.append({"text": text.strip(), "start": round(start, 3),
                          "end": round(max(end, start + 0.05), 3)})
    for w, nxt in zip(words, words[1:]):
        if nxt["start"] > w["start"]:
            w["end"] = round(max(w["start"] + 0.02, min(w["end"], nxt["start"])), 3)
    return words
