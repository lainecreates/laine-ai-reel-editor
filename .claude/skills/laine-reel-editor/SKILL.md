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
4. **Creative plan** (section "Creative plan" below): `python3 scripts/reel.py creative-context
   workspace/<reel>`, then write `workspace/<reel>/creative.json` and check it with
   `python3 scripts/reel.py plan workspace/<reel>` until it says "Creative plan used".
   This is where you decide what appears on screen and why. `finish` won't render
   without it (unless the customer explicitly wants the old automatic rules: `--rules`).
5. **Headline** (if their brand has one) - **don't ask**. The plan's hook is the
   headline: write the strongest one there (6 words max, their words, their caption
   case). Also write it plus 2 alternatives, strongest first, to
   `workspace/<reel>/review/suggestions.json` as `{"headlines": [...]}` so the review
   page can offer them. If the customer gave a headline in their request, use theirs.
6. **Render version 1**:
   `python3 scripts/reel.py finish workspace/<reel>` (it uses the plan's hook) or, only
   when they supplied one, `--headline "<their words>"` (about 1-2 minutes). Then look at
   4-5 frames (headline, a caption, each graphic) with ffmpeg + Read before showing
   anything. Tell them the headline you chose; they can change it on the review page.
7. **Open the review page**: run `python3 scripts/reel.py review workspace/<reel>`
   **in the background**. It replaces the previous reel's page and opens
   http://127.0.0.1:8765/ in their browser. Tell them: watch, pause, add notes
   or use the tabs, **Save feedback**, then say "apply my review".
8. **Each "apply my review"** (section 7): `apply-review`, handle the notes,
   `recut --check-speech` if it said so, then `final`. The new version appears on
   the same page by itself. Repeat until they press **Finalize & Download**
   (never press it for them).

## Creative plan (you are the creative director)

The editor no longer decides graphics by keywords. You read what is said and
decide, in `creative.json`, what deserves to be on screen. The style pack decides
how it looks; the engine checks your plan and keeps captions word-accurate.

1. `python3 scripts/reel.py creative-context workspace/<reel>` gives the numbered
   transcript (word numbers are what you reference), the style and its direction
   in the customer's words, their creative rules, brand choices, the intents
   allowed, density (max graphics) and text limits.
2. Understand the reel first: what is the message, who is it for, what are the
   beats (hook, setup, points/steps, proof, contrast, question, payoff, CTA)?
3. Choose moments - few and purposeful. Each must earn its place:
   - **hook**: the opening promise (required when the brand shows a headline).
   - **list** / **question_list**: when they actually enumerate (first/second/third,
     a run of questions). Items appear as each is said (`at_word`).
   - **stat**: a number that matters, exactly as said ("80%").
   - **key_phrase**: the one line that carries a point, a contrast ("it's not X, it's Y")
     or the payoff. Not every sentence.
   - **cta**: when they ask for an action (comment, follow, save, link).
   - **quote**: a line worth framing in their own words (a belief, a lesson, a mantra).
   - **contrast**: an explicit before/after or myth/truth ("not X, Y"): give `"before"` and
     `"after"` (each 5 words max, their words) as well as `text`.
   - **tip**: one practical instruction they give ("film near a window").
   - **reaction** (emoji) only when it adds feeling or humour; **pointer** only when
     they point ("look at this", "comment below").
   - **Nothing**: personal stories, emotional moments, and anything the face says
     best get no graphic. Write them in `no_graphics` with a why. Never fill space.
4. On-screen text: short enough to read at a glance (the context lists limits),
   built from their own words - shorten and tighten, never invent facts, claims or
   numbers. Spoken captions are never changed. If the customer gave exact wording,
   use it with `"source": "customer"`.
5. `key_words`: the words that carry the meaning (nouns, numbers, contrast, the
   payoff) - at most one or two per sentence. They drive caption highlighting.
6. **Designs (variety across reels).** Each style has several designs per intent
   (`designs.by_intent` in the context, with what this customer's recent reels used).
   Optionally give a moment `"design": "<id>"` when one suits the content better
   (a percentage suits a bar or line; a big number suits a cover) or to avoid repeating
   the look of their last reels. Keep one design per intent within a reel unless
   there's a reason. Without `design`, the editor picks the one their recent reels
   in this style used least (never at random). Colours, fonts and their rules apply
   to every design. Classic reels have no designs and never change.
7. **Composition (per moment, for this footage).** Nothing has a fixed slot. Without
   `"place"`, the editor picks the best clear spot: it moves text rather than shrinking it,
   goes lower when the person sits high in the frame, and may tuck text over hair or the
   top of the head when it stays readable (never over the face). Set `"place"`
   (`top|upper|middle|lower|above_head`, optionally with `left|right|centre`, e.g.
   `"lower left"`) when another spot composes better or the customer asked for one.
   `"backing": "none"` puts clean text straight on the footage (often best for bold
   headlines); `"box"` adds the style's box/plaque only when it truly helps legibility or
   matches their taste. Their position/design instructions and rules always win.
8. Optional `zooms`: push in on a build, punch on a reveal or the strongest line -
   matched to the style's energy (Luxe/Minimal: few, gentle; Bold/Energetic: on beats).
9. Follow, in this order: review notes > what they asked for this reel > their
   creative rules > their brand choices > the style's direction (their own words,
   `style.direction`) > the style pack. A customer request may use an intent their
   brand doesn't normally show: mark that moment `"source": "customer"`.
10. Run `reel.py plan`. If it lists problems (text too long, a word they didn't say,
   a rule broken, overlapping moments, a missing why), fix the plan and run it again.

Example moment:
```json
{"intent": "stat", "from": 23, "to": 29, "quote": "did you know 80% of creators quit",
 "text": "80% of creators quit", "why": "the proof beat: the number makes the problem real"}
```
The full format is at the top of `scripts/laine_reel/creative.py`.

**Try another design.** On the review page's Graphics tab each graphic shows
"Design n of m" and a **✨ Try another design** button. It changes only that graphic
(pinned in `workspace/<reel>/designs.json`); the rest of the reel keeps its look.
For a note like "show me a different design for the stat", write feedback
`{"graphics": {"g3": {"design": "next"}}}` (or a design id) and apply it with
`review.apply_feedback`; it then re-plans.

On "apply my review": interpret notes about graphics, pacing or energy by updating
`creative.json` (keep moments that weren't mentioned), then `reel.py plan`. Edits
made with the page controls stay in `edit.overrides.json` and apply on top. After a
re-cut the plan re-anchors itself by each moment's `quote`; moments whose words were
cut are dropped with a note, and key words / zooms reset - update the plan.

## Don't interrupt the customer

Editing should feel like handing it to a great editor. Ask only when essential
information is missing (which clip? which photos?) or when a real limitation needs their
decision. Don't ask them to pick headlines, confirm technical details, approve downloads
of fonts included with the editor, or choose between options you can judge yourself -
decide, tell them what you chose, and let them change it on the review page. If a word
in the transcript is genuinely uncertain and matters (a keyword viewers must comment),
check it once; otherwise trust the transcript.

## Custom effects in everyday words ("a spinning carousel of my photos")

Customers may ask for effects that aren't in the design catalog. Check honestly
whether it can be made **today, with the editor as it is and their uploaded assets**,
before saying yes. Never claim an effect is supported if it can't actually be produced.

**Can be made now (per-reel files only):**
- Their uploaded images (library: logos, photos, screenshots) at any moment, in a corner,
  at the top, above the head or `upper/middle/lower` + `left/right` (`edit.overrides.json`
  `add.graphics`, `"type": "image"`, `"asset"`, `"place"`, `src_start`; same as the review
  page's **Use at**). Several timed one after another give a photo sequence or slideshow.
- Entrances per graphic: pop, fade, soft grow, slide up, bounce, just appear
  (`style.animation_in`); each style's own motion; a sound on each appearance.
- Text graphics in any intent and design, placed and backed (`place`, `backing`) as above;
  full-screen colour overlay with text; push/punch zooms; their fonts and exact colours.

**Spinning image carousel (built in, per reel, on request only).** "Add a spinning
carousel of my product photos when I talk about them" -> 2-8 of their library images
orbit a tilted ring with depth (front cards big and bright, back cards smaller and dimmer).
Map their words to options, ask only if the images or the moment are unclear:

```bash
python3 scripts/reel.py carousel workspace/<reel> --images "Product 1,Product 2,Product 3" \
  --at 12.5 --duration 5 [--place auto|top|upper|middle|lower|left|right|top_left|top_right|near_subject] \
  [--size small|medium|large] [--speed slow|normal|fast] [--direction clockwise|counterclockwise] \
  [--motion subtle|noticeable]
python3 scripts/reel.py final workspace/<reel> --replan
```

`--at` is a time on the reel as it is now (`reel.py locate` / the words they say); 2-15 s.
Images by library name or id; upload new ones with `library add` first. Without `--place`
the editor picks the best clear spot for the footage (face rule and safe zones as always).
"Spin it the other way" = direction, "calmer" = slow + subtle, "bigger / more dramatic" =
large + noticeable. Their brand's border/shadow choices and rules apply to the cards. It
appears on the review page (Graphics tab: "Image carousel") where they can change
placement, size, speed, direction, motion or timing, or remove it; check frames before
showing. Version 1: images only (no video clips), one ring, flat cards (no reflections or
motion blur), speed capped so it never flickers.

**Page-flip calendar (built in).** "A calendar with pages flipping": `edit.overrides.json`
`add.graphics` `{"type": "calendar", "start", "end", "src_start", "flips": [seconds after it
appears, one per beat]}` - brand header and rings, a page swings up on each beat.

**Anything else they describe: build it for this reel (custom graphic).** Don't substitute
an emoji or a different effect for what they asked. Write a small component in
`workspace/<reel>/custom/<name>.js` that registers `window.COMPONENTS['custom.<name>'] =
(g, X) => ({ e, motion })`, exactly like the style packs' components (`styles/*/1.0.0/
components.js` show the contract): draw with HTML/CSS/SVG inside `X.mk('', box)` at
`g.geo` (the layout's approved box), use only the brand's colours and fonts (`X.C`,
`X.FONTVAR`), `X.esc` for text, `X.DECO` for boxes/shadows/borders, and animate from time
alone in `motion.tick(t)` (deterministic: no random, no timers, no network). Then add it:
`add.graphics` `{"type": "custom", "custom_component": "custom.<name>", "size": [w, h],
"start", "end", "src_start", "params": {...}, "label": "what it is"}` (`place` works too).
Render a preview, look at frames across the motion, fix and repeat until it looks right,
then `final`. A component that throws stops the render with its error (never a broken
video). It stays in that reel's folder only; the editor's own files never change for one
reel.

**Really not possible (say so plainly, offer the closest thing you can build):** footage
from their other videos inside the reel (the library has no video), text or graphics
*behind* the person (needs a person cutout), motion tracking of objects in the footage.

**How to handle a request:**
1. Build it: built-in options first (carousel, calendar, designs, images, sounds), else a
   custom graphic as above. Keep their brand colours, fonts and rules, the safe zones and
   the face rule.
2. Check frames across the whole motion before showing it; it appears on the review page
   like any other graphic ("Custom graphic") where they can retime or remove it.
3. Ask only if something essential is missing (which photos, which moment) or it truly can't
   be made - then say why and what you can make instead.

## Fonts

24 Google Fonts come with the editor (`assets/fonts/included/`, licensed for bundling) in
four groups: Bold & Attention-Grabbing, Elegant & Editorial, Handwritten & Playful, Clean
Everyday Captions. In Brand settings → Fonts → **Font library** customers see each one
previewed and tap Headlines / Captions / Graphics. In chat: `fonts` = {"headline", "body"}
by name, `graphics_font` = `font:<name>` (or headline / body). They render with no download
- never ask about downloading them. Their own TTF/OTF uploads still work and win for the
same family. `python3 tests/font_library_check.py` proves all 24 render.

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
  (TTF/OTF), sounds (MP3/WAV), images (PNG/JPG; iPhone HEIC/HEIF photos are converted to
  upright JPG automatically with macOS ImageIO), stored in `assets/library/`. Name,
  categorise, preview, archive (never deleted). **Use at** puts a sound or image
  at the current moment. Uploaded fonts appear in Brand settings fonts; sounds in
  Brand settings → Sound (per moment: headline, pop-ins, emoji, zooms, CTA,
  checklist ticks); images as Logo or at a timestamp.
- Their chosen sounds are used **exactly**: if one goes missing, the render
  fails `follows_brand_profile` rather than using a default. Uploaded sounds are
  level-matched to the built-in pack (peak −3 dB) before the brand gain.

## Preferences in their own words (any time)

Customers can say things like "hot pink headlines, clean captions, no outlines or
glows" in onboarding, in chat, in a review note, or in Brand settings ("In your own
words"). Turn them into exact settings, save, then read back:

```bash
python3 scripts/reel.py brand set '<json>'                                  # saved defaults (future reels)
python3 scripts/reel.py brand set '<json>' --scope reel --reel workspace/<reel>   # this reel only
python3 scripts/reel.py brand explain [--reel workspace/<reel>]            # read it back in plain words
```

| They say | Setting |
|---|---|
| "hot pink headlines" | `{"color_roles": {"headline": "#FF1493"}}` (use their exact HEX if they have one) |
| "white captions", "key words in gold" | `{"color_roles": {"captions": "#FFFFFF", "key_words": "#C9A227"}}` |
| "no outlines", "no glow", "no shadows", "no boxes", "never emojis", "no sound effects" | `{"creative_rules": {"flags": ["no_outlines", "no_glow", ...]}}` |
| "clean captions" | `no_outlines` + `no_glow` rules (ask if they also want no shadow) |
| "use my font" | `library add` the file, then `{"font_files": {...}}` |
| "more like Magazine", "Luxe but with Bold captions" | `{"style": {"pack": "luxe", "mix": [{"pack": "bold", "aspects": ["captions"]}]}}` |
| "keep my own caption style" | `{"style": {"keep": ["caption_style"]}}` |
| anything else about look and feel | keep their words: `{"style": {"direction": "<their words>"}}`; you follow it in every creative plan |

- Partial changes merge with what's set; rules flags are a list, so include the
  ones already there.
- If it's unclear whether they mean every future reel or just this one, ask
  (AskUserQuestion: "All future reels" / "Just this reel").
- Always save their exact words in `style.direction` too, and read `brand explain`
  back so they can confirm. Never change saved defaults they didn't ask to change.

## Reference reels (optional, any time)

A reel they love can inspire their edits. It never overrides their own settings,
words or rules, and nothing from it is copied.

1. Measure it: `python3 scripts/reel.py brand reference "<path>"` (or at onboarding,
   `brand finish` does it). It reports pacing, and the editing style it can see:
   captions (where, words at a time, case, size, colour, on boxes), graphics (how
   often, where, case, boxes), zooms (punch-ins vs slow pushes), colour mood.
2. Look at `brand/reference/contact-sheet.png` (Read it) and write what you see in
   plain words to `brand/reference/traits.json`:
   `{"overall": "...", "captions": "...", "typography": "...", "animation": "...",
   "graphics": "...", "zooms": "...", "pacing": "...", "colour": "..."}`.
   Describe the editing, not their content.
3. Ask what they like about it, in their words ("I love the captions and transitions,
   but not the graphics"), and save it:
   `reel.py brand set '{"reference_prefs": {"use": ["captions", "animation", "zooms"],
   "avoid": ["graphics"], "notes": "<their words>"}}'`.
   Parts: captions, typography (lettering), animation (transitions, motion), graphics,
   zooms, pacing, colour. "Transitions" = animation + zooms; "the vibe" / "the colours"
   = colour; "the text style" = typography + captions.
4. `reel.py brand reference-suggest` proposes settings for the parts they like, each
   with the measured reason ("their captions sit in the lower third, 1 word at a time").
   Read them out and ask which to apply (AskUserQuestion, multiSelect). Save only what
   they agree to, with `brand set`. Never apply suggestions on your own.
5. In every creative plan, `creative-context` includes `reference`: the measured traits
   of the parts they like, your traits.json, what to avoid, and the rule. Let liked
   traits shape rhythm, density and zoom energy within their settings; leave avoided
   parts alone. Never copy its text (the plan check rejects it), logos or artwork (the
   library refuses files from a reference), or its exact layout.

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
- **Style first.** New customers start by picking one of six styles (a starting
  point, never a template). Not sure? Describe each in a sentence, or suggest one
  from how they talk about their brand. Their own words come at the end and win.
- **Exact colours.** Ask for HEX codes ("paste them exactly, like #FF3E8E") so every
  reel is precisely on-brand; names work too. **No brand colours yet?** Run
  `python3 scripts/reel.py brand suggest <their style>`, show the three palettes as
  HEX codes with a few words each, and let them pick or tweak one.
- **Their files.** At the fonts and `brand_files` questions, invite them to drag in
  font files (TTF/OTF), a logo, graphics, images or sound effects. For each file:
  `python3 scripts/reel.py library add "<file>" --name "<what it is>"`, then attach it
  with `reel.py brand set` (fonts: `{"font_files": {"headline": "<id>", "body": "<id>"}}`;
  logo: `{"logo": {"id": "<id>", "position": "top_right"}}`; a sound for a moment:
  `{"sound_map": {"headline": "<id>"}}`). No files? That's fine: say they can add
  them later in the Library tab.
- **Captions and zooms** have a "Let my style decide" option; whatever they pick
  themselves is kept.
- **In their own words** (`style_direction`): save it exactly as said, then turn
  it into exact settings (section "Preferences in their own words") and read them
  back with `reel.py brand explain`.
- Colours: accept hex or names; the first is the main colour, the second the
  highlight colour. If they only give one, ask if they want a highlight colour.
- Reference reel: optional (section "Reference reels" below). A path inside a
  protected folder is refused; ask them to copy the file elsewhere. Never touch
  the original.
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
candidate ids to put back. Then `recut`.

**When they quote a phrase** ("remove the first 'they started'"), don't count word
numbers: `python3 scripts/reel.py remove-phrase workspace/<reel> "they started"
--occurrence first` (or `second`, `last`, `2`), or in the review file
`{"phrase": "they started", "occurrence": "first"}`. Then `recut --check-speech`.

How cuts are made: each end lands in measured silence; when they speak straight on with no
pause, it may land on a measured quiet point between the words (stricter for removals
nobody asked for). The speech check re-transcribes every join and puts back anything that
didn't come out clean. If a removal can't be made, `recut` prints `NOT REMOVED
(requested): "..." - <why>`: tell them that plainly, in one line, with the reason. Don't
suggest re-recording unless they ask what else they could do.

## 5. Check the edit plan before rendering

Graphics and zooms come from **your creative plan** (`creative.json`, see "Creative
plan" above), not from automatic rules. `reel.py plan workspace/<reel>` turns it into
`edit.json` + `edit-plan.md`; read `edit-plan.md` as an editor would:

- **Headline**: it is the plan's `hook` moment, chosen automatically (strongest, their
  words). Their own headline (`finish --headline`, or the review page) replaces it and is
  written back into `creative.json` as their wording.
- Every graphic matches what is said at that moment and has a `why`; cut anything that
  only repeats the caption. Zooms and graphics feel like their style.
- To change something, **edit `creative.json`** (keep the moments that are fine) and run
  `plan` again. `edit.overrides.json` is for the review page's controls and for things
  the plan can't express; it applies on top and survives re-planning.
- Emoji choices: check meaning (📸 for "camera angle", not 📐).

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
