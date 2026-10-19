"""The pipeline, as named stages.

    ingest -> audio -> transcribe -> silences -> align -> cleanup -> plan
           -> render -> remap -> verify -> design (edit plan, needs a brand profile)
    final: faces -> layout -> overlay frames (Chrome) -> composite (ffmpeg)

Each stage writes its artifact into the reel folder and records itself in
reel.json, so stages can be re-run on their own (e.g. re-plan with a new
pacing without transcribing again). Future stages (captions, zooms,
graphics, sfx) slot in between `remap` and a final composite render - see
docs/ARCHITECTURE.md.
"""

import difflib
import os
import shutil
from fractions import Fraction

from . import (align, cleanup, composite, conformance, config, faces, layout, media, overlay,
               pauses, planner, render, timeline, versions)
from .project import Reel, archive, read_json, sha256, write_json
from .tools import find_tool, find_whisper_model, run
from .transcribe import transcribe


def log(msg):
    print(f"  {msg}", flush=True)


EMPTY_EDIT = {
    "version": 1,
    "note": "Layers for later phases. Not rendered yet.",
    "brand": "brand/brand.json",
    "captions": {"enabled": False, "style": None, "source": "transcript.cut.json"},
    "zooms": [],
    "graphics": [],
    "sfx": [],
    "music": None,
}


def run_all(clip, name=None, pacing=config.DEFAULT_PACING, frame="cover", focus_x=0.5,
            loudness=True, preview=False, model=None, transcribe_speech=True,
            language="en", check_speech=False, workspace=None, clean=True):
    print(f"New reel from {clip}")
    reel = Reel.create(clip, name=name, workspace=workspace)
    log(f"ingest     -> {reel.root}")
    reel.mark("ingest", original=str(reel.original.relative_to(reel.root)))

    info = media.probe(reel.original)
    if not info["has_audio"]:
        raise RuntimeError("This clip has no audio track; nothing to transcribe or tighten.")
    reel.update_manifest(source_info=info)
    log(f"probe      {info['width']}x{info['height']} {info['fps']}fps {info['duration']:.2f}s")

    analyse(reel, model=model, language=language, transcribe_speech=transcribe_speech)
    write_json(reel.path("edit.json"), EMPTY_EDIT)
    return finish(reel, pacing=pacing, frame=frame, focus_x=focus_x, loudness=loudness,
                  preview=preview, check_speech=check_speech, model=model, language=language,
                  clean=clean)


def analyse(reel, model=None, language="en", transcribe_speech=True):
    """audio -> transcribe -> silences. Also used by `recut --retranscribe`."""
    stage_audio(reel)
    if transcribe_speech:
        stage_transcribe(reel, model=model, language=language)
    else:
        log("transcribe skipped (--no-transcribe): pauses use audio energy only")
    stage_silences(reel)


def finish(reel, pacing, frame, focus_x, loudness, preview, check_speech=False,
           model=None, language="en", use_edl=False, clean=True):
    """align -> cleanup -> plan -> render -> remap -> verify.

    use_edl=True renders edl.json as it is (e.g. after edits in the future
    review page) instead of re-planning it.
    """
    versions.set_status(reel, "working", "Re-cutting your video…")
    stage_align(reel)
    if use_edl:
        log("plan       using existing edl.json as edited")
    else:
        stage_cleanup(reel, pacing, enabled=clean)
        stage_plan(reel, pacing)
    stage_render(reel, frame=frame, focus_x=focus_x, loudness=loudness, preview=preview)
    stage_remap(reel)
    result = stage_verify(reel, check_speech=check_speech, model=model, language=language)
    failed = _failed_quiet_joins(reel, result) if check_speech and not use_edl else []
    if failed:
        # A quiet-point join didn't pass the speech check: put those words back and
        # cut again, so the video never keeps a clipped word.
        p = reel.path("cleanup.rejected.json")
        old = read_json(p) if p.exists() else {"quiet_joins_failed": []}
        old["quiet_joins_failed"] = sorted(set(old["quiet_joins_failed"]) | set(failed))
        write_json(p, old)
        log(f"verify     a quiet-point join didn't pass the speech check (word {', '.join(map(str, failed))}); "
            "putting those words back and cutting again")
        stage_cleanup(reel, pacing, enabled=clean)
        stage_plan(reel, pacing)
        stage_render(reel, frame=frame, focus_x=focus_x, loudness=loudness, preview=preview)
        stage_remap(reel)
        result = stage_verify(reel, check_speech=check_speech, model=model, language=language)
    write_report(reel)
    if not config.load_brand():
        log("design     neutral look: brand onboarding isn't done yet")
    stage_design(reel)
    # The cut is done; `final` sets "working" again when it starts rendering.
    versions.set_status(reel, "ready", "", version=versions.current_number(reel))
    print(f"Done: {reel.video_out}")
    return reel, result


# -- stages ---------------------------------------------------------------

def stage_audio(reel):
    wav = reel.work / "audio16k.wav"
    media.extract_audio(reel.original, wav)
    reel.mark("audio", file=str(wav.relative_to(reel.root)))
    log("audio      16 kHz mono extracted")


def stage_transcribe(reel, model=None, language="en"):
    model_path = find_whisper_model(model)
    if not model_path:
        raise RuntimeError("No whisper.cpp model found. Put a ggml-*.bin model in models/, "
                           "set whisper_model in config/settings.json, or pass --no-transcribe.")
    log(f"transcribe whisper.cpp ({model_path.name}) ...")
    data = transcribe(reel.work / "audio16k.wav", model_path, reel.work / "whisper", language)
    write_json(reel.path("transcript.json"), data)
    reel.mark("transcribe", model=str(model_path), words=len(data["words"]))
    log(f"transcribe {len(data['words'])} words")


def stage_silences(reel, noise_db=None):
    """Pauses (>= 0.15 s) for pacing, plus short gaps (>= 0.03 s) between
    words, which are the only places a content cut may start or end."""
    wav = reel.work / "audio16k.wav"
    mean = media.mean_volume(wav)
    threshold = noise_db if noise_db is not None else media.silence_threshold(mean)
    duration = reel.manifest()["source_info"]["duration"]
    audio_end = media.duration(wav)
    found = media.detect_silences(wav, threshold, duration=audio_end)
    gaps = media.detect_silences(wav, threshold, min_dur=config.GAP_MIN_DETECT, duration=audio_end)
    write_json(reel.path("silences.json"),
               {"mean_volume_db": mean, "threshold_db": threshold, "audio_end": audio_end,
                "video_duration": duration, "silences": found, "gaps": gaps})
    reel.mark("silences", threshold_db=threshold, count=len(found), gaps=len(gaps))
    log(f"silences   {len(found)} pauses, {len(gaps)} gaps below {threshold} dB (mean {mean} dB)")


def _silences(reel):
    """silences.json, adding short gaps for reels analysed before cleanup existed."""
    sil = read_json(reel.path("silences.json"))
    if "gaps" not in sil:
        sil["gaps"] = media.detect_silences(reel.work / "audio16k.wav", sil["threshold_db"],
                                            min_dur=config.GAP_MIN_DETECT,
                                            duration=sil["audio_end"])
        write_json(reel.path("silences.json"), sil)
    return sil


def stage_align(reel):
    """Snap whisper word times onto measured speech (see align.py)."""
    tpath = reel.path("transcript.json")
    if not tpath.exists():
        return
    data = read_json(tpath)
    sil = _silences(reel)
    # Always align from whisper's own times so re-runs don't compound.
    raw = [dict(w, start=w.get("whisper_start", w["start"]), end=w.get("whisper_end", w["end"]))
           for w in data["words"]]
    data["words"] = align.align_words(raw, sil["silences"], sil["audio_end"])
    snapped = align.snap_onsets(data["words"], sil["silences"] + sil.get("gaps", []))
    refined = align.refine_starts(data["words"], reel.work / "audio16k.wav")
    align.fill_ends(data["words"], sil["silences"] + sil.get("gaps", []))
    data["timing"] = ("whisper DTW (lag-corrected) -> speech regions -> pause onsets "
                      "-> loudness dips between words")
    # Customer fixes from the review page (spelling, timing) win over whisper.
    fpath = reel.path("transcript.fixes.json")
    if fpath.exists():
        for k, fix in read_json(fpath).get("words", {}).items():
            i = int(k)
            if 0 <= i < len(data["words"]):
                w = data["words"][i]
                if fix.get("text") is not None and fix["text"] != w["text"]:
                    w["heard"] = w["text"]   # cut detection keeps using this
                    w["text"] = fix["text"]
                for key in ("start", "end"):
                    if fix.get(key) is not None:
                        w[key] = round(fix[key], 3)
                w["fixed"] = True
    write_json(tpath, data)
    moved = sum(1 for w in data["words"] if abs(w["start"] - w["whisper_start"]) > 0.1)
    reel.mark("align", words=len(data["words"]), moved=moved, onsets_snapped=snapped,
              onsets_refined=refined)
    log(f"align      {snapped} start(s) snapped to a pause onset, {refined} refined to the "
        f"dip between words")


def stage_cleanup(reel, pacing_name, enabled=True):
    """Find repeats / fillers / restarts and place only audio-safe cuts."""
    tpath = reel.path("transcript.json")
    out = reel.path("cleanup.json")
    if not enabled or not tpath.exists():
        write_json(out, {"enabled": False, "candidates": [], "cuts": []})
        log("cleanup    off")
        return
    words = read_json(tpath)["words"]
    sil = _silences(reel)
    review_path = reel.path("cleanup.review.json")
    review = read_json(review_path) if review_path.exists() else None
    cands = cleanup.merge_review(cleanup.detect(words), review, words)
    rp = reel.path("cleanup.rejected.json")
    rejected = set((read_json(rp) if rp.exists() else {}).get("quiet_joins_failed", []))
    cuts, decisions = cleanup.place(cands, words, sil["gaps"], config.PACING[pacing_name],
                                    dip=_dip_finder(reel), no_dip=rejected)
    manual = []
    for i in (review or {}).get("pause_cuts", []):
        cut, why = cleanup.pause_cut(words, int(i), sil["silences"] + sil["gaps"],
                                     config.PACING[pacing_name])
        manual.append({"after_word": int(i), "applied": cut is not None, "why": why})
        if cut:
            cuts.append(cut)
            manual[-1]["pause_before"] = cut["pause_before"]
    for c in cands:
        c["decision"] = decisions.get(c["id"], {"applied": False, "why": c["reason"]})
    removed = sorted(cleanup.removed_indices(cands, decisions))
    write_json(out, {"enabled": True, "reviewed": review is not None, "candidates": cands,
                     "cuts": cuts, "removed_words": removed, "pause_cuts": manual})
    # Requests that couldn't be done are said out loud, never silently dropped.
    for c in cands:
        if c.get("source") == "review" and not c["decision"]["applied"]:
            log(f"cleanup    NOT REMOVED (requested): \"{c['text']}\" - {c['decision'].get('why') or c['reason']}")
        elif c["decision"].get("quiet_join"):
            log(f"cleanup    removed \"{c['text']}\" at a quiet point between words (no pause there); "
                "the speech check will confirm the join")
    applied = sum(1 for c in cands if c["decision"]["applied"])
    skipped = sum(1 for c in cands if c["auto"] and not c["decision"]["applied"])
    flagged = sum(1 for c in cands if not c["auto"])
    reel.mark("cleanup", applied=applied, skipped=skipped, flagged=flagged,
              reviewed=review is not None, words_removed=len(removed))
    log(f"cleanup    {applied} applied ({len(removed)} words), {skipped} left in (unsafe), "
        f"{flagged} flagged{', with review' if review else ''}")


def _dip_finder(reel):
    """dip(t0, t1) -> (t, level_db, speech_db): the quietest 20 ms between two words
    and how loud the speech around it is, measured on the clip's own audio."""
    wav = reel.work / "audio16k.wav"
    if not wav.exists():
        return None
    env = align.envelope(wav)
    hop = align.HOP

    def dip(t0, t1):
        i0, i1 = max(0, int(t0 / hop)), min(len(env) - 1, int(t1 / hop))
        if i1 - i0 < 3:
            return None
        pairs = [(max(env[k], env[k + 1]), k) for k in range(i0, i1 - 1)]   # 20 ms stays quiet
        level, k = min(pairs)
        around = sorted(env[max(0, i0 - 25):min(len(env), i1 + 25)])
        speech = around[int(len(around) * 0.75)] if around else level
        return (round((k + 1) * hop, 3), level, speech)
    return dip


def _failed_quiet_joins(reel, result):
    """Word numbers of quiet-point joins the speech check flagged."""
    bad = {p.get("word") for p in result.get("cleanup_join_problems") or [] if p.get("word") is not None}
    if not bad:
        return []
    cl = read_json(reel.path("cleanup.json"))
    return sorted({c["words"][0] for c in cl["candidates"]
                   if c["decision"].get("quiet_join") and c["words"] and c["words"][0] in bad})


def stage_plan(reel, pacing_name):
    pacing = config.PACING[pacing_name]
    duration = reel.manifest()["source_info"]["duration"]
    sil = _silences(reel)
    fps_str, fps = config.output_fps(reel.manifest()["source_info"].get("fps"))
    cpath = reel.path("cleanup.json")
    content = read_json(cpath)["cuts"] if cpath.exists() else []
    plan = pauses.plan_cuts(duration, sil["silences"], pacing, audio_end=sil.get("audio_end"),
                            fps=fps, extra_cuts=content, quiet=sil["silences"] + sil["gaps"])
    plan["source"] = str(reel.original.relative_to(reel.root))
    plan["fps"] = fps_str
    write_json(reel.path("edl.json"), plan)
    st = plan["stats"]
    reel.mark("plan", pacing=pacing_name, **st)
    log(f"plan       {pacing_name}: {st['cuts']} cuts ({st['content_cuts']} content), "
        f"{st['source_duration']:.2f}s -> {st['output_duration']:.2f}s (-{st['removed_pct']}%)")


def stage_render(reel, frame="cover", focus_x=0.5, loudness=True, preview=False):
    edl = read_json(reel.path("edl.json"))
    log(f"render     {len(edl['keep'])} segments, {frame} framing"
        f"{', preview quality' if preview else ''} ...")
    archive(reel.video_out)  # previous renders are kept in output/versions/
    render.render(reel.original, edl["keep"], reel.video_out, reel.work, frame=frame,
                  focus_x=focus_x, loudness=loudness, preview=preview,
                  fps=edl.get("fps", config.OUTPUT["fps"]))
    reel.mark("render", file=str(reel.video_out.relative_to(reel.root)), frame=frame,
              focus_x=focus_x, loudness=loudness, preview=preview)
    log(f"render     -> {reel.video_out.relative_to(reel.root)}")


def _removed(reel):
    cpath = reel.path("cleanup.json")
    return set(read_json(cpath).get("removed_words", [])) if cpath.exists() else set()


def stage_remap(reel):
    tpath = reel.path("transcript.json")
    if not tpath.exists():
        return
    edl = read_json(reel.path("edl.json"))
    removed = _removed(reel)
    kept = [dict(w, i=i) for i, w in enumerate(read_json(tpath)["words"]) if i not in removed]
    words = timeline.remap_words(kept, edl["keep"])
    write_json(reel.path("transcript.cut.json"), {"timeline": "output", "words": words})
    reel.mark("remap", words=len(words))
    log(f"remap      {len(words)} words on the output timeline")


def stage_verify(reel, check_speech=False, model=None, language="en"):
    m = reel.manifest()
    edl = read_json(reel.path("edl.json"))
    out = media.probe(reel.video_out)
    expected = edl["stats"]["output_duration"]
    checks = {
        "vertical_1080x1920": (out["width"], out["height"]) == (config.OUTPUT["width"],
                                                                 config.OUTPUT["height"]),
        "has_audio": out["has_audio"],
        "duration_matches_plan": abs(out["duration"] - expected) <= 0.15,
        "original_copy_unchanged": sha256(reel.original) == m["input"]["sha256"],
    }
    detail = {"output_duration": out["duration"], "expected_duration": expected}

    if check_speech and reel.path("transcript.json").exists():
        log("verify     re-transcribing output to check every kept word is there ...")
        wav = reel.work / "output16k.wav"
        media.extract_audio(reel.video_out, wav)
        again = transcribe(wav, find_whisper_model(model), reel.work / "whisper_output", language)
        words = read_json(reel.path("transcript.json"))["words"]
        removed = _removed(reel)
        # Expected = every word not deliberately removed, as tokens.
        exp, joins = [], []
        for i, w in enumerate(words):
            if i in removed and (i == 0 or i - 1 not in removed):
                joins.append((len(exp), i))
            if i not in removed:
                exp.extend(cleanup.tokens([w]))
        got = cleanup.tokens(again["words"])
        sm = difflib.SequenceMatcher(None, exp, got, autojunk=False)
        detail["speech_similarity"] = round(sm.ratio(), 3)
        diffs = [{"op": op, "expected": " ".join(exp[a:b]), "heard": " ".join(got[c:d]),
                  "at_token": a} for op, a, b, c, d in sm.get_opcodes() if op != "equal"]
        detail["speech_diffs"] = diffs
        checks["speech_preserved"] = sm.ratio() >= 0.9
        if joins:
            # No difference may sit right at a content-cleanup join: that
            # would mean a clipped word or a leftover fragment.
            bad = []
            for d in diffs:
                near = [w for j, w in joins if abs(d["at_token"] - j) <= 2]
                if near:
                    bad.append(dict(d, word=near[0]))
            detail["cleanup_join_problems"] = bad
            checks["cleanup_joins_clean"] = not bad

    cpath = reel.path("cleanup.json")
    asked = [p for p in (read_json(cpath).get("pause_cuts", []) if cpath.exists() else [])
             if p.get("applied")]
    if asked and reel.path("transcript.cut.json").exists():
        out_words = {w.get("i"): w for w in read_json(reel.path("transcript.cut.json"))["words"]}
        shorter = []
        for p in asked:
            a, b = out_words.get(p["after_word"]), out_words.get(p["after_word"] + 1)
            if a and b:
                now = b["start"] - a["end"]
                shorter.append(now < p.get("pause_before", 99) - 0.2 or now <= 0.3)
                p["pause_after"] = round(now, 3)
        detail["requested_pauses"] = asked
        checks["requested_pauses_shortened"] = all(shorter) if shorter else True

    ok = all(checks.values())
    reel.mark("verify", ok=ok, checks=checks, **detail)
    for k, v in checks.items():
        log(f"verify     {'ok  ' if v else 'FAIL'} {k}")
    return {"ok": ok, "checks": checks, **detail}


def stage_design(reel, brand=None):
    """Plan captions, zooms, graphics, sfx and music from the brand profile."""
    from .brand import effective
    brand = brand or effective(reel.root)   # saved defaults + this reel's own changes
    if not brand:
        raise RuntimeError("No brand profile yet. Run brand onboarding first.")
    cut = reel.path("transcript.cut.json")
    words = read_json(cut)["words"] if cut.exists() else []
    edl = read_json(reel.path("edl.json"))
    joins, t = [], 0.0
    for a, b in edl["keep"][:-1]:
        t += b - a
        joins.append(round(t, 3))
    opath = reel.path("edit.overrides.json")
    overrides = read_json(opath) if opath.exists() else {}
    if overrides.get("add") or overrides.get("set"):
        from .review import retime_additions
        overrides = retime_additions(overrides, edl["keep"])
    from . import creative
    brief = creative.load(reel)
    if brief is not None:
        brief, fresh = creative.complete(brief, words)
        brief, notes = creative.reanchor(brief, words)
        for n in notes:
            log(f"creative   {n}")
        try:
            creative.validate(brief, words, brand, edl["stats"]["output_duration"])
        except creative.BriefError as e:
            raise RuntimeError("The creative plan (creative.json) needs fixing:\n  - " +
                               "\n  - ".join(e.problems))
        if notes or fresh:
            creative.save(reel, brief, words)
    edit = planner.plan(words, edl["stats"]["output_duration"], joins, brand, overrides, brief=brief)
    # one design per graphic from the style's designs: the customer's pick, the plan's,
    # this reel's look, else what their recent reels used least (pinned in designs.json)
    from . import designs
    for gid, v in designs.assign(reel, edit, brand).items():
        log(f"design     {gid}: {next(g['variant_name'] for g in edit['graphics'] if g['id'] == gid)}")
    edit["creative"] = ({"used": True, "summary": brief.get("summary"), "tone": brief.get("tone"),
                         "moments": len(brief.get("moments", [])),
                         "no_graphics": brief.get("no_graphics", [])} if brief is not None
                        else {"used": False})
    write_json(reel.path("edit.json"), edit)
    reel.path("edit-plan.md").write_text(planner.plan_markdown(edit, reel.root.name))
    reel.mark("design", captions=len(edit["captions"]["items"]), zooms=len(edit["zooms"]),
              graphics=len(edit["graphics"]), sfx=len(edit["sfx"]),
              music=bool(edit["music"]), overrides=bool(overrides))
    log(f"design     {len(edit['captions']['items'])} captions, {len(edit['zooms'])} zooms, "
        f"{len(edit['graphics'])} graphics, {len(edit['sfx'])} sfx -> edit-plan.md")
    return edit


def stage_final(reel, preview=False, frame="cover", focus_x=0.5, loudness=True):
    """Render the branded reel, then keep it as the next numbered version."""
    versions.set_status(reel, "working", "Rendering your new version…")
    try:
        out, checks = _stage_final(reel, preview, frame, focus_x, loudness)
    except Exception as e:
        versions.set_status(reel, "error", f"Rendering stopped: {e}")
        raise
    if preview:
        versions.set_status(reel, "ready", "Preview rendered")
        return out, checks
    n = versions.snapshot(reel, out)
    if all(checks.values()):
        # remember which designs this reel used, so the next reels can vary
        from . import designs
        from .brand import effective
        edit = read_json(reel.path("edit.json"))
        designs.record(reel, edit, effective(reel.root) or {})
    versions.set_status(reel, "ready", f"Version {n} is ready", version=n)
    log(f"final      kept as version {n} (output/versions/v{n:03d})")
    return out, checks


def _stage_final(reel, preview=False, frame="cover", focus_x=0.5, loudness=True):
    """Render the branded reel: captions, graphics, zooms, sound effects."""
    from .brand import effective
    brand = effective(reel.root)   # saved defaults + this reel's own changes
    if not brand:
        raise RuntimeError("No brand profile yet. Run brand onboarding first.")
    # A test brand ($LAINE_BRAND_DIR) may only render test reels, never into a
    # customer's real reel folder.
    if os.environ.get("LAINE_BRAND_DIR") and "_tests" not in reel.root.parts \
            and "selftest" not in reel.root.name:
        raise RuntimeError("A test brand profile is active; it can only render reels in "
                           "workspace/_tests/. Unset LAINE_BRAND_DIR to use the real profile.")
    edit_path = reel.path("edit.json")
    edit = read_json(edit_path) if edit_path.exists() else {}
    if edit.get("version", 1) < 2:
        edit = stage_design(reel, brand)
    edl = read_json(reel.path("edl.json"))
    fps = float(Fraction(str(edl.get("fps", config.OUTPUT["fps"]))))
    if not reel.video_out.exists():
        raise RuntimeError("Render the clean cut first (reel.py recut).")

    # 1. where is the face (on the output timeline)?
    fpath = reel.path("faces.json")
    if not fpath.exists() or fpath.stat().st_mtime < reel.video_out.stat().st_mtime:
        write_json(fpath, faces.detect(reel.video_out, edit["duration"]))
    track = read_json(fpath)
    log(f"faces      {len(track['samples'])} samples ({track['source']})")

    # 2. where does everything go?
    _backdrop(reel, edit, brand)
    cdir = reel.root / "custom"
    edit["_custom_js"] = ({f.name: f.read_text() for f in sorted(cdir.glob("*.js"))}
                          if cdir.is_dir() else {})
    lay = layout.build(edit, track)
    for g in edit["graphics"]:
        g.pop("_luma", None)
        if lay["graphics"].get(g["id"], {}).get("backdrop", 0) > 0.7:
            log(f"WARNING    {g['id']} has no box and sits on a bright part of the frame: check it reads, "
                f"or give it \"backing\": \"box\" / another \"place\"")
    write_json(reel.path("layout.json"), lay)
    cap = lay.get("captions") or {}
    # a full-screen overlay the customer asked for covers the face on purpose
    hits = [g for g, v in lay["graphics"].items() if v.get("covers_face") and not v.get("allow_face")]
    _profile_avatars(reel, edit, track)
    _library_images(edit)
    log(f"layout     captions y={cap.get('y')} ({cap.get('why', 'none')}); "
        f"{len(lay['graphics'])} graphics placed, {len(hits)} touching the face")

    # 3. does the plan follow the saved profile? (checked on the exact page data)
    page_data = overlay.page_data(edit, lay, brand, fps)
    problems = conformance.check(edit, page_data, brand)
    warnings = conformance.font_warnings(brand)
    for w in warnings:
        log(f"WARNING    {w}")
    for pr in problems:
        log(f"PROFILE    {pr}")

    # 4. draw captions + graphics as transparent frames
    concat = None
    if edit["captions"]["items"] or any(g["type"] != "progress_bar" for g in edit["graphics"]):
        node = find_tool("node")
        if not node:
            raise RuntimeError("Node.js is needed to render captions and graphics.")
        odir = reel.work / "overlay"
        shutil.rmtree(odir, ignore_errors=True)
        odir.mkdir(parents=True)
        page = odir / "page.html"
        page.write_text(overlay.build_page(edit, lay, brand, fps))
        log("overlay    drawing captions and graphics in headless Chrome ...")
        cmd = [node, config.PROJECT_ROOT / "tools" / "render_overlay.mjs", page,
               odir / "frames", f"{fps:.6f}", f"{edit['duration']:.3f}"]
        r = run(cmd, check=False)
        if r.returncode == 5:      # Chrome stalled loading the page: one fresh retry
            log("overlay    Chrome stalled while loading; retrying once")
            r = run(cmd, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"Drawing captions and graphics failed: {(r.stderr or '').strip()[-400:]}")
        res = r.stdout
        log(f"overlay    {res.strip()}")
        concat = odir / "frames" / "frames.ffconcat"
        font_problems = conformance.check_fonts(read_json(odir / "frames" / "fonts.json"), brand,
                                                edit)
        # Face check on what Chrome actually drew, not just the planned boxes.
        rects = read_json(odir / "frames" / "rects.json")
        zooms = [dict(z, focus=lay["zoom_focus"].get(z["id"], {"x": .5, "y": .4})) for z in edit["zooms"]]
        gmap = {g["id"]: g for g in edit["graphics"]}
        for rc in rects:
            g = gmap.get(rc["id"])
            if not g or lay["graphics"].get(rc["id"], {}).get("allow_face"):
                continue
            face = layout.screen_face(track, zooms, g["start"], g["end"])
            if layout._overlap((rc["x"], rc["y"], rc["w"], rc["h"]), face) > 0 and rc["id"] not in hits:
                hits.append(rc["id"])
                log(f"FACE       {rc['id']} ({g['type']}) is drawn over the face")
        for pr in font_problems:
            log(f"PROFILE    {pr}")
        problems += font_problems

    # 5. one ffmpeg pass from the original
    out = reel.output / f"{reel.slug}-final{'-preview' if preview else ''}.mp4"
    log(f"final      compositing ({len(edit['zooms'])} zooms, {len(edit['sfx'])} sound effects)"
        f"{', preview quality' if preview else ''} ...")
    if not versions.is_snapshotted(reel, out):
        archive(out)   # a render from before numbered versions: keep it too
    composite.render_final(reel.original, edl, edit, lay, concat, out, reel.work, frame=frame,
                           focus_x=focus_x, preview=preview, loudness=loudness,
                           progress_color=brand.get("colors", {}).get("primary"))
    info = media.probe(out)
    checks = {"vertical_1080x1920": (info["width"], info["height"]) == (1080, 1920),
              "has_audio": info["has_audio"],
              "duration_matches_plan": abs(info["duration"] - edit["duration"]) <= 0.2,
              "captions_off_face": not (cap.get("covers_face")),
              "graphics_off_face": not hits,   # planned AND drawn rectangles
              "follows_brand_profile": not problems}
    reel.mark("final", file=str(out.relative_to(reel.root)), preview=preview, checks=checks,
              ok=all(checks.values()), profile_problems=problems, font_warnings=warnings)
    for k, v in checks.items():
        log(f"final      {'ok  ' if v else 'FAIL'} {k}")
    for w in warnings:
        log(f"final      WARN fonts: {w}")
    print(f"Done: {out}")
    return out, checks


def _backdrop(reel, edit, brand):
    """Text drawn straight on the footage (no box) has to sit where it reads: give
    layout a small brightness map of the frame behind each such graphic. Style
    packs only; Classic keeps its layout exactly."""
    from . import styles
    st = styles.resolve(brand)
    if st["legacy"]:
        return
    box_on = styles.decorations_on(st).get("graphic_box")
    for g in edit["graphics"]:
        boxed = g.get("backing") == "box" or (box_on and g.get("backing") != "none"
                                               and (g.get("style") or {}).get("custom_background") != "none")
        if not g.get("component") or boxed or g["type"] in ("emoji", "arrows", "image", "full_overlay"):
            continue
        t = (g["start"] + g["end"]) / 2
        import subprocess
        r = subprocess.run([str(find_tool("ffmpeg")), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", str(reel.video_out), "-frames:v", "1", "-vf",
                            f"scale={layout.LUMA_GRID[0]}:{layout.LUMA_GRID[1]},format=gray",
                            "-f", "rawvideo", "-"], capture_output=True)
        if r.returncode == 0 and len(r.stdout) == layout.LUMA_GRID[0] * layout.LUMA_GRID[1]:
            g["_luma"] = list(r.stdout)


def _library_images(edit):
    """Image graphics point at library assets: give the renderer the file."""
    from . import carousel, library
    for g in edit["graphics"]:
        if g["type"] == "carousel":
            bad = carousel.problems(g)
            if bad:
                raise RuntimeError(f"Carousel {g['id']}: " + "; ".join(bad))
            g["srcs"] = [library.path_of(a).as_uri() for a in g["assets"]]
            g["ratios"] = carousel.ratios(g)
        if g["type"] == "image" and g.get("asset"):
            p = library.path_of(g["asset"])
            if not p:
                raise RuntimeError(f"Image {g['asset']} is missing from your asset library.")
            g["src"] = p.as_uri()


def _profile_avatars(reel, edit, track):
    """Profile-card graphics get a round avatar cropped from the speaker's own
    face in the video (work/avatar-<id>.png)."""
    from .tools import require, run as _run
    for g in edit["graphics"]:
        if g["type"] != "profile_card" or g.get("avatar"):
            continue
        t = g["start"] + 0.2
        s = min(track["samples"], key=lambda x: abs(x["t"] - t))
        x, y, w, h = s["box"]
        side = max(w * 1080, h * 1920) * 1.5
        cx, cy = (x + w / 2) * 1080, (y + h / 2) * 1920
        X = int(max(0, min(1080 - side, cx - side / 2)))
        Y = int(max(0, min(1920 - side, cy - side / 2)))
        out = reel.work / f"avatar-{g['id']}.png"
        _run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}",
              "-i", reel.video_out, "-frames:v", "1", "-vf",
              f"crop={int(side)}:{int(side)}:{X}:{Y},scale=240:240", out])
        g["avatar"] = out.as_uri()


def write_report(reel):
    m = reel.manifest()
    edl = read_json(reel.path("edl.json"))
    st = edl["stats"]
    tpath = reel.path("transcript.json")
    words = read_json(tpath)["words"] if tpath.exists() else []
    cpath = reel.path("cleanup.json")
    cl = read_json(cpath) if cpath.exists() else {"candidates": []}
    verify = m["stages"].get("verify", {})

    def context(t):
        before = [w["text"] for w in words if w["end"] <= t + 0.05][-4:]
        after = [w["text"] for w in words if w["start"] >= t - 0.05][:4]
        return " ".join(before) + " ‖ " + " ".join(after)

    lines = [
        f"# Cut report: {m['name']}", "",
        f"- Source: `{m['original']}` ({st['source_duration']:.2f}s)",
        f"- Output: `{reel.video_out.relative_to(reel.root)}` ({st['output_duration']:.2f}s)",
        f"- Removed: {st['removed']:.2f}s ({st['removed_pct']}%) in {st['cuts']} cuts "
        f"({st.get('content_cuts', 0)} content), pacing **{edl['pacing']['name']}**",
        f"- Verify: {'all checks passed' if verify.get('ok') else 'see reel.json'}",
    ]
    if cl["candidates"]:
        lines += ["", "## Content cleanup", "",
                  "| Id | Type | Words | Text | Result |", "|---|---|---|---|---|"]
        for c in cl["candidates"]:
            d = c["decision"]
            if d.get("applied"):
                result = "**removed**"
            elif not c["auto"]:
                result = f"left in: {c['reason']}"
            else:
                result = f"left in: {d.get('why', '')}"
            span = f"{c['words'][0]}–{c['words'][1]}" if c.get("words") else "-"
            if d.get("quiet_join") and d.get("applied"):
                result += " (at a quiet point between words)"
            lines.append(f"| {c['id']} | {c['type']} | {span} | {c['text']} | {result} |")
    if verify.get("speech_diffs"):
        lines += ["", "## Re-transcription differences", ""]
        lines += [f"- {d['op']}: expected “{d['expected']}”, heard “{d['heard']}”"
                  for d in verify["speech_diffs"]]
    lines += ["", "## Cuts", "", "| # | Kind | Source time | Removed | Around |",
              "|---|---|---|---|---|"]
    for i, c in enumerate(edl["cuts"], 1):
        around = context(c["start"]) if words else ""
        lines.append(f"| {i} | {c['kind']} | {c['start']:.2f}–{c['end']:.2f}s | "
                     f"{c['end'] - c['start']:.2f}s | {around} |")
    reel.path("cut-report.md").write_text("\n".join(lines) + "\n")
