"""Numbered versions of a reel: every finished render is kept with the exact
edit state that produced it, so a customer can watch, compare, restore or
approve any of them.

    output/versions/v001/
        video.mp4      the finished render (hard link / copy, never re-encoded)
        state/         edl.json, edit.json, edit.overrides.json, cleanup.review.json,
                       transcript.fixes.json, transcript.cut.json, layout.json
        meta.json      {"n", "created", "duration", "from_feedback", "approved", ...}

review/status.json tells the review page what's happening (working / ready),
so it can show the newest version as soon as it exists.
"""

import datetime as _dt
import os
import shutil
from pathlib import Path

from .project import read_json, write_json

STATE_FILES = ["edl.json", "edit.json", "edit.overrides.json", "cleanup.review.json",
               "transcript.fixes.json", "transcript.cut.json", "layout.json",
               "brand.snapshot.json", "brand.answers.json"]


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def vdir(reel):
    return reel.output / "versions"


def list_versions(reel):
    """Numbered versions, oldest first."""
    d = vdir(reel)
    out = []
    if d.exists():
        for p in sorted(d.glob("v[0-9][0-9][0-9]")):
            if (p / "meta.json").exists() and (p / "video.mp4").exists():
                out.append(dict(read_json(p / "meta.json"), path=str(p)))
    return out


def legacy_renders(reel):
    """Renders archived before numbered versions existed (video only)."""
    d = vdir(reel)
    return sorted(d.glob("*.mp4")) if d.exists() else []


def latest(reel):
    vs = list_versions(reel)
    return vs[-1] if vs else None


def current_number(reel):
    m = reel.manifest()
    if m.get("current_version"):
        return m["current_version"]
    v = latest(reel)
    return v["n"] if v else None


def _link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def snapshot(reel, final_path, note=None):
    """Record a finished render as the next version. Returns its number."""
    vs = list_versions(reel)
    n = (vs[-1]["n"] + 1) if vs else 1
    d = vdir(reel) / f"v{n:03d}"
    (d / "state").mkdir(parents=True, exist_ok=True)
    _link_or_copy(final_path, d / "video.mp4")
    for name in STATE_FILES:
        p = reel.path(name)
        if p.exists():
            shutil.copy2(p, d / "state" / name)
    fb = sorted((reel.root / "review").glob("feedback-*.json")) if (reel.root / "review").exists() else []
    applied = [f.name for f in fb if read_json(f).get("applied_at")]
    edl = read_json(reel.path("edl.json"))
    meta = {"n": n, "created": _now(), "duration": edl["stats"]["output_duration"],
            "from_feedback": applied[-1] if applied else None, "note": note,
            "approved": False, "size": Path(final_path).stat().st_size}
    write_json(d / "meta.json", meta)
    reel.update_manifest(current_version=n)
    return n


def is_snapshotted(reel, final_path):
    """Is this exact file already kept as a version? (same inode or size+mtime)"""
    if not Path(final_path).exists():
        return True
    st = Path(final_path).stat()
    for v in list_versions(reel):
        vp = Path(v["path"]) / "video.mp4"
        vs = vp.stat()
        if (vs.st_ino == st.st_ino) or (vs.st_size == st.st_size and
                                         abs(vs.st_mtime - st.st_mtime) < 1):
            return True
    return False


def restore(reel, n, final_path):
    """Make version n current again: its edit state and its video. The state
    being replaced is backed up to review/history/<time>-before-restore/."""
    d = vdir(reel) / f"v{int(n):03d}"
    if not (d / "meta.json").exists():
        raise ValueError(f"No version {n}")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = reel.root / "review" / "history" / f"{stamp}-before-restore"
    backup.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        p = reel.path(name)
        if p.exists():
            shutil.copy2(p, backup / name)
        src = d / "state" / name
        if src.exists():
            shutil.copy2(src, p)
        elif p.exists() and name in ("edit.overrides.json", "cleanup.review.json",
                                     "transcript.fixes.json"):
            p.unlink()   # that version had none of these edits
        elif p.exists() and name == "brand.answers.json" and (d / "state" / "brand.snapshot.json").exists():
            p.unlink()   # that version recorded its brand and had no reel-only changes
        # versions from before brand snapshots existed leave the reel's brand as it is
    tmp = Path(final_path).with_suffix(".restore.mp4")
    if tmp.exists():
        tmp.unlink()
    _link_or_copy(d / "video.mp4", tmp)
    tmp.replace(final_path)
    reel.update_manifest(current_version=int(n))
    set_status(reel, "ready", f"Version {n} restored", version=int(n))
    return int(n)


def approve(reel, n):
    """Mark version n approved and copy it to output/approved/ for download."""
    d = vdir(reel) / f"v{int(n):03d}"
    meta = read_json(d / "meta.json")
    out_dir = reel.output / "approved"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{reel.slug}-approved-v{int(n):03d}.mp4"
    dest = out_dir / name
    if not dest.exists():
        _link_or_copy(d / "video.mp4", dest)
    meta.update(approved=True, approved_at=_now(), approved_file=f"output/approved/{name}")
    write_json(d / "meta.json", meta)
    reel.update_manifest(approved_version=int(n), approved_file=f"output/approved/{name}")
    return dest


# -- status for the review page ------------------------------------------------

def set_status(reel, state, message, version=None):
    d = reel.root / "review"
    d.mkdir(exist_ok=True)
    write_json(d / "status.json", {"state": state, "message": message, "version": version,
                                   "updated": _now()})


def get_status(reel):
    p = reel.root / "review" / "status.json"
    st = read_json(p) if p.exists() else {"state": "ready", "message": ""}
    v = latest(reel)
    st["latest_version"] = v["n"] if v else None
    st["current_version"] = current_number(reel)
    d = reel.root / "review"
    pending = [f.name for f in sorted(d.glob("feedback-*.json"))
               if not read_json(f).get("applied_at")] if d.exists() else []
    st["pending_feedback"] = pending
    st["pending_settings"] = (reel.root / "review" / "settings-pending.json").exists()
    return st


def label(v):
    when = _dt.datetime.fromisoformat(v["created"])
    return f"Version {v['n']} · {when.strftime('%b %-d, %-I:%M %p')}" + \
        (" · approved" if v.get("approved") else "")

