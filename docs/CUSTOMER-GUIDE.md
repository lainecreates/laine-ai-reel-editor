# Using Laine AI Reel Editor

Open the Claude app → **Code** → choose the **laine-ai-reel-editor** folder.
Then just talk to Claude.

## 1. Set up your brand: "Start my brand onboarding"

Claude asks about 20 short questions, one at a time:

- your **style**, the starting point for your look: Luxe, Playful, Magazine,
  Minimal, Bold or Energetic. Or "let my style decide" for anything you don't mind about
- your exact colours (HEX codes like `#FF3E8E` work) and fonts
- caption style, size, position and lettering
- whether you want a headline
- how often to zoom
- which graphics and sound effects you like
- your personality, your @handle, and your style **in your own words**
  (for example "hot pink headlines, clean captions, no outlines or glows")
- optionally, a reference reel you love. Claude learns its feel (captions,
  pacing, zooms), never its words, logos or artwork

You can stop and continue later. Until you finish, reels use a clean neutral
look: white captions, no headline and no sound effects.

## 2. Edit a reel: "Edit my reel"

1. Drag your raw video into the chat. A talking-head clip filmed upright or sideways works.
   You can add instructions in your own words, for example "no emojis, calm pace".
2. Claude removes pauses, repeats, "um"s and false starts, and checks no words were lost.
3. Claude listens to what you say and writes a **creative plan**: which moments
   deserve a graphic and why, which words to highlight, where to zoom, and where
   to leave your face alone.
4. Claude picks the strongest **headline** from your own words. If you gave
   one, yours is used. You can change it on the review page.
5. A few minutes later, the **review page** opens in your browser.

Claude only asks you something when it really needs your decision. Your
original video is never changed.

## 3. Review it in your browser

- **Watch and leave notes** at any moment, in your own words: "make this bigger",
  "remove the first 'they started'", "add a calendar with pages flipping here".
- **Tabs** let you:
  - put back or remove cuts, and shorten pauses
  - fix caption spelling and timing
  - choose or write the headline
  - restyle, retime or remove graphics, or press **✨ Try another design** for
    a different design of just that graphic
  - add graphics, zooms and sounds
- Press **Save feedback**, then tell Claude **apply my review**. A new version appears on the same page by itself.
- **Versions**: every render is kept. Compare any two, or restore an older one.
- When you're happy, press **Finalize & Download**. The approved MP4 is saved to your Downloads.

**Removing repeated words:** quote the words and say which time, for example
"remove the first 'they started'". Claude cuts in a pause, or at the quietest
point between the words when you spoke straight on, then re-checks the result
by listening to it again. If a cut would clip a word, Claude tells you why
instead of making it.

## 4. Graphics and special effects

- Each style has several **designs** for headlines, lists, statistics, quotes,
  comparisons, tips and calls to action. Your reels vary on purpose, while your
  colours, fonts and rules stay the same.
- **Image carousel**: "add a spinning carousel of my product photos when I talk
  about them" puts 2–8 of your uploaded images on a turning ring. You can change
  its placement, size, speed, direction and motion on the review page.
- **Page-flip calendar**: for "months passing" moments.
- **Anything else you describe**, for example a spinning badge or a highlighted
  price: Claude builds it for that reel in your colours and fonts, instead of
  swapping in an emoji. Some things can't be done yet (other video clips inside
  the reel, text behind you, tracking objects). Claude says so and offers the
  closest thing.
- Graphics never cover your face, and stay inside Instagram and TikTok's safe areas.

## 5. Brand settings (🎛 on the review page)

Change any brand choice: style, colours (including exact colours for headlines,
captions and key words), fonts, captions, headline, graphics, zooms, sounds,
logo, and your always/never rules (no outlines, no glow, no boxes…). Choose
where it applies:

- **This reel only**: your saved style stays as it is.
- **My saved defaults**: every future reel, and this one.

Some things to know:

- **Reels you've already made keep their look.** Each reel remembers the brand it was made with. To bring an older reel up to date, use **Use my current saved defaults for this reel**.
- **Earlier saved defaults** lists every earlier version of your defaults, with the date and what changed. Press **Restore** to go back.
- Caption settings you pick yourself are kept, even when you change style.

Changes show up after you tell Claude **apply my review**.

### Fonts

**Fonts → Font library** has 24 fonts ready to use, nothing to download. They're
grouped as Bold & Attention-Grabbing, Elegant & Editorial, Handwritten & Playful,
and Clean Everyday Captions, and each is previewed in its own lettering. Tap
**Headlines**, **Captions** or **Graphics** to use one. Your own uploaded fonts
appear in the same lists.

## 6. Your asset library (📁 Library tab)

Upload your own:

- **fonts**: TTF or OTF
- **sounds**: MP3 or WAV
- **images**: PNG, JPG, or iPhone photos (HEIC). Photos are turned the right way
  up automatically and never cropped.

Then:

- **Use at** puts a sound or image at the current moment of the video.
- Uploaded fonts appear in Brand settings → Fonts.
- Uploaded sounds appear in Brand settings → Sound. When you choose your own sound, exactly that sound is used.
- Images can be your **logo** on every reel, or go into a carousel.

Nothing is ever deleted. "Remove" only hides an item, and you can bring it back.

## 7. Keeping it up to date: "Update my reel editor"

Gets the newest version. Your brand, uploads and reels stay exactly as they are.

## Where your things are

All of these are inside the **laine-ai-reel-editor** folder:

| What | Folder |
|---|---|
| Your reels, every version, and approved videos | `workspace/` |
| Your brand and its history | `brand/` |
| Your uploads | `assets/library/` |
| The included fonts and their licenses | `assets/fonts/included/` |

## Beta testers

Thank you for testing! If something goes wrong, tell Claude what happened in
the Code tab. It can check the setup ("Check my reel editor setup") and explain
any error. When you report a problem to Laine, include the reel's
`cut-report.md` and `edit-plan.md`, found in `workspace/<your reel>/`, and
what you expected to happen. Don't send your video unless you want to.
