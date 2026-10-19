"""The customer's own asset library: fonts, sounds and images.

    assets/library/
        library.json          index: one entry per asset
        fonts/   *.ttf *.otf
        sounds/  *.mp3 *.wav
        images/  *.png *.jpg

Every upload is checked by content (magic bytes), size, and by actually
reading it (ffprobe for sounds and images, font table header for fonts), so a
renamed file can't sneak in. Assets are never deleted by the editor; "remove"
archives them (hidden, kept on disk).
"""

import datetime as _dt
import json
import os
import re
import struct
import uuid
from pathlib import Path

from . import config
from .tools import require, run

KINDS = {
    "font": {"dir": "fonts", "ext": (".ttf", ".otf"), "max_mb": 15},
    "sound": {"dir": "sounds", "ext": (".mp3", ".wav"), "max_mb": 40},
    "image": {"dir": "images", "ext": (".png", ".jpg", ".jpeg", ".heic", ".heif"), "max_mb": 25},
}
IMAGE_CATEGORIES = ["logo", "screenshot", "graphic", "photo"]
SOUND_CATEGORIES = ["whoosh", "pop", "click", "ding", "transition", "music", "other"]


class LibraryError(ValueError):
    pass


def library_dir():
    return Path(os.environ.get("LAINE_LIBRARY_DIR", config.ASSETS_DIR / "library"))


def _index_path():
    return library_dir() / "library.json"


def load():
    p = _index_path()
    return json.loads(p.read_text()) if p.exists() else {"assets": []}


def _save(idx):
    d = library_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(_index_path())


def items(kind=None, include_archived=False):
    out = []
    for a in load()["assets"]:
        if kind and a["kind"] != kind:
            continue
        if a.get("archived") and not include_archived:
            continue
        out.append(dict(a, path=str(library_dir() / a["file"])))
    return out


def get(asset_id):
    for a in load()["assets"]:
        if a["id"] == asset_id:
            return dict(a, path=str(library_dir() / a["file"]))
    return None


def path_of(asset_id):
    a = get(asset_id)
    if not a:
        return None
    p = Path(a["path"])
    return p if p.is_file() else None


def exif_orientation(path):
    """EXIF orientation of a JPEG (1 = upright). Phones save portrait photos
    sideways with 6 or 8 here; browsers show them upright."""
    import struct
    try:
        data = Path(path).read_bytes()[:131072]
    except OSError:
        return 1
    if data[:2] != b"\xff\xd8":
        return 1
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker, size = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            t = data[i + 10:i + 2 + size]
            end = "<" if t[:2] == b"II" else ">"
            try:
                ifd = struct.unpack(end + "I", t[4:8])[0]
                for k in range(struct.unpack(end + "H", t[ifd:ifd + 2])[0]):
                    e = ifd + 2 + 12 * k
                    if struct.unpack(end + "H", t[e:e + 2])[0] == 0x0112:
                        return struct.unpack(end + "H", t[e + 8:e + 10])[0]
            except struct.error:
                return 1
            return 1
        if marker in (0xDA, 0xD9):
            break
        i += 2 + size
    return 1


def display_size(asset):
    """(width, height) of an image as people see it (EXIF rotation applied)."""
    w, h = asset.get("width") or 4, asset.get("height") or 5
    if asset.get("path") and exif_orientation(asset["path"]) in (5, 6, 7, 8):
        w, h = h, w
    return w, h


# -- checking uploads -----------------------------------------------------------

def _kind_for(name):
    ext = Path(name).suffix.lower()
    for k, spec in KINDS.items():
        if ext in spec["ext"]:
            return k
    raise LibraryError(f"{Path(name).suffix or 'that file'} isn't supported. Use TTF/OTF fonts, "
                       "MP3/WAV sounds, or PNG/JPG/HEIC images.")


def _font_family(data):
    """Read the font's family name from its 'name' table (no libraries)."""
    try:
        num = struct.unpack(">H", data[4:6])[0]
        for i in range(num):
            tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            if tag != b"name":
                continue
            fmt, count, strings = struct.unpack(">HHH", data[off:off + 6])
            best = {}
            for j in range(count):
                pid, eid, lid, nid, ln, so = struct.unpack(
                    ">HHHHHH", data[off + 6 + 12 * j:off + 18 + 12 * j])
                if nid not in (1, 16):
                    continue
                raw = data[off + strings + so:off + strings + so + ln]
                text = raw.decode("utf-16-be", "ignore") if pid in (0, 3) else \
                    raw.decode("latin-1", "ignore")
                if text.strip():
                    best.setdefault(nid, text.strip())
            return best.get(16) or best.get(1)
    except (struct.error, IndexError):
        return None
    return None


def check(kind, name, data):
    """Validate an upload. Returns details (family, duration, size...)."""
    spec = KINDS[kind]
    if len(data) == 0:
        raise LibraryError("The file is empty.")
    if len(data) > spec["max_mb"] * 1024 * 1024:
        raise LibraryError(f"That file is over {spec['max_mb']} MB.")
    head = data[:12]
    if kind == "font":
        if head[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise LibraryError("That isn't a TTF/OTF font file.")
        fam = _font_family(data)
        if not fam:
            raise LibraryError("Couldn't read the font's name; the file may be damaged.")
        return {"family": fam}
    if kind == "sound":
        ok = head[:4] == b"RIFF" and data[8:12] == b"WAVE" or head[:3] == b"ID3" or \
            (head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
        if not ok:
            raise LibraryError("That isn't an MP3 or WAV sound file.")
    if kind == "image":
        png = head[:8] == b"\x89PNG\r\n\x1a\n"
        jpg = head[:3] == b"\xff\xd8\xff"
        if not (png or jpg):
            raise LibraryError("That isn't a PNG or JPG image.")
    return {}


def _probe(path, kind):
    out = run([require("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams",
               "-show_format", path], check=False)
    if out.returncode != 0:
        raise LibraryError("The file couldn't be read; it may be damaged.")
    d = json.loads(out.stdout)
    s = (d.get("streams") or [{}])[0]
    if kind == "sound":
        dur = float(d.get("format", {}).get("duration") or 0)
        if s.get("codec_type") != "audio" or dur <= 0:
            raise LibraryError("No sound found in that file.")
        if dur > 600:
            raise LibraryError("Sounds can be at most 10 minutes long.")
        return {"duration": round(dur, 3), "peak_db": peak_db(path)}
    if kind == "image":
        w, h = int(s.get("width") or 0), int(s.get("height") or 0)
        if not (w and h):
            raise LibraryError("No picture found in that file.")
        alpha = any(x in (s.get("pix_fmt") or "") for x in ("rgba", "ya", "pal8", "argb", "bgra"))
        return {"width": w, "height": h, "transparent": alpha}
    return {}


def peak_db(path):
    """Loudest point of a sound (dBFS), so uploads can be level-matched."""
    import re as _re
    err = run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-af", "volumedetect",
               "-f", "null", "-"], check=False).stderr
    m = _re.search(r"max_volume: (-?[\d.]+) dB", err)
    return float(m.group(1)) if m else -3.0


def level_match_db(asset):
    """Gain that brings a sound's peak to -3 dBFS, like the built-in pack."""
    pk = asset.get("peak_db")
    if pk is None:
        p = Path(library_dir() / asset["file"])
        pk = peak_db(p) if p.exists() else -3.0
    return round(max(-24.0, min(24.0, -3.0 - pk)), 1)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "asset"


def _not_from_reference(p):
    """A reference reel is someone else's work: it (and anything taken from it)
    can inspire, never become one of the customer's assets."""
    ref_dir = (config.brand_dir() / "reference").resolve()
    p = Path(p).resolve()
    ref_file = None
    try:
        from .brand import load_progress
        ref_file = (load_progress().get("answers") or {}).get("reference_reel")
    except Exception:
        pass
    if ref_dir in p.parents or (ref_file and Path(ref_file).resolve() == p):
        raise LibraryError("That comes from your reference reel - another creator's logos, artwork and "
                           "video are never reused. Upload your own instead.")


HEIC_JS = config.PROJECT_ROOT / "tools" / "heic.js"


def from_heic(data):
    """iPhone HEIC/HEIF photo -> upright JPEG bytes (rotation baked in, full size,
    never cropped), with macOS's own ImageIO. Nothing to install."""
    import shutil
    import subprocess
    import tempfile
    osa = shutil.which("osascript")
    if not osa:
        raise LibraryError("HEIC photos can only be converted on a Mac. Please export it as JPG and add that.")
    with tempfile.TemporaryDirectory(prefix="laine-heic-") as d:
        src, out = Path(d) / "in.heic", Path(d) / "out.jpg"
        src.write_bytes(data)
        r = subprocess.run([osa, "-l", "JavaScript", str(HEIC_JS), str(src), str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not out.is_file():
            raise LibraryError("That HEIC photo couldn't be converted; it may be damaged. "
                               "Try exporting it as JPG.")
        return out.read_bytes()


def add(filename, data, name=None, category=None):
    """Store an upload in the library. Returns the new entry."""
    kind = _kind_for(filename)
    converted = None
    if Path(filename).suffix.lower() in (".heic", ".heif"):
        if len(data) > KINDS["image"]["max_mb"] * 1024 * 1024:
            raise LibraryError(f"That file is over {KINDS['image']['max_mb']} MB.")
        data, converted = from_heic(data), Path(filename).suffix.upper().lstrip(".")
        filename = str(Path(filename).with_suffix(".jpg"))
    info = check(kind, filename, data)
    if converted:
        info["converted_from"] = converted
    ext = Path(filename).suffix.lower().replace(".jpeg", ".jpg")
    aid = f"{kind[:1]}-{uuid.uuid4().hex[:8]}"
    rel = f"{KINDS[kind]['dir']}/{_slug(name or Path(filename).stem)}-{aid}{ext}"
    dest = library_dir() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        if kind in ("sound", "image"):
            info.update(_probe(dest, kind))
    except LibraryError:
        dest.unlink()
        raise
    if kind == "image" and not category:
        category = "logo" if info.get("transparent") and max(info["width"], info["height"]) <= 1600 \
            else "screenshot"
    if kind == "sound" and not category:
        category = "other"
    entry = {"id": aid, "kind": kind, "name": (name or Path(filename).stem).strip()[:60],
             "category": category or ("font" if kind == "font" else "other"), "file": rel,
             "original_name": Path(filename).name if not converted else
             Path(filename).with_suffix("." + converted.lower()).name, "bytes": len(data),
             "added": _dt.datetime.now().isoformat(timespec="seconds"), **info}
    idx = load()
    idx["assets"].append(entry)
    _save(idx)
    return dict(entry, path=str(dest))


def add_file(path, name=None, category=None):
    p = config.check_not_protected(path)
    if not p.is_file():
        raise LibraryError(f"No file at {p}")
    _not_from_reference(p)
    return add(p.name, p.read_bytes(), name=name, category=category)


def update(asset_id, name=None, category=None, archived=None):
    idx = load()
    for a in idx["assets"]:
        if a["id"] == asset_id:
            if name is not None and name.strip():
                a["name"] = name.strip()[:60]
            if category is not None:
                a["category"] = category.strip()[:30] or a["category"]
            if archived is not None:
                a["archived"] = bool(archived)
            _save(idx)
            return dict(a, path=str(library_dir() / a["file"]))
    raise LibraryError(f"No asset {asset_id}")

