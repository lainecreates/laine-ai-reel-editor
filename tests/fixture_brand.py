"""A complete test brand built from brand/brand.example.json, so tests never
need (or touch) the customer's own brand."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRA = {"headline": "opening_hook", "caption_color": "white_primary_keywords",
         "sticky_font": "hand"}   # answers added to onboarding after the example was made


def write_test_brand(brand_dir, **overrides):
    """Write brand.json + onboarding.json for a test brand into brand_dir.
    Call with $LAINE_BRAND_DIR already pointing at brand_dir."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from laine_reel import brand
    answers = dict(json.loads((ROOT / "brand" / "brand.example.json").read_text())["answers"], **EXTRA)
    answers.update(overrides)
    d = Path(brand_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "onboarding.json").write_text(json.dumps({"answers": answers, "started": None}, indent=2))
    (d / "brand.json").write_text(json.dumps(brand.compile_profile(answers), indent=2))
