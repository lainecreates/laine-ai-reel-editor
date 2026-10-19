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
from laine_reel.project import Reel, list_reels, read_json, write_json  # noqa: E402


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
    from laine_reel import timeline
    keep = read_json(root / "edl.json")["keep"] if (root / "edl.json").exists() else None
    print("Word numbers here are for clean-up (cleanup.review.json). Times: in the raw clip, then "
          "[on the reel]. creative-context numbers the reel's words separately.\n")
    cpath = root / "cleanup.json"
    cands = read_json(cpath)["candidates"] if cpath.exists() else []
    removed = set(read_json(cpath).get("removed_words", [])) if cpath.exists() else set()
    line = []
    for i, w in enumerate(words):
        mark = "~~" if i in removed else ""
        line.append(f"[{i}]{mark}{w['text']}{mark}")
        if len(line) == 1:
            t0 = w["start"]
        if w["text"].rstrip().endswith((".", "?", "!")) or len(line) >= 14:
            on = timeline.source_to_output(t0, keep) if keep else None
            print(f"{t0:7.2f}s [{'%6.2fs' % on if on is not None else '   cut '}]  " + " ".join(line))
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
    print(f"Captions: {len(edit['captions']['items'])}. Graphics and zooms: none yet - they come "
          "from the creative plan (next step), not from automatic rules.")
    hstyle = config.load_brand().get("headline", {}).get("style", "none")
    print("NEXT 1 - CREATIVE PLAN: run `python3 scripts/reel.py creative-context "
          f'"{reel.root}"`, write creative.json (see the skill), check it with `reel.py plan`.')
    if hstyle != "none":
        print("HEADLINE (brand headline: " + hstyle + "): chosen automatically from the plan's hook - "
              f"don't ask. Write the hook + 2 alternatives to {sugg} for the review page. "
              "Pass --headline only if the customer gave one.")
        print(f"Opening words: {opening}")
    print(f'NEXT 2 - RENDER: python3 scripts/reel.py finish "{reel.root}"')
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
        if not args.headline:
            # no interruption: the strongest headline is the plan's hook (written from what
            # they say); the customer can change it on the review page
            from laine_reel import creative
            args.headline = creative.hook_text(reel) or review.choose_headline(reel)
            print(f"Headline chosen for you (change it any time on the review page): {args.headline}")
        if not args.headline:
            print("No headline could be chosen (no creative plan and no transcript).")
            return 1
        import json as _j
        op = reel.path("edit.overrides.json")
        ov = read_json(op) if op.exists() else {}
        ov["headline"] = {"text": args.headline.strip()}
        op.write_text(_j.dumps(ov, indent=2, ensure_ascii=False) + "\n")
        from laine_reel import creative
        creative.set_headline(reel, args.headline.strip())
    if not reel.path("creative.json").exists() and not args.rules:
        print("No creative plan yet. Run `reel.py creative-context` and write creative.json "
              "(the content-aware plan), or pass --rules to use the old automatic rules.")
        return 1
    try:
        pipeline.stage_design(reel)
    except RuntimeError as e:
        print(str(e))
        return 2
    out, checks = pipeline.stage_final(reel, preview=args.preview)
    print("\n=== EDIT STEP 2 DONE ===")
    print(f"Video: {out}")
    print(f"Checks: {'all passed' if all(checks.values()) else checks}")
    print(f'NEXT: python3 scripts/reel.py review "{reel.root}"   (opens the review page)')
    return 0 if all(checks.values()) else 2


def cmd_plan(args):
    reel = Reel(Path(args.reel).expanduser().resolve())
    try:
        edit = pipeline.stage_design(reel)
    except RuntimeError as e:
        print(str(e))
        return 2
    cr = edit.get("creative", {})
    print(("Creative plan used: " + (cr.get("summary") or "") + f" ({cr.get('moments')} moments)")
          if cr.get("used") else "No creative plan (creative.json): graphics from the fallback rules.")
    print(f"Plan: {reel.path('edit-plan.md')}")
    return 0


def cmd_creative_context(args):
    """What Claude needs to write creative.json: the numbered transcript, the
    style and the customer's rules, allowed intents, limits."""
    import json as _j
    from laine_reel import creative
    reel = Reel(Path(args.reel).expanduser().resolve())
    words = read_json(reel.path("transcript.cut.json"))["words"]
    dur = read_json(reel.path("edl.json"))["stats"]["output_duration"]
    prof = brand.effective(reel.root)
    ctx = creative.context(words, dur, prof, brand.reel_answers(reel.root), reel.root.name)
    out = reel.path("review") / "creative-context.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(_j.dumps(ctx, indent=1, ensure_ascii=False))
    print(_j.dumps(ctx, indent=1, ensure_ascii=False))
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
    if act == "set":
        # Claude saves preferences given in everyday words, as exact settings
        import json as _j
        if not args.rest:
            print("usage: reel.py brand set '<json settings>' [--scope default|reel --reel <reel>]")
            return 1
        try:
            changes = _j.loads(args.rest[0])
        except ValueError as e:
            print(f"NOT SAVED: that isn't valid JSON ({e})")
            return 3
        scope = args.scope or "default"
        root = Path(args.reel).expanduser().resolve() if args.reel else None
        if scope == "reel" and not root:
            print("NOT SAVED: --scope reel needs --reel <reel folder>")
            return 3
        try:
            brand.save_settings(changes, scope, root)
        except brand.AnswerError as e:
            print(f"NOT SAVED: {e}")
            return 3
        if root:
            review.mark_settings_changed(Reel(root), list(changes), scope)
        print(f"Saved for {'this reel only' if scope == 'reel' else 'your saved defaults (future reels)'}:")
        prof = brand.effective(root) if root else config.load_brand()
        print("\n".join("  " + l for l in brand.explain(prof)))
        return 0
    if act == "explain":
        root = Path(args.reel).expanduser().resolve() if args.reel else None
        prof = brand.effective(root) if root else (config.load_brand() or brand.neutral_profile())
        print("\n".join(brand.explain(prof)))
        return 0
    if act == "suggest":
        import json as _j
        print(_j.dumps(brand.suggestions(args.rest[0] if args.rest else None), indent=1))
        return 0
    if act == "reference":
        # measure a reference reel's editing style (any time); changes no settings
        import json as _j
        if not args.rest:
            print('usage: reel.py brand reference "<path to a reel you love>"')
            return 1
        try:
            ref = reference.analyse(args.rest[0], transcribe_speech=not args.no_transcribe)
        except ValueError as e:
            print(f"Can't use that file: {e}")
            return 3
        (config.brand_dir() / "reference").mkdir(parents=True, exist_ok=True)
        (config.brand_dir() / "reference" / "reference.json").write_text(_j.dumps(ref, indent=1))
        print(_j.dumps({k: v for k, v in ref.items() if k != "file"}, indent=1))
        print("\nLook at the contact sheet, write what you see to brand/reference/traits.json, then ask "
              "what they like about it (reel.py brand set '{\"reference_prefs\": {...}}').")
        return 0
    if act == "reference-suggest":
        import json as _j
        from laine_reel import reference_style
        rp = config.brand_dir() / "reference" / "reference.json"
        ref = _j.loads(rp.read_text()) if rp.exists() else (config.load_brand().get("reference") or {})
        prefs = (brand.load_progress().get("answers") or {}).get("reference_prefs") or {}
        sug = reference_style.inspired_settings(reference_style.load(), ref, prefs)
        print(_j.dumps(sug, indent=1))
        print("\nProposals only: read them to the customer; save only what they agree to (brand set).")
        return 0
    print("actions: status, next, answer, finish, show, history, restore, use-defaults, set, explain, suggest, "
          "reference, reference-suggest")
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


def cmd_remove_phrase(args):
    """Remove a phrase by quoting it ("they started", the first time it's said).
    Writes cleanup.review.json; `recut --check-speech` makes and verifies the cut."""
    from laine_reel import cleanup
    reel = Reel(Path(args.reel).expanduser().resolve())
    words = read_json(reel.path("transcript.json"))["words"]
    found = cleanup.find_phrase(words, args.phrase, args.occurrence)
    if isinstance(found, str):
        print(f"NOT ADDED: {found}")
        return 3
    p = reel.path("cleanup.review.json")
    rv = read_json(p) if p.exists() else {"remove": [], "keep": []}
    rv.setdefault("remove", []).append({"phrase": args.phrase, "occurrence": args.occurrence,
                                        "type": "requested", "reason": args.reason or "customer request"})
    write_json(p, rv)
    print(f"Will remove words {found[0]}-{found[1]}: \"{' '.join(w['text'] for w in words[found[0]:found[1] + 1])}\" "
          f"({args.occurrence} time it's said)")
    print("Next: python3 scripts/reel.py recut <reel> --check-speech")
    return 0


def cmd_carousel(args):
    """Add a spinning image carousel to one reel (a customer request; never a default)."""
    from laine_reel import carousel
    reel = Reel(Path(args.reel).expanduser().resolve())
    opts = {k: getattr(args, k) for k in carousel.DEFAULTS if getattr(args, k)}
    g, problems = carousel.request(reel, [x.strip() for x in args.images.split(",") if x.strip()],
                                   args.at, args.duration, **opts)
    if problems:
        print("NOT ADDED:\n  - " + "\n  - ".join(problems))
        return 3
    o = carousel.options(g)
    print(f"Carousel added: {len(g['assets'])} images at {g['start']:.1f}-{g['end']:.1f}s, "
          f"{o['place'].replace('_', ' ')}, {o['size']}, {o['speed']}, {o['direction']}, {o['motion']}")
    print("Next: python3 scripts/reel.py final <reel> --replan")
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
    rp = sub.add_parser("remove-phrase", help='remove a quoted phrase: "they started" --occurrence first')
    rp.add_argument("reel")
    rp.add_argument("phrase")
    rp.add_argument("--occurrence", default="first", help="first | second | last | 1 | 2 ...")
    rp.add_argument("--reason")
    cs = sub.add_parser("carousel", help="add a spinning carousel of library images to one reel")
    cs.add_argument("reel")
    cs.add_argument("--images", required=True, help="library ids or names, comma-separated (2-8)")
    cs.add_argument("--at", type=float, required=True, help="start time on the reel as it is now (s)")
    cs.add_argument("--duration", type=float, default=5.0)
    from laine_reel import carousel as _c
    cs.add_argument("--place", choices=_c.PLACES)
    cs.add_argument("--size", choices=list(_c.SIZES))
    cs.add_argument("--speed", choices=list(_c.SPEEDS))
    cs.add_argument("--direction", choices=_c.DIRECTIONS)
    cs.add_argument("--motion", choices=list(_c.MOTIONS))
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
                                           "restore", "use-defaults", "set", "explain", "suggest",
                                           "reference", "reference-suggest"])
    br.add_argument("rest", nargs="*")
    br.add_argument("--json", action="store_true", help="next: print the question as JSON")
    br.add_argument("--scope", choices=["default", "reel"], help="set: your saved defaults or this reel only")
    br.add_argument("--reel", help="set/explain: the reel folder")
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
    cc = sub.add_parser("creative-context", help="what Claude needs to write the creative plan")
    cc.add_argument("reel")
    fn = sub.add_parser("finish", help='"Edit my reel" step 2: headline + render version 1')
    fn.add_argument("--rules", action="store_true", help="no creative plan: use the old automatic rules")
    fn.add_argument("reel")
    fn.add_argument("--headline")
    fn.add_argument("--choose-for-me", action="store_true",  # the default now; kept for old instructions
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
    handler = {"creative-context": cmd_creative_context, "doctor": cmd_doctor, "run": cmd_run, "recut": cmd_recut, "list": cmd_list,
               "words": cmd_words, "plan": cmd_plan, "brand": cmd_brand, "final": cmd_final,
               "review": cmd_review, "apply-review": cmd_apply_review, "locate": cmd_locate,
               "edit": cmd_edit, "finish": cmd_finish, "library": cmd_library,
               "verify-assets": cmd_verify_assets, "carousel": cmd_carousel,
               "remove-phrase": cmd_remove_phrase}
    try:
        return handler[args.cmd](args)
    except (tools.ToolError, RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
