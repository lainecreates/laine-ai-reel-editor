#!/usr/bin/env python3
"""Laine AI Reel Editor - command line.

    python3 scripts/reel.py doctor
    python3 scripts/reel.py edit <clip> --name hook       # "Edit my reel", step 1
    python3 scripts/reel.py finish <reel> --headline "..." # step 2: render version 1
    python3 scripts/reel.py run <clip> [--name hook-test] [--pacing natural|tight|fast]
    python3 scripts/reel.py recut <reel-folder> --pacing tight
    python3 scripts/reel.py words <reel-folder>     # numbered transcript for review
    python3 scripts/reel.py plan <reel-folder>      # captions/zooms/graphics/sfx plan
    python3 scripts/reel.py final <reel-folder>     # render the branded reel
    python3 scripts/reel.py review <reel-folder>    # open the review page
    python3 scripts/reel.py apply-review <reel-folder> --render
    python3 scripts/reel.py brand status|next|answer|finish|show
    python3 scripts/reel.py list
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from laine_reel import brand, config, pipeline, reference, review, tools  # noqa: E402


def brand_mod_effective(reel_root):
    return brand.effective(reel_root) if reel_root else config.load_brand()
from laine_reel.project import Reel, list_reels, read_json  # noqa: E402


def cmd_doctor(args):
    rows = tools.doctor()
    if getattr(args, "json", False):
        import json as _j
        print(_j.dumps([{"label": a, "ok": b, "detail": c, "required": d} for a, b, c, d in rows]))
        return 0 if all(b or not d for a, b, c, d in rows) else 1
    bad = False
    for label, ok, detail, required in rows:
        mark = "ok  " if ok else ("MISS" if required else "--  ")
        if required and not ok:
            bad = True
        print(f"[{mark}] {label:28} {detail}")
    print("\nReady." if not bad else "\nMissing required items - see DEPENDENCIES.md.")
    return 1 if bad else 0


def _defaults(args, reel_root=None):
    """CLI flag > this reel's brand (defaults + reel-only changes) > built-in."""
    brand = brand_mod_effective(reel_root)
    pacing = args.pacing or brand.get("pacing") or config.DEFAULT_PACING
    frame = args.frame or brand.get("framing", {}).get("mode") or "cover"
    focus = args.focus_x if args.focus_x is not None else brand.get("framing", {}).get("focus_x", 0.5)
    return pacing, frame, focus


def cmd_run(args):
    pacing, frame, focus = _defaults(args)
    _, result = pipeline.run_all(
        args.clip, name=args.name, pacing=pacing, frame=frame, focus_x=focus,
        loudness=not args.no_loudness, preview=args.preview, model=args.model,
        transcribe_speech=not args.no_transcribe, language=args.language,
        check_speech=args.check_speech, clean=not args.no_cleanup)
    return 0 if result["ok"] else 2


def cmd_recut(args):
    reel = Reel(Path(args.reel).expanduser().resolve())
    if not reel.manifest_path.exists():
        print(f"Not a reel folder: {reel.root}")
        return 1
    pacing, frame, focus = _defaults(args, reel.root)
    print(f"Re-cutting {reel.root.name}")
    if args.retranscribe:
        pipeline.analyse(reel, model=args.model, language=args.language)
    _, result = pipeline.finish(reel, pacing=pacing, frame=frame, focus_x=focus,
                                loudness=not args.no_loudness, preview=args.preview,
                                check_speech=args.check_speech, model=args.model,
                                language=args.language, use_edl=args.use_edl,
                                clean=not args.no_cleanup)
    return 0 if result["ok"] else 2


def cmd_words(args):
    """Numbered transcript with cleanup results, for Claude's review step."""
    root = Path(args.reel).expanduser().resolve()
    words = read_json(root / "transcript.json")["words"]
    cpath = root / "cleanup.json"
    cands = read_json(cpath)["candidates"] if cpath.exists() else []
    removed = set(read_json(cpath).get("removed_words", [])) if cpath.exists() else set()
    line = []
    for i, w in enumerate(words):
        mark = "~~" if i in removed else ""
        line.append(f"[{i}]{mark}{w['text']}{mark}")
        if w["text"].rstrip().endswith((".", "?", "!")) or len(line) >= 14:
            print(f"{w['start']:7.2f}s  " + " ".join(line))
            line = []
    if line:
        print("         " + " ".join(line))
    if cands:
        print("\nCleanup candidates (~~struck~~ words are removed):")
        for c in cands:
            d = c.get("decision", {})
            state = "REMOVED" if d.get("applied") else ("flagged" if not c["auto"] else "left in")
            why = "" if d.get("applied") else f" - {d.get('why', c['reason'])}"
            print(f"  {c['id']:4} {c['type']:12} [{c['words'][0]}-{c['words'][1]}] "
                  f"{state}{why}: {c['text']}")
    return 0


def cmd_final(args):
    reel = Reel(Path(args.reel).expanduser().resolve())
    pacing, frame, focus = _defaults(args, reel.root)
    if args.replan:
        pipeline.stage_design(reel)
    _, checks = pipeline.stage_final(reel, preview=args.preview, frame=frame, focus_x=focus)
    return 0 if all(checks.values()) else 2


def cmd_review(args):
    from laine_reel.review_server import serve
    reel = Reel(Path(args.reel).expanduser().resolve())
    if not reel.manifest_path.exists():
        print(f"Not a reel folder: {reel.root}")
        return 1
    sugg = reel.path("review/suggestions.json")
    if not sugg.exists():
        reel.path("review").mkdir(exist_ok=True)
        import json as _j
        sugg.write_text(_j.dumps({"headlines": review.suggest_headlines(reel),
                                  "by": "engine (first line)"}, indent=2))

    def ready(url, _):
        print(f"Review page: {url}", flush=True)
        print("Leave this running while you review. Press Ctrl+C to stop.", flush=True)
    serve(reel, port=args.port, open_browser=not args.no_open, ready=ready)
    return 0


def cmd_locate(args):
    """What's said at a time on the review page (for interpreting notes)."""
    from laine_reel import versions as V
    reel = Reel(Path(args.reel).expanduser().resolve())
    keep = read_json(reel.path("edl.json"))["keep"]
    if args.version:
        snap = V.vdir(reel) / f"v{args.version:03d}" / "state" / "edl.json"
        keep = read_json(snap)["keep"]
    src = review.output_to_source(args.t, keep)
    words = read_json(reel.path("transcript.json"))["words"]
    near = [(i, w) for i, w in enumerate(words) if abs(w["start"] - src) < 2.5]
    print(f"{args.t:.2f}s on the page = {src:.2f}s in the original")
    for i, w in near:
        mark = " <" if w["start"] <= src <= w["end"] + 0.4 else ""
        print(f"  [{i}] {w['start']:7.2f}-{w['end']:7.2f}  {w['text']}{mark}")
    return 0


def cmd_apply_review(args):
    from laine_reel import versions as V
    reel = Reel(Path(args.reel).expanduser().resolve())
    V.set_status(reel, "working", "Claude is applying your feedback…")
    res = review.apply_all(reel)   # every saved round, oldest first
    settings = review.take_settings_changes(reel)
    if settings:
        print(f"Brand settings changed ({', '.join(settings['scopes'])}): "
              + ", ".join(settings["keys"]))
        for line in review.settings_supersede(reel, settings["keys"]):
            print(f"  + replaced earlier choice: {line}")
        need = "recut" if "pacing" in settings["keys"] else "final"
        if res["needs"] != "recut":
            res["needs"] = need
        if not res["file"]:
            res["file"] = "(brand settings)"
    if not res["file"]:
        print("No new feedback to apply.")
        V.set_status(reel, "ready", "", version=V.current_number(reel))
        return 0
    print(f"Applied {res['file']}:")
    for a in res["applied"]:
        print(f"  + {a}")
    for s in res["skipped"]:
        print(f"  - skipped: {s}")
    if res["notes"]:
        print("Notes for Claude to handle:")
        for n in res["notes"]:
            print(f"  [{n['t']:.1f}s on the page = {n['src_t']:.2f}s in the original] {n['text']}")
    if res["needs"] and args.render:
        pacing, frame, focus = _defaults(args, reel.root)
        if res["needs"] == "recut":
            pipeline.finish(reel, pacing=pacing, frame=frame, focus_x=focus, loudness=True,
                            preview=False, check_speech=True)
        else:
            pipeline.stage_design(reel)   # new settings / assets / headline go into the plan
        _, checks = pipeline.stage_final(reel, preview=args.preview, frame=frame, focus_x=focus)
        return 0 if all(checks.values()) else 2
    if res["needs"]:
        step = ("python3 scripts/reel.py recut <reel> --check-speech && " if res["needs"] == "recut" else "")
        print(f"Next: {step}python3 scripts/reel.py final <reel> --replan")
    return 0


def preflight(allow_test_brand=False):
    """Before an edit: the customer's own brand, complete, and every tool."""
    import os
    problems = []
    if os.environ.get("LAINE_BRAND_DIR") and not allow_test_brand:
        problems.append("A test brand is active (LAINE_BRAND_DIR is set). Unset it so your "
                        "own brand/ profile is used.")
    if not brand.is_onboarded():
        pass   # reels use the neutral look until onboarding is done (see _brand_line)
    else:
        q = brand.next_question()
        if q:
            problems.append(f"Brand onboarding has a new question to answer first ({q['id']}).")
    missing = [label for label, ok, _, required in tools.doctor() if required and not ok]
    if missing:
        problems.append("Missing: " + ", ".join(missing) + " (see DEPENDENCIES.md).")
    if not tools.find_tool("node"):
        problems.append("Node.js is missing (needed to draw captions and graphics).")
    return problems


def _brand_line():
    if not brand.is_onboarded():
        return ("neutral look (brand onboarding not done yet: white captions, no headline). "
                "Say \"Start my brand onboarding\" any time to make it yours.")
    b = config.load_brand()
    c, cap = b.get("colors", {}), b.get("captions", {})
    return (f"{b.get('name') or 'your brand'}: {c.get('primary')} / {c.get('accent')}, "
            f"{b.get('fonts', {}).get('headline')} + {b.get('fonts', {}).get('body')}, "
            f"{cap.get('style')} captions, {b.get('pacing')} pacing, "
            f"headline: {b.get('headline', {}).get('style')}  [{config.brand_dir() / 'brand.json'}]")


def cmd_edit(args):
    """Step 1 of "Edit my reel": brand check, cut, clean-up, plan. Stops for the
    headline choice; `finish` renders and the review page follows."""
    problems = preflight(args.allow_test_brand)
    if problems:
        print("Can't start the edit yet:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("Brand: " + _brand_line())
    pacing, frame, focus = _defaults(args)
    reel, result = pipeline.run_all(args.clip, name=args.name, pacing=pacing, frame=frame,
                                    focus_x=focus, check_speech=True)
    sugg = reel.path("review") / "suggestions.json"
    sugg.parent.mkdir(exist_ok=True)
    import json as _j
    if not sugg.exists():
        sugg.write_text(_j.dumps({"headlines": review.suggest_headlines(reel),
                                  "by": "engine (first line) - Claude replaces these"}, indent=2))
    from laine_reel import versions as V
    V.set_status(reel, "waiting", "Choosing the headline…")
    words = read_json(reel.path("transcript.cut.json"))["words"]
    opening = " ".join(w["text"] for w in words[:40])
    cl = read_json(reel.path("cleanup.json"))
    st = read_json(reel.path("edl.json"))["stats"]
    print("\n=== EDIT STEP 1 DONE ===")
    print(f"Reel: {reel.root}")
    print(f"Length: {st['source_duration']:.1f}s -> {st['output_duration']:.1f}s "
          f"({st['cuts']} cuts, {st.get('content_cuts', 0)} content clean-ups)")
    removed = [c["text"] for c in cl.get("candidates", []) if c.get("decision", {}).get("applied")]
    print("Removed: " + ("; ".join(f'"{t}"' for t in removed) if removed else "pauses only"))
    print(f"Checks: {'all passed' if result['ok'] else result['checks']}")
    edit = read_json(reel.path("edit.json"))
    print(f"Plan: {len(edit['captions']['items'])} captions, {len(edit['zooms'])} zooms, "
          f"{len(edit['graphics'])} graphics, {len(edit['sfx'])} sound effects")
    hstyle = config.load_brand().get("headline", {}).get("style", "none")
    if hstyle != "none":
        print("HEADLINE NEEDED (brand headline: " + hstyle + ")")
        print(f"Opening words: {opening}")
        print(f"Write 3 suggestions to {sugg}, ask the customer, then:")
    print(f'NEXT: python3 scripts/reel.py finish "{reel.root}"' +
          (' --headline "<their choice>"' if hstyle != "none" else ""))
    return 0 if result["ok"] else 2


def cmd_finish(args):
    """Step 2 of "Edit my reel": set the chosen headline, render version 1."""
    reel = Reel(Path(args.reel).expanduser().resolve())
    problems = preflight(args.allow_test_brand)
    if problems:
        print("Can't render yet:")
        for p in problems:
            print(f"  - {p}")
        return 1
    hstyle = brand.effective(reel.root).get("headline", {}).get("style", "none")
    if hstyle != "none":
        if args.choose_for_me:
            args.headline = review.choose_headline(reel)
            print(f"Headline chosen for you: {args.headline}")
        if not args.headline:
            print("This brand uses a headline: pass --headline \"...\" or --choose-for-me.")
            return 1
        import json as _j
        op = reel.path("edit.overrides.json")
        ov = read_json(op) if op.exists() else {}
        ov["headline"] = {"text": args.headline.strip()}
        op.write_text(_j.dumps(ov, indent=2, ensure_ascii=False) + "\n")
    pipeline.stage_design(reel)
    out, checks = pipeline.stage_final(reel, preview=args.preview)
    print("\n=== EDIT STEP 2 DONE ===")
    print(f"Video: {out}")
    print(f"Checks: {'all passed' if all(checks.values()) else checks}")
    print(f'NEXT: python3 scripts/reel.py review "{reel.root}"   (opens the review page)')
    return 0 if all(checks.values()) else 2


def cmd_plan(args):
    reel = Reel(Path(args.reel).expanduser().resolve())
    pipeline.stage_design(reel)
    print(f"Plan: {reel.path('edit-plan.md')}")
    return 0


def _print_question(q):
    print(f"[{q['number']}/{q['total']}] {q['section']}  (id: {q['id']})")
    print(q["prompt"] + ("  (optional)" if q["optional"] else ""))
    for n, (value, label) in enumerate(q["options"], 1):
        print(f"  {n}. {label}  [{value}]")
    if q.get("help"):
        print(f"  ({q['help']})")


def cmd_brand(args):
    act = args.action
    if act == "status":
        prog = brand.load_progress()
        q = brand.next_question()
        print(f"Profile: {'yes' if brand.is_onboarded() else 'not yet'} "
              f"({config.brand_dir() / 'brand.json'})")
        print(f"Answered: {len(prog['answers'])} of {len(brand.applicable(prog['answers']))}")
        print("Next question: " + (q["id"] if q else "none - ready for `brand finish`"))
        return 0
    if act == "next":
        q = brand.next_question()
        if not q:
            print("DONE - all questions answered. Run: reel.py brand finish")
            return 0
        if args.json:
            print(json.dumps(q, ensure_ascii=False, indent=2))
        else:
            _print_question(q)
        return 0
    if act == "answer":
        if len(args.rest) < 2:
            print("usage: reel.py brand answer <question-id> \"answer text\"")
            return 1
        qid, text = args.rest[0], " ".join(args.rest[1:])
        try:
            value = brand.answer(qid, text)
        except brand.AnswerError as e:
            print(f"NOT SAVED: {e}")
            return 3
        print(f"saved {qid} = {json.dumps(value, ensure_ascii=False)}")
        q = brand.next_question()
        print("next: " + (q["id"] if q else "none - run `reel.py brand finish`"))
        return 0
    if act == "finish":
        ref = None
        path = brand.load_progress()["answers"].get("reference_reel")
        if path:
            print(f"Measuring reference reel {path} ...")
            ref = reference.analyse(path, transcribe_speech=not args.no_transcribe)
        try:
            p = brand.finish(reference=ref)
        except brand.AnswerError as e:
            print(f"Not finished: {e}")
            return 3
        print((config.brand_dir() / "brand.md").read_text())
        if not (p["fonts"]["headline_file"] and p["fonts"]["body_file"]):
            print("Note: a brand font isn't installed on this computer. Add its .ttf/.otf to "
                  "assets/fonts/ before rendering (Google Fonts are free).")
        return 0
    if act == "show":
        f = config.brand_dir() / "brand.md"
        print(f.read_text() if f.exists() else "No brand profile yet.")
        return 0
    if act == "history":
        h = brand.history()
        if not h:
            print("No earlier saved defaults yet.")
        for e in h:
            print(f"{e['id']}  until {e['saved_at']}  ({len(e['differs_from_now'])} differ from now)")
            for d in e["differs_from_now"][:8]:
                print(f"    {d['label']}: {d['before']} -> {d['after']} now")
        return 0
    if act == "restore":
        if not args.rest:
            print("usage: reel.py brand restore <history id>   (see `reel.py brand history`)")
            return 1
        try:
            brand.restore_history(args.rest[0])
        except brand.AnswerError as e:
            print(f"Not restored: {e}")
            return 3
        print("Restored. Your saved defaults are now:")
        print((config.brand_dir() / "brand.md").read_text())
        return 0
    if act == "use-defaults":
        if not args.rest:
            print("usage: reel.py brand use-defaults <reel folder>")
            return 1
        reel = Reel(Path(args.rest[0]).expanduser().resolve())
        changed = brand.use_current_defaults(reel.root)
        if changed:
            review.mark_settings_changed(reel, changed, "default")
        print("This reel now uses your current saved defaults" +
              (f" (changed: {', '.join(changed)}). Render a new version to see it." if changed else "."))
        return 0
    print("actions: status, next, answer, finish, show, history, restore, use-defaults")
    return 1


def cmd_library(args):
    from laine_reel import library
    if args.action == "add":
        if not args.file:
            print("usage: reel.py library add <file> [--name ...] [--category ...]")
            return 1
        try:
            a = library.add_file(args.file, name=args.name, category=args.category)
        except library.LibraryError as e:
            print(f"NOT ADDED: {e}")
            return 3
        print(f"added {a['kind']} {a['id']}: {a['name']} ({a.get('family') or a.get('category')})")
        return 0
    for a in library.items(include_archived=True):
        extra = a.get("family") or f"{a.get('duration', '')}s" if a["kind"] == "sound" else \
            a.get("family") or f"{a.get('width')}x{a.get('height')}"
        print(f"{a['id']:12} {a['kind']:6} {a.get('category', ''):10} {a['name']:30} {extra}"
              + ("  (archived)" if a.get("archived") else ""))
    return 0


def cmd_verify_assets(args):
    from laine_reel.verify import verify
    reel = Reel(Path(args.reel).expanduser().resolve())
    res = verify(reel)
    if not res["checks"]:
        print("This reel uses none of your library assets.")
        return 0
    for c in res["checks"]:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['what']}: {c['detail']}")
    reel.mark("verify_assets", ok=res["ok"], checks=res["checks"])
    print("ASSETS IN VIDEO: " + ("all confirmed" if res["ok"] else "PROBLEMS"))
    return 0 if res["ok"] else 2


def cmd_list(args):
    for p in list_reels():
        m = read_json(p / "reel.json")
        plan = m["stages"].get("plan", {})
        print(f"{p.name:45} {plan.get('source_duration', 0):6.1f}s -> "
              f"{plan.get('output_duration', 0):6.1f}s  {plan.get('pacing', '')}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="reel.py", description="Laine AI Reel Editor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    dr = sub.add_parser("doctor", help="check tools, filters and whisper model")
    dr.add_argument("--json", action="store_true", help="machine-readable (used by install.sh)")
    sub.add_parser("list", help="list reels in workspace/")
    va = sub.add_parser("verify-assets", help="prove uploaded fonts/sounds/images are in the video")
    va.add_argument("reel")
    lb = sub.add_parser("library", help="asset library: list | add <file>")
    lb.add_argument("action", choices=["list", "add"])
    lb.add_argument("file", nargs="?")
    lb.add_argument("--name")
    lb.add_argument("--category")
    wd = sub.add_parser("words", help="numbered transcript + cleanup candidates")
    wd.add_argument("reel")
    pl = sub.add_parser("plan", help="plan captions, zooms, graphics and sfx from the brand")
    pl.add_argument("reel")
    lc = sub.add_parser("locate", help="what's said at a review-page time")
    lc.add_argument("reel")
    lc.add_argument("t", type=float)
    lc.add_argument("--version", type=int, help="the version that was being watched")
    rv = sub.add_parser("review", help="open the review page in the browser")
    rv.add_argument("reel")
    rv.add_argument("--port", type=int, default=8765)
    rv.add_argument("--no-open", action="store_true", help="don't open the browser")
    ap_ = sub.add_parser("apply-review", help="apply the latest saved review feedback")
    ap_.add_argument("reel")
    ap_.add_argument("--render", action="store_true", help="re-cut / re-render as needed")
    ap_.add_argument("--preview", action="store_true")
    ap_.add_argument("--pacing", choices=sorted(config.PACING))
    ap_.add_argument("--frame", choices=["cover", "blur"])
    ap_.add_argument("--focus-x", type=float, default=None)
    fi = sub.add_parser("final", help="render the branded reel (captions, graphics, zooms, sfx)")
    fi.add_argument("reel")
    fi.add_argument("--preview", action="store_true", help="fast, lower-quality encode")
    fi.add_argument("--replan", action="store_true", help="regenerate edit.json first")
    fi.add_argument("--pacing", choices=sorted(config.PACING))
    fi.add_argument("--frame", choices=["cover", "blur"])
    fi.add_argument("--focus-x", type=float, default=None)
    br = sub.add_parser("brand", help="brand onboarding: status | next | answer | finish | show")
    br.add_argument("action", choices=["status", "next", "answer", "finish", "show", "history",
                                           "restore", "use-defaults"])
    br.add_argument("rest", nargs="*")
    br.add_argument("--json", action="store_true", help="next: print the question as JSON")
    br.add_argument("--no-transcribe", action="store_true",
                    help="finish: skip measuring the reference reel's speaking pace")

    def edit_flags(p):
        p.add_argument("--pacing", choices=sorted(config.PACING))
        p.add_argument("--frame", choices=["cover", "blur"],
                       help="cover = fill 9:16 by cropping; blur = whole frame on blurred fill")
        p.add_argument("--focus-x", type=float, default=None,
                       help="horizontal crop position 0..1 for cover (0.5 = centre)")
        p.add_argument("--preview", action="store_true", help="fast, lower-quality encode")
        p.add_argument("--no-loudness", action="store_true", help="skip -14 LUFS normalisation")
        p.add_argument("--check-speech", action="store_true",
                       help="re-transcribe the output and confirm no words were lost")
        p.add_argument("--model", help="path to a whisper.cpp ggml model")
        p.add_argument("--no-cleanup", action="store_true",
                       help="only remove pauses; keep repeats, fillers and restarts")
        p.add_argument("--language", default="en")

    ed = sub.add_parser("edit", help='"Edit my reel" step 1: brand check, cut, clean-up, plan')
    ed.add_argument("clip")
    ed.add_argument("--name")
    ed.add_argument("--pacing", choices=sorted(config.PACING))
    ed.add_argument("--frame", choices=["cover", "blur"])
    ed.add_argument("--focus-x", type=float, default=None)
    ed.add_argument("--allow-test-brand", action="store_true", help=argparse.SUPPRESS)
    fn = sub.add_parser("finish", help='"Edit my reel" step 2: headline + render version 1')
    fn.add_argument("reel")
    fn.add_argument("--headline")
    fn.add_argument("--choose-for-me", action="store_true",
                    help="use the strongest suggested headline")
    fn.add_argument("--preview", action="store_true")
    fn.add_argument("--allow-test-brand", action="store_true", help=argparse.SUPPRESS)
    r = sub.add_parser("run", help="edit a raw clip into a clean vertical reel")
    r.add_argument("clip")
    r.add_argument("--name", help="short name for the reel folder")
    r.add_argument("--no-transcribe", action="store_true",
                   help="skip whisper; cut pauses from audio energy only")
    edit_flags(r)

    rc = sub.add_parser("recut", help="re-plan and re-render an existing reel")
    rc.add_argument("reel")
    rc.add_argument("--retranscribe", action="store_true",
                    help="transcribe and measure silences again from source/original")
    rc.add_argument("--use-edl", action="store_true",
                    help="render edl.json exactly as it is (hand/review-page edits)")
    edit_flags(rc)

    args = ap.parse_args(argv)
    handler = {"doctor": cmd_doctor, "run": cmd_run, "recut": cmd_recut, "list": cmd_list,
               "words": cmd_words, "plan": cmd_plan, "brand": cmd_brand, "final": cmd_final,
               "review": cmd_review, "apply-review": cmd_apply_review, "locate": cmd_locate,
               "edit": cmd_edit, "finish": cmd_finish, "library": cmd_library,
               "verify-assets": cmd_verify_assets}
    try:
        return handler[args.cmd](args)
    except (tools.ToolError, RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
