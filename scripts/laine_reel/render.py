"""Render the cut list to a clean vertical MP4 with ffmpeg.

Uses only core filters (trim/atrim/concat/scale/crop/fps/loudnorm). No
drawtext or subtitles: those are missing from many ffmpeg builds, so future
text layers are rendered to transparent images and composited with `overlay`
(see docs/ARCHITECTURE.md).
"""

from pathlib import Path

from . import config
from .tools import require, run

FADE = 0.008  # 8 ms audio fade at every join: removes clicks, inaudible


def reframe_filter(mode, width, height, focus_x=0.5):
    """Filter chain that turns any frame into width x height (9:16)."""
    fx = min(1.0, max(0.0, focus_x))
    if mode == "cover":
        return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-{width})*{fx}:(ih-{height})/2,setsar=1")
    if mode == "blur":
        # Whole frame visible, centred on a blurred, zoomed copy of itself.
        return (f"split[bgsrc][fgsrc];"
                f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=40[bg];"
                f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    raise ValueError(f"Unknown frame mode: {mode}")


def build_filtergraph(keep, frame="cover", focus_x=0.5, loudness=True,
                      width=config.OUTPUT["width"], height=config.OUTPUT["height"],
                      fps=config.OUTPUT["fps"]):
    n = len(keep)
    if n == 0:
        raise ValueError("Nothing to render: every second was cut.")
    lines = [f"[0:v]fps={fps},split={n}" + "".join(f"[vs{i}]" for i in range(n)),
             f"[0:a]aresample=48000,asplit={n}" + "".join(f"[as{i}]" for i in range(n))]
    for i, (a, b) in enumerate(keep):
        d = b - a
        lines.append(f"[vs{i}]trim=start={a:.4f}:end={b:.4f},setpts=PTS-STARTPTS[v{i}]")
        lines.append(f"[as{i}]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, d - FADE):.4f}:d={FADE}[a{i}]")
    lines.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    lines.append(f"[vc]{reframe_filter(frame, width, height, focus_x)},format=yuv420p[vout]")
    audio = "[ac]"
    if loudness:
        audio += (f"loudnorm=I={config.OUTPUT['loudness_lufs']}:"
                  f"TP={config.OUTPUT['true_peak_db']}:LRA=11,aresample=48000")
    else:
        audio += "anull"
    lines.append(audio + "[aout]")
    return ";\n".join(lines)


def render(source, keep, out_path, work_dir, frame="cover", focus_x=0.5,
           loudness=True, preview=False, fps=config.OUTPUT["fps"]):
    """Encode the cut. Writes the filtergraph next to the output for debugging."""
    graph = build_filtergraph(keep, frame=frame, focus_x=focus_x, loudness=loudness, fps=fps)
    graph_file = Path(work_dir) / "filtergraph.txt"
    graph_file.write_text(graph)
    preset, crf = ("veryfast", "23") if preview else ("medium", "18")
    tmp = Path(out_path).with_suffix(".partial.mp4")
    run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", source,
         "-/filter_complex", graph_file,
         "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", tmp])
    tmp.replace(out_path)
    return out_path
