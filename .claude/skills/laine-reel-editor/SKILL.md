---
name: laine-reel-editor
description: Laine AI Reel Editor, the project-local AI reel editor in this folder (laine-ai-reel-editor). Use inside this project when someone says "Edit my reel", gives a raw talking-head clip to tighten into a clean vertical reel (pauses, repeated words, restarts, fillers), wants a reel re-cut with different pacing or framing, wants their brand style set up or changed ("Start my brand onboarding", "set up my brand", first use), wants a captions/zooms/graphics/sound plan, says "Update my reel editor", or asks to check the editor's setup. If another reel-editing skill is installed on this computer, use this one inside this project and never the other one's scripts or folders.
---

# Laine AI Reel Editor

Turns a raw talking-head clip into a clean 1080x1920 MP4: dead air removed,
natural pauses kept, repeated words / restarts / fillers cleaned up, meaning
untouched. Everything happens inside this
project; follow the isolation rules in `CLAUDE.md`.

All commands run from the project root.

## "Edit my reel": the whole flow

When they say "Edit my reel" (or hand over a raw clip), follow these steps in
order. Never use another project's or a test brand's settings: `edit` and
`finish` refuse to run with a test brand active.

**No brand yet?** If `python3 scripts/reel.py brand status` says `Profile: not yet`,
say so and offer brand onboarding first (section 2, recommended, about 10 minutes).
If they'd rather go ahead, the reel uses the clean neutral look (`brand/neutral.json`:
white captions, no headline, no sounds). That look is never pinned to the reel, so
once they finish onboarding, the next "apply my review" uses their brand.

1. **Get the clip.** Ask for the path if not given. It must be a NEW raw video;
   a path inside a protected folder (`protected_paths` in `config/settings.json`) is refused, so ask them to
   copy it elsewhere. Pick a short name from what it's about.
2. **Cut and plan**:
   `python3 scripts/reel.py edit "<clip>" --name <short-name>`
   This checks the brand and tools, transcribes, removes pauses, fillers and
   obvious repeats (audio-safe only), checks no words were lost, renders the
   clean cut, and plans captions, zooms, graphics and sound from their brand.
   Read the output. If checks failed, stop and say why.
3. **Content review** (section 4 below): `reel.py words <reel>`. Add a
   `cleanup.review.json` only for clear meaning-level fixes; if you do, re-run
   `reel.py recut <reel> --check-speech`.
4. **Headline** (if their brand has one). From the opening words it prints,
   write 3 short options (6 words max, their words, their caption case),
   **strongest first**, to `workspace/<reel>/review/suggestions.json` as
   `{"headlines": [...]}`. Ask with AskUserQuestion: the 3 suggestions plus
   "✨ Choose for me" as options ("Other" lets them type their own).
5. **Render version 1**:
   `python3 scripts/reel.py finish workspace/<reel> --headline "<their choice>"`
   or, for "Choose for me", `--choose-for-me` (uses the strongest suggestion)
   (about 1-2 minutes). Then look at 4-5 frames (headline, a caption, each
   graphic) with ffmpeg + Read before showing anything.
6. **Open the review page**: run `python3 scripts/reel.py review workspace/<reel>`
   **in the background**. It replaces the previous reel's page and opens
   http://127.0.0.1:8765/ in their browser. Tell them: watch, pause, add notes
   or use the tabs, **Save feedback**, then say "apply my review".
7. **Each "apply my review"** (section 7): `apply-review`, handle the notes,
   `recut --check-speech` if it said so, then `final`. The new version appears on
   the same page by itself. Repeat until they press **Finalize & Download**
   (never press it for them).

## Brand settings and the asset library (any time)

- **Brand settings**: the review page's **🎛 Brand settings** button. Every brand
  choice (colours, fonts, captions, headline, graphics, zooms, sounds, logo) with
  "This reel only" (saved in `workspace/<reel>/brand.answers.json`) or "My saved
  defaults" (updates `brand/`; the earlier set goes to `brand/history/`, listed under
  "Earlier saved defaults" with **Restore**; `reel.py brand history` / `brand restore <id>`).
  Each reel keeps the brand it was made with (`brand.snapshot.json`), so default
  changes never alter older reels unless they press "Use my current saved defaults
  for this reel" (`reel.py brand use-defaults <reel>`). Saved changes show up
  after "apply my review" (it re-plans; it re-cuts if pacing changed). In chat:
  `brand.save_settings({...}, "reel"|"default", reel_root)`. Never change defaults
  unless they chose that.
- **Asset library**: the page's **📁 Library** tab (or
  `python3 scripts/reel.py library add <file> --name ... --category ...`). Fonts
  (TTF/OTF), sounds (MP3/WAV), images (PNG/JPG), stored in `assets/library/`. Name,
  categorise, preview, archive (never deleted). **Use at** puts a sound or image
  at the current moment. Uploaded fonts appear in Brand settings fonts; sounds in
  Brand settings → Sound (per moment: headline, pop-ins, emoji, zooms, CTA,
  checklist ticks); images as Logo or at a timestamp.
- Their chosen sounds are used **exactly**: if one goes missing, the render
  fails `follows_brand_profile` rather than using a default. Uploaded sounds are
  level-matched to the built-in pack (peak −3 dB) before the brand gain.

## Update my reel editor

1. `git status --short`. Their brand, uploads, reels, settings and models are git-ignored,
   so only editor files can show up. If editor files were changed, ask before discarding.
2. `git pull --ff-only`, then `./install.sh --check`.
3. Tell them what's new from `CHANGELOG.md`. Nothing of theirs changes.

## 1. Check the setup (once per machine, or when something fails)

```bash
python3 scripts/reel.py doctor
```

Every line marked `MISS` must be fixed before editing; see `DEPENDENCIES.md`.
Never install, upgrade or download anything without asking the customer first.
`./install.sh` fixes missing tools and asks before each step; `./install.sh --check` only reports.
`drawtext` / `subtitles` showing `--` is expected: this editor never uses them.

## 2. Brand onboarding (first use, or "set up / change my brand")

Run it when `python3 scripts/reel.py brand status` says `Profile: not yet`,
before the first edit. Pausing is fine: answers are saved as they come
(`brand/onboarding.json`), and `brand next` resumes where it stopped.

The loop, **one question per message**:

1. `python3 scripts/reel.py brand next --json` gives the next question:
   `id`, `prompt`, `options`, `help`, `number`/`total`, `optional`.
2. Ask it warmly in your own words, with "Question 3 of 19". If it has 2-4
   options, use AskUserQuestion with those labels. Otherwise list the options
   numbered in chat. Free-text questions (colours, fonts, personality) go in chat.
3. Save exactly what they said: `python3 scripts/reel.py brand answer <id> "<their words>"`.
   If it prints `NOT SAVED: ...`, explain that message kindly and ask again.
   Never invent an answer or skip a required question.
4. Repeat until `brand next` prints `DONE`.

Notes:
- Colours: accept hex or names; the first is the main colour, the second the
  highlight colour. If they only give one, ask if they want a highlight colour.
- Reference reel: optional. A path inside a protected folder is refused; ask
  them to copy the file elsewhere. Never touch the original.
- To change one thing later: `brand answer <id> "..."` then `brand finish`.

Then `python3 scripts/reel.py brand finish`. It measures the reference reel
(cuts/min, words/min, loudness, plus a contact sheet at
`brand/reference/contact-sheet.png`; look at it with Read and describe the
caption placement and graphic style you see) and writes `brand/brand.json` +
`brand/brand.md`. Read the summary back. If the reference suggests a
different pacing or zoom frequency than they chose, mention it once and let
them decide. If a font isn't installed, say so; they can add the .ttf/.otf to
`assets/fonts/` (Google Fonts are free). **Ask before downloading anything.**

## 3. Edit a clip

```bash
python3 scripts/reel.py run "<path to clip>" --name <short-name> --check-speech
```

- The raw clip is only read. A read-only copy goes to
  `workspace/<date>-<name>/source/`; everything else is written next to it.
- `--pacing natural|tight|fast` (default: `brand/brand.json` "pacing", else natural).
- `--frame cover` (crop to fill, default) or `--frame blur` (whole frame on a
  blurred fill, for wide shots). `--focus-x 0..1` moves the crop left/right when
  the speaker is off-centre.
- `--preview` for a fast draft encode.
- `--check-speech` re-transcribes the result and fails if words were lost.
  Use it for every final render.

## 4. Review the content cleanup (your judgement, the engine's safety)

The engine already removes the obvious cases: repeated phrases ("some of
y'all, some of y'all, some of y'all" -> the last, complete one), fillers
(um/uh), and cut-off restarts ("real- the real"). Now read the transcript for
what needs judgement:

```bash
python3 scripts/reel.py words workspace/<reel>
```

Look for:
- **Abandoned sentences**: a sentence that starts, stops and is replaced by a
  different one ("So what you want to- Here's the thing.").
- **Self-corrections**: "on Tuesday, I mean Wednesday" -> remove "Tuesday, I mean".
- **Engine mistakes**: a removed repeat that was actually deliberate emphasis.

Rules - follow them exactly:
- Never change the meaning. Never remove a word that carries information.
- Keep complete sentences. The kept words must read as natural speech.
- Keep their voice: "y'all", "like", "okay", "you know" used as style stay in.
- **If unsure, leave it in.** An awkward edit is worse than a repeated word.

If (and only if) there is something to change, write
`workspace/<reel>/cleanup.review.json`:

```json
{
  "remove": [{"from": 12, "to": 14, "type": "self_correction", "reason": "Tuesday, I mean -> Wednesday"}],
  "keep": ["c3"]
}
```

`from`/`to` are word numbers from `words` (inclusive); `keep` lists engine
candidate ids to put back. Then `recut`. The engine still refuses any cut
whose ends don't land in measured silence and says so in `cut-report.md`;
never try to force those.

## 5. Review the edit plan (captions, zooms, graphics, sound)

With a brand profile, every edit also writes `edit.json` + `edit-plan.md`
(regenerate any time with `python3 scripts/reel.py plan workspace/<reel>`).
Read `edit-plan.md` as an editor would:

- **Headline first**: the headline (`role: headline`, from the profile's
  headline setting, drawn in the headline font) starts as a `draft` = the first
  line. Propose 2-3 short options (6 words max, their voice, only what they
  actually say, matching their caption case) and **let them choose** before
  rendering. `final` fails `follows_brand_profile` while it is still a draft.
- Graphic text must match what is said at that moment. Cut anything that
  repeats the caption word-for-word without adding anything.
- Zooms and graphics should feel like their profile (soft luxe = calm,
  bold = punchy). Remove any that land awkwardly.

Make changes in `workspace/<reel>/edit.overrides.json` (it survives re-planning),
then run `plan` again:

```json
{"set": {"g1": {"text": "Your camera isn't the problem"}}, "remove": ["g3", "z4"]}
```

Check emoji choices against meaning (📸 for "camera angle", not 📐). Swap
any that read too literally with `set`.

## 6. Render the branded reel

```bash
python3 scripts/reel.py final workspace/<reel> --preview   # ~1 min draft
python3 scripts/reel.py final workspace/<reel>             # high quality, a few minutes
```

It finds the face (Apple Vision; estimated if not on a Mac), places captions
and graphics around it (including while zoomed in), draws them in headless
Chrome as transparent frames, and composites everything with the 4K original
in one ffmpeg pass: zooms toward the face, sound effects, music. Output:
`output/<name>-final.mp4`.

`final` also checks `follows_brand_profile` (every caption setting, colour,
font, headline and graphic type against `brand/brand.json`) and prints a
WARNING for each brand font drawn with a stand-in. Report both honestly.

**Never render with a test brand into a real reel.** `$LAINE_BRAND_DIR` test
profiles only render reels inside `workspace/_tests/`. Only show the customer
videos made from *their* profile; label anything else clearly.

**Always look before you show it**: grab frames at the graphics and zoom
times (`ffmpeg -ss <t> -i <final> -frames:v 1 frame.png`) and Read them. Check:
nothing on the face, text readable at phone size, graphics match what's
being said. `layout.json` explains every placement; `final` checks
`captions_off_face` and `graphics_off_face`.

Sound effects come from `assets/sfx/` (customer's own files win) or the
generated pack in `assets/sfx/generated/`. Fonts come from `assets/fonts/`;
if the brand font isn't there, a close system font is used. Say which.

## 7. Customer review (the review page)

After a render, offer the review page. First write 3 headline suggestions
(6 words max, their words and voice, their caption case) to
`workspace/<reel>/review/suggestions.json` as `{"headlines": [...]}`.
Without it, the page falls back to weak first-line suggestions.

```bash
python3 scripts/reel.py review workspace/<reel>
```

This opens http://127.0.0.1:8765/ in their browser. It's local only, and
serves and writes only inside that reel folder. Leave it running in the
background while they review. On the page they can add timestamped notes;
put back or remove cuts and shorten long pauses; fix caption spelling and
timing; pick an AI headline or write their own; restyle, retime or remove
graphics; and add graphics, zooms and sounds. Drafts autosave. **Save
feedback** writes `review/feedback-<time>.json`.

When they say "apply my review":

```bash
python3 scripts/reel.py apply-review workspace/<reel>
```

This applies the structured changes into per-reel files only
(`cleanup.review.json`, `transcript.fixes.json`, `edit.overrides.json`).
**Never touch `brand/`**. Previous versions go to `review/history/`.
Then handle each printed **note** yourself. Write your interpretation as a
feedback file `review/feedback-<time>-claude-notes.json` (with
`"from_notes_of"` and an `"interpretation"` line per note) and apply it with
`review.apply_feedback`, so there's a record. Page options cover most notes:
`graphics.<id>`: `background`, `color`, `font`, `animation`, `paper: lined`,
`checks: true` (tick boxes + clicks), `place: above_head` / `top`,
`background: none` (text only, outlined), `font: bulky`; new graphic types
`full_overlay` (`text`, `opacity`; covers the frame on purpose, hides captions
under it) and `profile_card` (handle, avatar cropped from their video,
placeholder stats: never invent follower numbers). To change a graphic's type
or a sound, set it in `edit.overrides.json` (`set.<gid>.type` + `source: review`,
`set.<sfx id>.kind`); `cuts.cut_pauses`
(word index before the pause; also removes breaths and mic clicks inside the
pause). Anything else goes in 
`edit.overrides.json` (`add` / `set` / `remove_match`, with `src_start`
times so they follow the speech). If a note is ambiguous, ask. Then:

```bash
python3 scripts/reel.py recut workspace/<reel> --check-speech   # only if it said "recut"
python3 scripts/reel.py final workspace/<reel>
```

Every final render becomes the next numbered version (`output/versions/vNNN/`).
The review page shows "Rendering…" while you work and loads the new version
by itself. The customer can keep going round (watch, notes, save, "apply my
review") as many times as they like, compare or restore any version, and press
**Finalize & Download** when they're happy. Never press Finalize for them: it
approves the video and downloads a file.

Times on the page belong to the version they were watching; apply-review maps
them with that version's cuts. To see what's said at a page time:
`python3 scripts/reel.py locate workspace/<reel> 31.0 --version 1`. Check frames for every change before
showing the new version, and tell them which notes you applied and how.

## 8. Show the result

Read `workspace/<reel>/cut-report.md` and summarise: old length -> new length,
what content was removed (quote it), what was left in and why, and the verify
results. `cleanup_joins_clean` must pass: it re-transcribes the output and
checks no word was clipped at a cleanup join. Give the path to
`output/<name>-vertical.mp4`.

Ask whether the pacing feels right. Then:

```bash
python3 scripts/reel.py recut workspace/<reel> --pacing tight   # or natural / fast
python3 scripts/reel.py recut workspace/<reel> --frame blur --focus-x 0.4
python3 scripts/reel.py recut workspace/<reel> --use-edl        # render a hand-edited edl.json as is
python3 scripts/reel.py recut workspace/<reel> --no-cleanup     # pauses only, keep every word
python3 scripts/reel.py recut workspace/<reel> --retranscribe   # re-run whisper (after engine updates)
```

`recut` reuses the transcript and silence data, so it is quick.

## 9. If something goes wrong

- Verify `FAIL cleanup_joins_clean`: the diff is in `cut-report.md`. Veto that
  candidate with `"keep"` in cleanup.review.json and recut.
- Verify `FAIL duration_matches_plan` or `speech_preserved`: open `edl.json`
  and `silences.json`; a noisy room may need a different threshold
  (`stage_silences(noise_db=...)` in `scripts/laine_reel/pipeline.py`).
- No whisper model: suggest `./install.sh`, which asks before downloading it (see DEPENDENCIES.md).
- Run the tests after any code change:
  `python3 -m unittest discover -s tests` and `python3 tests/selftest.py`.

## Not built yet

Live preview of graphic edits on the review page (changes show after the re-render). See `docs/ARCHITECTURE.md` for where each one
plugs in. Don't improvise them with ffmpeg `drawtext`/`subtitles`; they are not
available on this machine and are not part of the design.
