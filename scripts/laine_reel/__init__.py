"""Laine AI Reel Editor - talking-head reel pipeline.

Phase 1: ingest -> transcribe (whisper.cpp) -> detect silence (ffmpeg)
-> plan pause cuts -> render clean vertical MP4 -> remap transcript.

Python standard library only. External tools: ffmpeg, ffprobe, whisper-cli.
"""

__version__ = "0.1.0"
