"""Fonts included with the editor: 24 Google Fonts in four groups, ready to use
with no download (assets/fonts/included/, catalog.json). All are licensed for
bundling with software that is sold (SIL Open Font License 1.1; Permanent Marker:
Apache License 2.0); each family's licence file sits next to its font files.

Customers pick any of them for headlines, captions or graphics in Brand settings.
Their own uploads (the asset library) keep working alongside.
"""

import json
import re
from pathlib import Path

from . import config

INCLUDED_DIR = config.ASSETS_DIR / "fonts" / "included"
CATEGORIES = ["Bold & Attention-Grabbing", "Elegant & Editorial", "Handwritten & Playful",
              "Clean Everyday Captions"]


def _key(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def catalog():
    p = INCLUDED_DIR / "catalog.json"
    if not p.exists():
        return {"categories": {}}
    return json.loads(p.read_text())


def families():
    """[{family, category, files: [Path], license}] for every included font."""
    out = []
    for cat, fams in catalog().get("categories", {}).items():
        for f in fams:
            out.append({"family": f["family"], "category": cat, "license": f["license"],
                        "variable": f.get("variable", False),
                        "files": [INCLUDED_DIR / f["dir"] / n for n in f["files"]
                                  if (INCLUDED_DIR / f["dir"] / n).is_file()]})
    return out


def find(family):
    """The included font of that name (any spacing/case), or None."""
    k = _key(family)
    return next((f for f in families() if _key(f["family"]) == k and f["files"]), None)


def files_for(family):
    f = find(family)
    return f["files"] if f else []


def primary_file(family):
    """One file to name the font by (the variable font, else Regular, else the first)."""
    files = files_for(family)
    if not files:
        return None
    reg = [p for p in files if p.stem.lower().endswith("regular")]
    return str((reg or files)[0])
