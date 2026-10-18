# Architecture

## Phase 1 pipeline

```
raw clip ─► ingest ─► audio ─► transcribe ─► silences ─► align ─► plan ─► render ─► remap ─► verify
            (copy,    (16 kHz   (whisper.cpp  (ffmpeg     (snap     (cut    (ffmpeg   (words   (checks +
            read-only) mono)    + DTW)        silence-    words to  list)   trim/     onto     optional
                                              detect)     speech)           concat)   output)  re-transcribe)
```

| Stage | Module | Writes |
|---|---|---|
| ingest | `project.py` | `source/original.<ext>` (read-only), `reel.json` |
| audio | `media.py` | `work/audio16k.wav` |
| transcribe | `transcribe.py` | `work/whisper.json` (raw), `transcript.json` |
| silences | `media.py` | `silences.json` |
| align | `align.py` | updates `transcript.json` word times |
| plan | `pauses.py` | `edl.json` |
| render | `render.py` | `output/<name>-vertical.mp4`, `work/filtergraph.txt` |
| remap | `timeline.py` | `transcript.cut.json` |
| verify | `pipeline.py` | `reel.json` → `stages.verify`, `cut-report.md` |

The orchestrator is `scripts/laine_reel/pipeline.py`; the CLI is `scripts/reel.py`.
Every stage records itself in `reel.json`, so stages can be re-run independently
(`recut` re-runs plan → verify without transcribing again).

## Key design decisions

**Audio energy decides where to cut, not whisper.** whisper.cpp recognises words
well, but its timestamps drift (in testing, the first word was placed 1.3 s too
early, and a full stop "owned" a whole 1.8 s pause). Cuts happen only inside
silence measured by ffmpeg `silencedetect`, and only remove the part of a pause
beyond the pacing's `keep_pause`. Speech audio is never cut.

**Adaptive threshold.** Silence = quieter than the clip's mean volume − 14 dB,
clamped to −50…−28 dBFS. That handles quiet and loud recordings without tuning.

**Word timing (caption sync).** Measured against ground truth
(`tests/sync_bench.py`: speech built word by word with macOS `say`, so every
word's real start is known), whisper.cpp's DTW word times run **~0.28 s late**
(median +0.27 to +0.31 s, both test voices). The pipeline: (1) subtract that
calibrated lag (`transcribe.DTW_LAG`), (2) snap words into speech regions,
(3) words after a pause start at the pause's end, (4) words mid-phrase start at
the loudness dip between words (`align.refine_starts`, 10 ms envelope read
with Python's `wave`). Result: median error 0.00 s, mean 0.03 s, versus 0.27–0.31 s
before. The self-test re-runs this benchmark and fails if the median drifts past
±0.04 s. Recalibrate `DTW_LAG` with the benchmark if the model changes.

**Older notes on alignment.** whisper.cpp runs with `-dtw <model>`
(and `-nfa`, which DTW needs) for accurate word starts. `align.py` then moves any
word that still sits in measured silence into the nearest speech region. With
both, 1 of 34 test words needed correcting (14 without DTW). Finally
`align.snap_onsets` starts each word where the audio shows the voice begins
(a silence/gap ends just before it), because whisper's starts still ran late:
on the real clip, 10 of 54 words after a pause lagged > 0.15 s, now 0.
Captions also appear 0.08 s early (`CAPTION_LEAD`), which reads as in sync.

**Frame-accurate cuts.** Video is converted to a constant 30 fps first, and every
cut boundary is snapped to that frame grid, so audio and video segments have
identical lengths and A/V sync can't drift across many joins. Each join gets an
8 ms audio fade to prevent clicks.

**Safety net.** `--check-speech` re-transcribes the output and compares word
sequences (must be ≥ 90 % similar; the test clip scores 100 %).

**Original preserved.** The input file is only read. A copy is hashed, made
read-only, and its hash re-checked at verify time.

## Content cleanup (Phase 1.5)

`cleanup.py` finds repeated phrases, fillers and cut-off restarts in the
transcript. Claude can add meaning-level edits (abandoned sentences,
self-corrections) or veto engine ones in `cleanup.review.json`. Every
candidate then has to pass the audio: both ends of the cut must land in a gap
measured by `silencedetect` (≥ 30 ms), and the speech between the gaps must
match the words removed. Otherwise it stays in, and `cut-report.md` says why.
Verify re-transcribes the output and fails if any difference sits at a
cleanup join.

## Brand onboarding (Phase 2)

```
Claude (skill) ──ask one question──► customer
      ▲                                  │ answer
      │ next question / NOT SAVED: why   ▼
reel.py brand next | answer ──► brand.py ──► brand/onboarding.json (progress, resumable)
reel.py brand finish ─────────► brand.py + reference.py ──► brand/brand.json + brand/brand.md
```

- `brand.py` holds the 19 questions in 7 sections, with conditions (no
  captions means no caption questions). It parses free answers (colour names,
  hex, "option 2", labels) and compiles the profile: palette roles, readable
  text colours (WCAG contrast), font files found on disk, caption sizes,
  zoom scales/spacing, graphics density, sfx events and aesthetic style tokens.
- `reference.py` measures an optional reference reel: cuts/min (per-frame
  scene scores with a peak test, so jump cuts in a static shot count and
  gestures don't; calibrated on our own edit: 10/10 joins found, 0 false hits
  in 95 s of raw footage), words/min via whisper, loudness, plus a contact sheet.
- Each project install keeps its own profile in `brand/`. Re-finishing keeps
  `brand.previous.json`. Paths in `settings.json` `protected_paths` are refused.

## Edit plan (Phase 2)

`planner.py`: brand profile + `transcript.cut.json` (output timeline) + cut
points → `edit.json` + `edit-plan.md`. Runs automatically after every edit
once a profile exists, or via `reel.py plan <reel>`.

| Layer | How it's planned |
|---|---|
| Captions | Chunked per style (word pop / karaoke / lines / keyword boxes) with a line breaker that scores every split (fits the width; no line ending on "the"/"to"; no orphan words; names kept together; breaks at commas and pauses). One emphasis word per sentence. Sentence-case repair after cleanup cuts. Safe-zone y positions. |
| Zooms | Snap punch-ins on jump cuts (hides them), slow pushes on hook / CTA / questions, extra punches on key lines for "frequent". Released only at a cut or sentence end; never shorter than 1.5 s; never overlapping; spaced by frequency. |
| Graphics | Only the elements the customer chose. Triggers from the transcript: hook title (draft for Claude), runs of questions → sticky note / checklist, named things → key-phrase card, numbers → callout, CTA ("comment X") → end card, emoji on emphasis words, progress bar. Placed in the zone opposite the captions, with density cap and breathing room. |
| Sound | Whoosh on punch zooms, pop on graphics, ding on CTA, per profile; ≥ 1.2 s apart. Music bed with ducking. Files come from `assets/sfx/` (flagged `needs_asset` until added). |

Claude reviews `edit-plan.md` and adjusts through `edit.overrides.json`
(`set` / `remove` by id), which survives re-planning. `render_requirements`
in `edit.json` lists the method and ffmpeg filters for every layer, checked
against this machine. Examples: `docs/examples/`.

## Branded render (Phase 3)

```
clean MP4 ──► faces.py (Vision via osascript, 2 samples/s) ──► faces.json
edit.json + faces.json ──► layout.py (cost-based, face-aware) ──► layout.json
edit.json + layout.json + brand ──► overlay.py ──► work/overlay/page.html
page.html ──► tools/render_overlay.mjs (headless Chrome, CDP) ──► transparent PNGs + ffconcat
original + edl + zooms + PNGs + sfx ──► composite.py (one ffmpeg pass) ──► output/<name>-final.mp4
```

- **Text without drawtext**: every caption and graphic is HTML/CSS (real
  fonts, emoji, shadows, SVG arrows) on a transparent 1080×1920 page with a
  deterministic `__seek(t)` timeline. Chrome screenshots only frames whose
  visual state changed (~50 % of frames for one-word captions), and an
  ffconcat file holds each image for as long as it's unchanged.
- **Face-aware layout**: the face box (union over the element's time window,
  enlarged by any active zoom) is a hard no-go. Hair is a soft cost, so
  graphics tuck over the hairline instead of shrinking. Graphics never stack.
  Captions take one position for the whole reel. Platform UI strips (bottom
  caption area, right-hand buttons) are avoided. The reasoning for each
  placement is in `layout.json`.
- **Zooms** happen on a 2160×3840 frame (from the 4K original) before
  downscaling, centred on the face, so punch-ins stay sharp and pushes don't
  jitter. Snap zooms use a constant scale; pushes use smoothstep easing.
- **Sound**: voice (−14 LUFS) + each effect (`adelay` + `volume`) mixed with
  `amix`, then `alimiter`. Music is ducked under the voice with `sidechaincompress`.
- **Follows the profile**: `conformance.py` compares the exact page data with
  `brand/brand.json` (caption settings and colours, headline type, graphic
  types, fonts, sticky-note font) and fails `follows_brand_profile` on any
  mismatch, including an unreviewed draft headline. Stand-in fonts are
  reported as warnings. A test brand (`$LAINE_BRAND_DIR`) can't render into a
  real reel folder.
- **Meaning drives timing**: everything comes from the plan, which is built from
  the words (questions → sticky note filling in as each is asked; "comment"
  → arrow to the comment button on that word; emphasis words → emoji; cuts
  → zooms that hide them).

## Review (Phase 4)

```
reel.py review ──► review_server.py (127.0.0.1, stdlib) ──► tools/review/ (HTML/CSS/JS, no libraries)
   page ──POST /api/draft──► review/draft.json        (autosave)
   page ──POST /api/feedback─► review/feedback-<time>.json  (never overwritten)
reel.py apply-review ──► review.py ──► cleanup.review.json   (cuts: keep / remove / pause cuts)
                                   ──► transcript.fixes.json (caption spelling + timing)
                                   ──► edit.overrides.json   (headline, graphic edits, additions)
                                   ──► notes for Claude
recut (if cuts/captions changed) ──► final ──► output/<name>-final.mp4 (old one -> output/versions/)
```

- **Brand stays put**: a review only writes per-reel files. `brand/` is never touched.
- **Caption fixes change display, not cut decisions**: a fixed word keeps
  `heard` (what whisper heard), which cut detection uses.
- **Requested pause cuts** stay inside measured silence. Because the customer
  asked, they may also remove short non-speech sounds (≤ 0.15 s breaths)
  between the two words. Verify checks the pause really got shorter.
- **Requested items follow the speech**: additions store their source time
  (`src_start`), so a later re-cut moves them with the words.
- **Graphic edits survive re-plans**: matched by type + nearby start
  (`_match`), not just id; styles are merged. Customer styles
  (`custom_background`, `custom_text`, `custom_font`, `animation_in`) win in the
  renderer, and the font check accepts them.
- **Extra styles from review**: lined notebook paper (`custom_paper: lined`),
  tick boxes that check as each line appears with a generated mouse-click
  (`checks`; the clicks are generated from the items at plan time so they
  can't drift), and `place: above_head` for emoji / small graphics.
- **Versions**: every final render becomes `output/versions/vNNN/` (the video,
  hard-linked, plus the exact edit state that made it and `meta.json`). The page
  can watch, compare side by side, **restore** (state and video come back; the
  replaced state goes to `review/history/<time>-before-restore/`), and
  **Finalize & Download** (copies to `output/approved/`, marks the version approved,
  and serves it as a download).
- **Drawn = checked**: a graphic is never drawn bigger than the box layout
  approved (scaled to fit, position kept). After rendering, Chrome reports each
  graphic's real rectangle (`rects.json`) and `graphics_off_face` checks those
  too. A full-screen overlay the customer asked for is the only thing allowed
  over the face.
- **Live page**: `review/status.json` (working / waiting / ready / error) is
  written by apply-review, recut and final. The page polls `/api/status` every
  3 s and loads the newest version by itself when it's ready.
- **Timestamps you can trust**: feedback records which version was being
  watched. Times are mapped to the original footage with *that version's* cut
  list, so a request lands on the same words even if the reel was re-cut since.
  Pause and word requests are stored by word index; additions and retimed
  graphics carry source times. "Remove the pause here" picks the gap between
  the words nearest the playhead. A requested pause keeps only a 0.12 s breath.
  `reel.py locate <reel> <t> [--version N]` shows what's said at a page time.
- **History**: every applied feedback file records what was applied, and the
  files it replaced are copied to `review/history/<time>/`. Every replaced
  render is copied to `output/versions/`.
- **Server safety**: binds to 127.0.0.1 only. `/media/` serves only `.mp4/.png/.jpg`
  inside the reel folder (path traversal → 404). Byte ranges let the player seek.

## Brand settings and asset library (Phase 5)

- `library.py`: `assets/library/` with `library.json`. Uploads are checked by
  magic bytes, size, and by reading them (ffprobe for sounds and images, the
  font's `name` table for fonts: no libraries). Sounds store their peak level,
  so they're level-matched at mix time. Nothing is deleted (archive instead).
- Brand settings = onboarding answers plus extra keys `font_files`,
  `graphics_font`, `sound_map`, `logo`. **Defaults**: answers updated and the
  profile recompiled (`brand.previous.json` kept). **This reel only**:
  `<reel>/brand.answers.json`, merged over the defaults by `brand.effective()`,
  which is what planning, rendering, review and the brand check all use.
- Rendering: library fonts become `@font-face` rules (captions = text font,
  headline = headline font, other cards = graphics font); `sound_map` sounds
  replace the built-in sound for that moment exactly (missing → check fails,
  never a default); the logo is placed first in a corner clear of the face;
  images can be requested at timestamps (`type: image`, `asset`).
- Placement: the face is a hard rule (any clear spot at any allowed size beats a
  spot on the face). `tests/assets_render_check.py` renders a test reel and
  checks the font, sounds (by frequency), logo and image in the MP4 itself.

## Two timelines

- *Source timeline*: `transcript.json`, `silences.json`, `edl.json` (times in the original clip).
- *Output timeline*: `transcript.cut.json`, and every future layer in `edit.json`.

`timeline.py` converts between them (`source_to_output`, `remap_words`). All
future layers are timed on the output timeline, so they don't need to know
about cuts.

## Without drawtext / subtitles

This machine's FFmpeg (and many others) has neither the `drawtext` nor the
`subtitles`/`ass` filter. The editor is designed never to need them:

1. Text and graphics are drawn **outside** FFmpeg, as transparent frames:
   a PNG sequence with alpha, or a single `qtrle` / ProRes 4444 `.mov` with alpha.
   (Both decoders are present.)
2. FFmpeg composites them with the `overlay` filter, which every build has.

This also gives full control over fonts, animation and brand styling, which
`drawtext` can't do well anyway.

## Where the next phases plug in

All layers are now planned in `edit.json` (Phase 2), timed on the output
timeline. The next phase adds one **composite render** stage after `design`:
the clean MP4 is the base layer, and each planned layer is drawn and mixed on top.

| Feature | Plan | FFmpeg filters (all present) |
|---|---|---|
| **Captions** | Group words from `transcript.cut.json` into lines; render caption frames in a headless browser (HTML/CSS = full brand fonts and animation) via Node, as alpha PNGs or a `qtrle` MOV; composite. | `overlay` |
| **Animations / branded graphics** | Same renderer as captions; cards in `edit.json` → `graphics[]` with `start`, `end`, `type`, fields. | `overlay` |
| **Zooms / punch-ins** | `edit.json` → `zooms[]` (`start`, `end`, `scale`, `focus`); per-segment `scale`+`crop` with time expressions, or `zoompan`. | `crop`, `scale`, `zoompan` |
| **Sound effects / music** | `edit.json` → `sfx[]` (`file`, `at`, `gain`), `music` with ducking under speech. Files in `assets/sfx/`. | `adelay`, `amix`, `volume` |
| **Interactive review page** | Local web page (served from this project only) that reads `transcript.json`, `edl.json`, `silences.json`; lets the customer tap words/pauses to keep or cut and preview; writes `edl.json` back. Then `reel.py recut <reel> --use-edl`. | – |
| **Filler-word removal** | Already detected (`transcript.json` → `fillers`); needs review UI before cutting, since whisper timing on fillers is unreliable. | – |

`edl.json` is the hand-off format between the planner, the review page and the
renderer; `--use-edl` already renders a hand-edited one as is.
