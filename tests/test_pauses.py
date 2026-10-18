"""Unit tests for pause planning and timeline remapping (no media needed).

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from laine_reel import align, config, pauses, timeline  # noqa: E402

NATURAL = config.PACING["natural"]


def W(text, s, e):
    return {"text": text, "start": s, "end": e}


class PlanCuts(unittest.TestCase):
    def test_short_pauses_are_left_alone(self):
        plan = pauses.plan_cuts(10.0, [{"start": 4.0, "end": 4.3}], NATURAL)
        self.assertEqual(plan["cuts"], [])
        self.assertEqual(plan["keep"], [[0.0, 10.0]])

    def test_long_pause_keeps_natural_gap(self):
        plan = pauses.plan_cuts(10.0, [{"start": 4.0, "end": 6.0}], NATURAL)
        (cut,) = plan["cuts"]
        self.assertEqual(cut["kind"], "pause")
        remaining = 2.0 - (cut["end"] - cut["start"])
        self.assertAlmostEqual(remaining, NATURAL.keep_pause, delta=2 / 30)
        self.assertLess(plan["stats"]["output_duration"], 10.0)

    def test_lead_and_tail_trimmed(self):
        sil = [{"start": 0.0, "end": 1.5}, {"start": 8.0, "end": 10.0}]
        plan = pauses.plan_cuts(10.0, sil, NATURAL)
        kinds = [c["kind"] for c in plan["cuts"]]
        self.assertEqual(kinds, ["lead", "tail"])
        a, b = plan["keep"][0]
        self.assertAlmostEqual(a, 1.5 - NATURAL.lead_in, delta=1 / 30)
        self.assertAlmostEqual(b, 8.0 + NATURAL.tail, delta=1 / 30)

    def test_boundaries_on_frame_grid(self):
        plan = pauses.plan_cuts(10.0, [{"start": 3.1234, "end": 5.6789}], NATURAL)
        for a, b in plan["keep"]:
            for t in (a, b):
                self.assertAlmostEqual(t * 30, round(t * 30), places=3)

    def test_video_running_past_audio_is_tail(self):
        # audio stops at 8.0 s, video runs to 10.0 s, last silence 7.0-8.0
        plan = pauses.plan_cuts(10.0, [{"start": 7.0, "end": 8.0}], NATURAL, audio_end=8.0)
        (cut,) = plan["cuts"]
        self.assertEqual(cut["kind"], "tail")
        self.assertAlmostEqual(plan["keep"][-1][1], 7.0 + NATURAL.tail, delta=1 / 30)

    def test_cuts_stay_inside_silence(self):
        sil = [{"start": 2.0, "end": 3.0}, {"start": 5.0, "end": 7.5}]
        plan = pauses.plan_cuts(10.0, sil, NATURAL)
        for c in plan["cuts"]:
            self.assertTrue(any(s["start"] <= c["start"] and c["end"] <= s["end"] for s in sil))

    def test_sound_blip_splits_a_pause(self):
        # 0.25 s silence, 18 ms of sound (end of a soft word), 0.32 s silence:
        # two short pauses, not one long one -> nothing is cut.
        sil = [{"start": 27.232, "end": 27.482}, {"start": 27.5, "end": 27.816}]
        self.assertEqual(pauses.plan_cuts(60.0, sil, NATURAL)["cuts"], [])

    def test_presets_get_progressively_tighter(self):
        sil = [{"start": 2.0, "end": 2.5}, {"start": 5.0, "end": 6.0}]
        outs = [pauses.plan_cuts(10.0, sil, config.PACING[p])["stats"]["output_duration"]
                for p in ("natural", "tight", "fast")]
        self.assertGreater(outs[0], outs[1])
        self.assertGreater(outs[1], outs[2])

    def test_fillers_flagged(self):
        f = pauses.find_fillers([W("So", 0, .2), W("um,", .3, .5), W("yes", .6, .8)])
        self.assertEqual([x["text"] for x in f], ["um,"])


class Remap(unittest.TestCase):
    keep = [[0.0, 2.0], [3.0, 5.0]]

    def test_source_to_output(self):
        self.assertEqual(timeline.source_to_output(1.0, self.keep), 1.0)
        self.assertIsNone(timeline.source_to_output(2.5, self.keep))
        self.assertEqual(timeline.source_to_output(3.5, self.keep), 2.5)

    def test_words_shift_and_cut_words_drop(self):
        words = [W("a", 0.5, 0.8), W("gone", 2.2, 2.6), W("b", 3.2, 3.6)]
        out = timeline.remap_words(words, self.keep)
        self.assertEqual([w["text"] for w in out], ["a", "b"])
        self.assertAlmostEqual(out[1]["start"], 2.2)
        self.assertEqual(out[1]["source_start"], 3.2)


class Align(unittest.TestCase):
    sil = [{"start": 0.0, "end": 1.27}, {"start": 3.67, "end": 5.49}]

    def test_early_words_pushed_into_speech(self):
        # whisper put "Hi" at 0.0 though speech starts at 1.27 s
        out = align.align_words([W("Hi,", 0.0, 0.25), W("this", 0.49, 0.98),
                                 W("is", 1.3, 1.5)], self.sil, 10.0)
        self.assertGreaterEqual(out[0]["start"], 1.27)
        self.assertGreaterEqual(out[1]["start"], out[0]["start"])
        self.assertEqual(out[0]["whisper_start"], 0.0)

    def test_word_stretched_over_pause_is_clamped(self):
        (w,) = align.align_words([W("editor.", 3.2, 5.6)], self.sil, 10.0)
        self.assertEqual((w["start"], w["end"]), (3.2, 3.67))

    def test_soft_word_touching_sound_keeps_whisper_time(self):
        sil = [{"start": 27.232, "end": 27.482}, {"start": 27.5, "end": 27.816}]
        (w,) = align.align_words([W("good,", 27.26, 27.53)], sil, 60.0)
        self.assertEqual((w["start"], w["end"]), (27.26, 27.53))

    def test_order_preserved(self):
        words = [W(str(i), i * 0.4, i * 0.4 + 0.3) for i in range(20)]
        out = align.align_words(words, self.sil, 10.0)
        starts = [w["start"] for w in out]
        self.assertEqual(starts, sorted(starts))


class Onsets(unittest.TestCase):
    def test_late_word_snaps_to_voice_onset(self):
        # silence until 1.00 s, the (lag-corrected) estimate is still 0.2 s late
        words = [W("hello", 1.20, 1.70)]
        align.snap_onsets(words, [{"start": 0.0, "end": 1.0}])
        self.assertEqual(words[0]["start"], 1.0)

    def test_early_word_inside_silence_moves_to_onset(self):
        words = [W("hello", 0.80, 1.40)]
        align.snap_onsets(words, [{"start": 0.0, "end": 1.0}])
        self.assertEqual(words[0]["start"], 1.0)

    def test_stretched_word_before_a_pause_is_clamped(self):
        # "camera." stretched into the pause; the pause ends at 14.81 when "Because" starts
        words = [W("camera.", 14.30, 14.90), W("Because", 15.18, 15.40)]
        align.snap_onsets(words, [{"start": 14.55, "end": 14.81}])
        self.assertEqual(words[0]["end"], 14.55)
        self.assertEqual(words[1]["start"], 14.81)

    def test_never_before_previous_word(self):
        words = [W("hi", 0.5, 1.2), W("there", 1.4, 1.8)]
        align.snap_onsets(words, [{"start": 0.0, "end": 0.5}, {"start": 1.1, "end": 1.15}])
        self.assertEqual(words[1]["start"], 1.4)   # onset 1.15 is before "hi" ends (1.2)


class Ends(unittest.TestCase):
    def test_word_runs_until_the_pause_after_it(self):
        # "to," really lasts 3.12-3.46 (pause 3.46-3.80); whisper said it ended at 3.17
        words = [W("to,", 3.12, 3.17), W("today", 3.801, 3.96)]
        align.fill_ends(words, [{"start": 3.098, "end": 3.162}, {"start": 3.46, "end": 3.801}])
        self.assertEqual(words[0]["end"], 3.46)   # the 64 ms gap inside the word is ignored

    def test_word_runs_until_the_next_word(self):
        words = [W("want", 2.78, 2.9), W("to,", 3.12, 3.17)]
        align.fill_ends(words, [])
        self.assertEqual(words[0]["end"], 3.12)


class Refine(unittest.TestCase):
    def test_start_moves_to_the_dip_between_words(self):
        import tempfile, wave, array, math
        from pathlib import Path
        # 1.0 s tone, 60 ms near-silence, 1.0 s tone at 16 kHz: the second word
        # really starts at 1.06 s; the estimate says 1.15 s.
        rate = 16000
        data = array.array("h")
        for t in range(int(2.06 * rate)):
            s = t / rate
            loud = s < 1.0 or s >= 1.06
            data.append(int((8000 if loud else 30) * math.sin(2 * math.pi * 220 * s)))
        f = Path(tempfile.mkdtemp()) / "t.wav"
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(data.tobytes())
        words = [W("one", 0.0, 1.0), W("two", 1.15, 2.0)]
        align.refine_starts(words, f)
        self.assertAlmostEqual(words[1]["start"], 1.06, delta=0.02)
        self.assertLessEqual(words[0]["end"], words[1]["start"])


class Whisper(unittest.TestCase):
    def test_parse_tokens(self):
        from laine_reel.transcribe import parse_whisper_json

        def T(text, a, b):
            return {"text": text, "offsets": {"from": a, "to": b}}
        raw = {"transcription": [
            {"text": " Hello, don't.", "offsets": {"from": 0, "to": 5600}, "tokens": [
                T("[_BEG_]", 0, 0), T(" Hello", 0, 300), T(",", 300, 320),
                T(" don", 400, 600), T("'t", 600, 700), T(".", 700, 5600)]},
            {"text": " [BLANK_AUDIO]", "offsets": {"from": 5600, "to": 6000}, "tokens": [
                T(" [", 5600, 5700), T("BLANK_AUDIO", 5700, 5900), T("]", 5900, 6000)]},
        ]}
        words = parse_whisper_json(raw)
        self.assertEqual([w["text"] for w in words], ["Hello,", "don't."])
        self.assertEqual(words[1]["end"], 0.7)  # "." does not stretch the word


    def test_dtw_start_used(self):
        from laine_reel.transcribe import parse_whisper_json
        raw = {"transcription": [{"text": " Hi there", "offsets": {"from": 0, "to": 900},
               "tokens": [{"text": " Hi", "offsets": {"from": 0, "to": 230}, "t_dtw": 152},
                          {"text": " there", "offsets": {"from": 230, "to": 900}, "t_dtw": 198}]}]}
        words = parse_whisper_json(raw)
        self.assertEqual(words[0]["start"], 1.52)
        self.assertEqual(words[0]["end"], 1.75)  # DTW start + whisper's length
        self.assertEqual(words[1]["end"], 2.65)

    def test_dtw_preset_names(self):
        from laine_reel.transcribe import dtw_preset
        self.assertEqual(dtw_preset("/x/ggml-small.en.bin"), "small.en")
        self.assertEqual(dtw_preset("ggml-base.en-q5_1.bin"), "base.en")
        self.assertEqual(dtw_preset("ggml-large-v3-turbo.bin"), "large.v3.turbo")
        self.assertIsNone(dtw_preset("my-custom.bin"))


class FrameRate(unittest.TestCase):
    def test_source_rate_kept(self):
        self.assertEqual(config.output_fps(24.001)[0], "24")
        self.assertEqual(config.output_fps(29.97)[0], "30000/1001")
        self.assertEqual(config.output_fps(25.0)[0], "25")
        self.assertEqual(config.output_fps(119.88)[0], "60")
        self.assertEqual(config.output_fps(0)[0], "30")


class Filtergraph(unittest.TestCase):
    def test_no_text_filters_used(self):
        from laine_reel.render import build_filtergraph
        for frame in ("cover", "blur"):
            g = build_filtergraph([[0, 1], [2, 3]], frame=frame)
            self.assertNotIn("drawtext", g)
            self.assertNotIn("subtitles", g)
            self.assertIn("concat=n=2", g)


if __name__ == "__main__":
    unittest.main()
