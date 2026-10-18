# Edit plan: 2026-10-17-raw-copy-test

49.2s · 107 captions · 9 zooms · 2 graphics · 9 sound effects · music: upbeat

**Needs Claude's review:** g1 (text_callouts: "Some of y'all are not waiting")

## Timeline

| Time | Layer | What | Why |
|---|---|---|---|
| 0:00.0 | sfx s1 | pop (needs file) | graphic_in |
| 0:00.0–0:02.6 | text_callouts g1 | Some of y'all are not waiting | hook title (draft - Claude rewrites it short) |
| 0:00.0–0:49.2 | progress_bar g2 | progress_bar | watch-time cue |
| 0:00.4–0:02.6 | zoom z1 | punch to 1.22x | new key line |
| 0:09.0 | sfx s2 | whoosh (needs file) | zoom_punch |
| 0:09.0–0:15.2 | zoom z2 | punch to 1.22x | hides the jump cut |
| 0:15.3 | sfx s3 | whoosh (needs file) | zoom_punch |
| 0:15.3–0:20.3 | zoom z3 | punch to 1.22x | hides the jump cut |
| 0:20.4 | sfx s4 | whoosh (needs file) | zoom_punch |
| 0:20.5–0:22.5 | zoom z4 | punch to 1.22x | hides the jump cut |
| 0:23.7 | sfx s5 | whoosh (needs file) | zoom_punch |
| 0:23.8–0:26.4 | zoom z5 | punch to 1.22x | hides the jump cut |
| 0:27.1 | sfx s6 | whoosh (needs file) | zoom_punch |
| 0:27.1–0:30.3 | zoom z6 | punch to 1.22x | new key line |
| 0:31.8 | sfx s7 | whoosh (needs file) | zoom_punch |
| 0:31.9–0:35.9 | zoom z7 | punch to 1.22x | hides the jump cut |
| 0:36.0 | sfx s8 | whoosh (needs file) | zoom_punch |
| 0:36.1–0:39.4 | zoom z8 | punch to 1.22x | hides the jump cut |
| 0:40.9 | sfx s9 | whoosh (needs file) | zoom_punch |
| 0:41.0–0:48.8 | zoom z9 | punch to 1.22x | hides the jump cut |

## Captions (word_pop, first 8)

- 0:00.4 SOME
- 0:00.6 OF Y'ALL
- 0:01.0 ARE
- 0:01.2 NOT
- 0:01.5 WAITING
- 0:01.8 ON A **BETTER**
- 0:02.5 CAMERA.
- 0:02.9 YOU'RE

## Can this machine render it?

- **captions + graphics**: draw transparent frames outside ffmpeg, composite with overlay — ffmpeg ready; needs frame renderer (next phase; not built yet)
- **zooms**: per-frame crop + scale (eval=frame expressions) — ffmpeg ready
- **sound effects**: delay each effect to its time, mix under the voice — ffmpeg ready; needs sound files in assets/sfx/
- **music**: music bed ducked under the voice — ffmpeg ready; needs a music file
- **text**: never drawtext/subtitles — ffmpeg ready (drawtext available: False, subtitles: False)
