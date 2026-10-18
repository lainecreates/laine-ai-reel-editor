"""Final render: one ffmpeg pass from the ORIGINAL footage.

    original -> cut (edl keep) -> reframe at 2x -> zooms (zoompan, toward the
    face) -> 1080x1920 -> overlay (transparent frames from Chrome) ->
    progress bar -> encode
    voice (click-free joins, -14 LUFS) + sound effects (+ ducked music) -> mix

Zooming happens on the 2x (2160x3840) frame before downscaling, so a 1.18x
punch-in is still full 1080p detail and slow pushes don't jitter. Uses only
filters present in this ffmpeg (no drawtext / subtitles).
"""

from pathlib import Path

from . import config
from .render import FADE, reframe_filter
from .tools import require, run

OUT_W, OUT_H = config.OUTPUT["width"], config.OUTPUT["height"]


def zoom_exprs(zooms, focus):
    """zoompan z / x / y expressions as a function of input time `it`."""
    if not zooms:
        return None
    z_terms, x_terms, y_terms = "1", None, None
    x_terms = "(iw-iw/zoom)/2"
    y_terms = "(ih-ih/zoom)/2"
    for z in reversed(zooms):
        a, b, s = z["start"], z["end"], z["scale"]
        if z["type"] == "push":
            p = f"clip((it-{a:.3f})/{max(0.05, b - a):.3f},0,1)"
            val = f"(1+{s - 1:.4f}*{p}*{p}*(3-2*{p}))"   # smoothstep ease
        else:
            val = f"{s:.4f}"
        f = focus.get(z["id"], {"x": 0.5, "y": 0.4})
        cond = f"between(it,{a:.3f},{b - 0.001:.3f})"
        z_terms = f"if({cond},{val},{z_terms})"
        x_terms = f"if({cond},(iw-iw/zoom)*{f['x']},{x_terms})"
        y_terms = f"if({cond},(ih-ih/zoom)*{f['y']},{y_terms})"
    return z_terms, x_terms, y_terms


def build_graph(keep, fps, frame, focus_x, zooms, focus, has_overlay, progress_color,
                duration, sfx_inputs, music_input, loudness=True):
    n = len(keep)
    L = [f"[0:v]fps={fps},split={n}" + "".join(f"[vs{i}]" for i in range(n)),
         f"[0:a]aresample=48000,asplit={n}" + "".join(f"[as{i}]" for i in range(n))]
    for i, (a, b) in enumerate(keep):
        d = b - a
        L.append(f"[vs{i}]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[v{i}]")
        L.append(f"[as{i}]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, d - FADE):.4f}:d={FADE}[a{i}]")
    L.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")

    ze = zoom_exprs(zooms, focus)
    if ze:
        z, x, y = ze
        L.append(f"[vc]{reframe_filter(frame, OUT_W * 2, OUT_H * 2, focus_x)},"
                 f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={OUT_W}x{OUT_H}:fps={fps},"
                 f"setsar=1[vz]")
    else:
        L.append(f"[vc]{reframe_filter(frame, OUT_W, OUT_H, focus_x)}[vz]")
    cur = "vz"
    if has_overlay:
        L.append(f"[1:v]fps={fps},format=rgba[ov]")
        L.append(f"[{cur}][ov]overlay=0:0:format=auto:eof_action=pass[vo]")
        cur = "vo"
    if progress_color:
        L.append(f"color=c={progress_color}:s={OUT_W}x12:r={fps}[pb]")
        L.append(f"[{cur}][pb]overlay=x='-w+w*t/{duration:.3f}':y=0:shortest=1[vp]")
        cur = "vp"
    L.append(f"[{cur}]format=yuv420p[vout]")

    voice = "[ac]aformat=channel_layouts=stereo"
    if loudness:
        voice += (f",loudnorm=I={config.OUTPUT['loudness_lufs']}:"
                  f"TP={config.OUTPUT['true_peak_db']}:LRA=11")
    voice += ",aresample=48000"
    mix_inputs = []
    if music_input is not None:
        L.append(voice + ",asplit=2[voice][vsc]")
        L.append(f"[{music_input['index']}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"volume={music_input['gain_db']}dB,atrim=0:{duration:.3f}[mraw]")
        L.append("[mraw][vsc]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=350[music]")
        mix_inputs += ["[voice]", "[music]"]
    else:
        L.append(voice + "[voice]")
        mix_inputs.append("[voice]")
    for k, s in enumerate(sfx_inputs):
        ms = int(round(s["at"] * 1000))
        L.append(f"[{s['index']}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"adelay={ms}:all=1,volume={s['gain_db']}dB[s{k}]")
        mix_inputs.append(f"[s{k}]")
    if len(mix_inputs) > 1:
        L.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:normalize=0:"
                 f"duration=first,alimiter=limit=0.95[aout]")
    else:
        L.append("[voice]anull[aout]")
    return ";\n".join(L)


def render_final(source, edl, edit, layout, overlay_concat, out_path, work_dir,
                 frame="cover", focus_x=0.5, preview=False, loudness=True,
                 progress_color=None):
    fps = edl.get("fps", config.OUTPUT["fps"])
    inputs = [["-i", str(source)]]
    if overlay_concat:
        inputs.append(["-f", "concat", "-safe", "0", "-i", str(overlay_concat)])
    idx = len(inputs)
    sfx_inputs = []
    for s in edit.get("sfx", []):
        if s.get("missing_custom"):
            continue   # never substitute a default for the customer's own sound
        if s.get("file"):
            inputs.append(["-i", s["file"]])
            # customer sounds are level-matched to the built-in pack, then the brand gain
            sfx_inputs.append({"index": idx, "at": s["at"],
                               "gain_db": s.get("gain_db", -18) + s.get("level_db", 0.0)})
            idx += 1
    music_input = None
    m = edit.get("music")
    if m and m.get("file"):
        inputs.append(["-stream_loop", "-1", "-i", m["file"]])
        music_input = {"index": idx, "gain_db": m.get("gain_db", -24)}
        idx += 1
    progress = None
    if any(g["type"] == "progress_bar" for g in edit.get("graphics", [])):
        progress = (progress_color or "#FFFFFF").replace("#", "0x")

    graph = build_graph(edl["keep"], fps, frame, focus_x, edit.get("zooms", []),
                        layout.get("zoom_focus", {}), bool(overlay_concat), progress,
                        edit["duration"], sfx_inputs, music_input, loudness)
    gfile = Path(work_dir) / "final-filtergraph.txt"
    gfile.write_text(graph)
    preset, crf = ("veryfast", "22") if preview else ("slow", "17")
    tmp = Path(out_path).with_suffix(".partial.mp4")
    cmd = [require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    for i in inputs:
        cmd += i
    cmd += ["-/filter_complex", gfile, "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-t", f"{edit['duration']:.3f}", tmp]
    run(cmd)
    tmp.replace(out_path)
    return out_path
