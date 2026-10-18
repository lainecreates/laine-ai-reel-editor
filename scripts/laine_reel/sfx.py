"""A small original sound-effect pack, synthesised with ffmpeg.

No downloads and no licensing questions: every sound is generated from maths
(sine sweeps, filtered noise, envelopes) into assets/sfx/generated/. A
customer's own files in assets/sfx/ (whoosh*.wav, pop*.mp3, ...) always win.
"""

from pathlib import Path

from . import config
from .tools import require, run

GENERATED = config.ASSETS_DIR / "sfx" / "generated"

# name -> (lavfi source, extra audio filters)
RECIPES = {
    # Airy rush: pink noise through a rising band, swelling then falling.
    "whoosh": ("anoisesrc=color=pink:amplitude=0.9:duration=0.55:sample_rate=48000",
               "highpass=f=350,lowpass=f=4200,bandpass=f=1600:width_type=h:w=2600,"
               "afade=t=in:st=0:d=0.30:curve=exp,afade=t=out:st=0.30:d=0.25:curve=qsin,"
               "aecho=0.6:0.4:22:0.25,volume=12"),
    # Bubbly pop: fast downward pitch blip with a quick decay.
    "pop": ("aevalsrc='0.9*sin(2*PI*t*(1150-3600*t))*exp(-34*t)':s=48000:d=0.16",
            "highpass=f=180,afade=t=out:st=0.12:d=0.04"),
    # Mouse click: a sharp press and a softer release ~45 ms later.
    "click": ("aevalsrc='(lt(t,0.005)*(random(0)*2-1)*exp(-t*700)"
              "+gte(t,0.045)*lt(t,0.05)*0.55*(random(1)*2-1)*exp(-(t-0.045)*700))*0.95'"
              ":s=48000:d=0.12",
              "highpass=f=1800,lowpass=f=9000,volume=3"),
    # Soft bell ding: fundamental + octave, gentle decay.
    "ding": ("aevalsrc='0.55*sin(2*PI*1318.5*t)*exp(-4.2*t)+0.25*sin(2*PI*2637*t)*exp(-7*t)"
             "+0.12*sin(2*PI*3955*t)*exp(-11*t)':s=48000:d=1.3",
             "afade=t=in:st=0:d=0.004,afade=t=out:st=1.1:d=0.2"),
}


def ensure_pack(force=False):
    """Create any missing generated sounds. Returns {name: path}."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, (src, filters) in RECIPES.items():
        path = GENERATED / f"{name}.wav"
        if force or not path.exists():
            run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", src, "-af", f"{filters},alimiter=limit=0.89,"
                 "aformat=sample_rates=48000:channel_layouts=stereo", path])
        out[name] = str(path)
    return out


def resolve(kind):
    """Customer's own file first (assets/sfx/<kind>*), else the generated one."""
    d = config.ASSETS_DIR / "sfx"
    for ext in (".wav", ".mp3", ".m4a", ".aiff", ".aif"):
        hits = sorted(p for p in d.glob(f"{kind}*{ext}") if p.is_file()) if d.is_dir() else []
        if hits:
            return str(hits[0])
    gen = GENERATED / f"{kind}.wav"
    if not gen.exists():
        ensure_pack()
    return str(gen) if gen.exists() else None
