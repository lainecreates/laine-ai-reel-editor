# Edit plan: 2026-10-17-raw-copy-test

49.2s · 35 captions · 7 zooms · 6 graphics · 6 sound effects · music: soft

**Needs Claude's review:** g1 (text_callouts: "Some of y'all are not waiting")

## Timeline

| Time | Layer | What | Why |
|---|---|---|---|
| 0:00.0–0:02.6 | text_callouts g1 | Some of y'all are not waiting | hook title (draft - Claude rewrites it short) |
| 0:00.4–0:02.6 | zoom z1 | push to 1.08x | hook |
| 0:09.0 | sfx s1 | whoosh (needs file) | zoom_punch |
| 0:09.0–0:15.2 | zoom z2 | punch to 1.18x | hides the jump cut |
| 0:15.3 | sfx s2 | whoosh (needs file) | zoom_punch |
| 0:15.3–0:20.3 | zoom z3 | punch to 1.18x | hides the jump cut |
| 0:20.4 | sfx s3 | whoosh (needs file) | zoom_punch |
| 0:20.5–0:22.5 | zoom z4 | punch to 1.18x | hides the jump cut |
| 0:20.9–0:27.6 | sticky_notes g2 | Okay, where do I put it?, What angle do I get?, Why does my footage look so random? | list of questions |
| 0:26.5 | sfx s4 | whoosh (needs file) | zoom_punch |
| 0:26.5–0:30.3 | zoom z5 | punch to 1.18x | hides the jump cut |
| 0:30.6–0:31.8 | emoji g3 | 📐 | emphasis on 'angle' |
| 0:31.8 | sfx s5 | whoosh (needs file) | zoom_punch |
| 0:31.9–0:35.9 | zoom z6 | punch to 1.18x | hides the jump cut |
| 0:35.8–0:37.0 | emoji g4 | 🎯 | emphasis on 'intentional.' |
| 0:38.3–0:41.3 | keyword_cards g5 | Morning Light Studio | named thing |
| 0:41.4 | sfx s6 | ding (needs file) | cta |
| 0:41.4–0:48.8 | zoom z7 | push to 1.08x | call to action |
| 0:41.4–0:49.2 | cta_card g6 | Comment "CONTENT" | call to action |

## Captions (karaoke, first 8)

- 0:00.4 Some of y'all are not
- 0:01.5 waiting on a **better** camera.
- 0:02.9 You're waiting
- 0:03.7 to **finally** know,
- 0:05.2 like you know
- 0:05.8 what the heck you're doing
- 0:07.4 when you hit record.
- 0:09.4 And the thing that actually

## Can this machine render it?

- **captions + graphics**: draw transparent frames outside ffmpeg, composite with overlay — ffmpeg ready; needs frame renderer (next phase; not built yet)
- **zooms**: per-frame crop + scale (eval=frame expressions) — ffmpeg ready
- **sound effects**: delay each effect to its time, mix under the voice — ffmpeg ready; needs sound files in assets/sfx/
- **music**: music bed ducked under the voice — ffmpeg ready; needs a music file
- **text**: never drawtext/subtitles — ffmpeg ready (drawtext available: False, subtitles: False)
