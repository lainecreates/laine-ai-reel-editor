#!/usr/bin/env python3
"""Every font included with the editor really renders: for each of the 24 families,
draw a headline and a caption with it through the same page the export uses
(overlay.build_page + tools/render_overlay.mjs) and check Chrome loaded that font
file and used it for both (no stand-in). Temporary brand; no video encode.

    python3 tests/font_library_check.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="fontlib-"))
    os.environ["LAINE_BRAND_DIR"], os.environ["LAINE_LIBRARY_DIR"] = str(tmp / "b"), str(tmp / "l")
    from fixture_brand import write_test_brand
    write_test_brand(tmp / "b")
    from laine_reel import brand, fontlib, layout, overlay
    from test_render import edit, track
    fails, rows = [], []
    for f in fontlib.families():
        fam = f["family"]
        prof = brand.compile_profile(dict(brand.load_progress()["answers"], fonts={"headline": fam, "body": fam}))
        e = edit(graphics=[{"id": "g1", "type": "text_callouts", "role": "headline", "text": "Your next reel",
                            "start": 0.0, "end": 1.0, "style": {}}])
        e["duration"] = 0.5
        lay = layout.build(e, track())
        d = tmp / fam.replace(" ", "_"); d.mkdir()
        (d / "page.html").write_text(overlay.build_page(e, lay, prof, 2))
        r = subprocess.run(["node", ROOT / "tools/render_overlay.mjs", d / "page.html", d / "f", "2", "0.5"],
                           capture_output=True, text=True)
        loaded = json.loads((d / "f/fonts_loaded.json").read_text()) if (d / "f/fonts_loaded.json").exists() else {}
        used = json.loads((d / "f/fonts.json").read_text()) if (d / "f/fonts.json").exists() else []
        drawn = {u["family"].split(",")[0].strip().strip('"\'') for u in used}
        ok = r.returncode == 0 and loaded.get(fam) is True and drawn == {fam}
        rows.append(f"{'ok  ' if ok else 'FAIL'} {f['category'][:22]:22} {fam:20} loaded={loaded.get(fam)} drawn={sorted(drawn)}")
        if not ok:
            fails.append(fam)
    print("\n".join(rows))
    print(f"\n{len(rows) - len(fails)}/{len(rows)} included fonts render" + ("" if not fails else f"; FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
