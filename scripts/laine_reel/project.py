"""Reel folders inside workspace/ and the reel.json manifest.

Layout of one reel:

    workspace/<yyyy-mm-dd>-<name>/
      source/original.<ext>   read-only copy of the raw clip (never edited)
      work/                   intermediate files (audio, raw whisper, filtergraph)
      transcript.json         words on the SOURCE timeline
      silences.json           silent ranges from ffmpeg
      edl.json                cut list: what is kept / removed (review page edits this)
      transcript.cut.json     words on the OUTPUT timeline (captions use this)
      edit.json               future layers: captions, zooms, graphics, sfx
      cut-report.md           human-readable summary
      output/<name>-vertical.mp4
      reel.json               manifest: inputs, hashes, settings, stage status
"""

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

from . import config


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "reel"


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


class Reel:
    def __init__(self, root):
        self.root = Path(root)
        self.source_dir = self.root / "source"
        self.work = self.root / "work"
        self.output = self.root / "output"
        self.manifest_path = self.root / "reel.json"

    # -- creation ---------------------------------------------------------
    @classmethod
    def create(cls, clip, name=None, workspace=None):
        clip = config.check_not_protected(clip)
        if not clip.is_file():
            raise FileNotFoundError(clip)
        workspace = Path(workspace or config.WORKSPACE)
        workspace.mkdir(parents=True, exist_ok=True)
        base = f"{_dt.date.today().isoformat()}-{slugify(name or clip.stem)}"
        root, n = workspace / base, 2
        while root.exists():
            root, n = workspace / f"{base}-{n}", n + 1
        reel = cls(root)
        for d in (reel.source_dir, reel.work, reel.output):
            d.mkdir(parents=True)
        reel.ingest(clip)
        return reel

    def ingest(self, clip):
        """Copy the raw clip in and make the copy read-only. The file at
        `clip` is only ever read."""
        input_hash = sha256(clip)
        dst = self.source_dir / f"original{clip.suffix.lower()}"
        shutil.copy2(clip, dst)
        os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        if sha256(dst) != input_hash:
            raise IOError("Copy of the original does not match the source file.")
        self.save_manifest({
            "name": self.root.name,
            "created": _dt.datetime.now().isoformat(timespec="seconds"),
            "input": {"path": str(clip), "sha256": input_hash,
                      "bytes": clip.stat().st_size},
            "original": str(dst.relative_to(self.root)),
            "stages": {},
        })

    # -- accessors --------------------------------------------------------
    @property
    def original(self):
        return self.root / self.manifest()["original"]

    @property
    def slug(self):
        return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", self.root.name)

    @property
    def video_out(self):
        return self.output / f"{self.slug}-vertical.mp4"

    def path(self, name):
        return self.root / name

    def manifest(self):
        return read_json(self.manifest_path)

    def save_manifest(self, data):
        write_json(self.manifest_path, data)

    def update_manifest(self, **fields):
        m = self.manifest()
        m.update(fields)
        self.save_manifest(m)

    def mark(self, stage, **info):
        m = self.manifest()
        m["stages"][stage] = dict(info, at=_dt.datetime.now().isoformat(timespec="seconds"))
        self.save_manifest(m)


def archive(path):
    """Keep a render before it is replaced: copy it to output/versions/
    as <name>-<time it was made>.mp4. Never deletes anything."""
    path = Path(path)
    if not path.exists():
        return None
    stamp = _dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
    dest = path.parent / "versions" / f"{path.stem}-{stamp}{path.suffix}"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    return dest


def list_reels(workspace=None):
    ws = Path(workspace or config.WORKSPACE)
    return sorted(p for p in ws.iterdir() if (p / "reel.json").exists()) if ws.exists() else []
