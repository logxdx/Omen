import os
import tempfile
import time
import unittest
import wave

try:
    import numpy as np
except ImportError:  # text-only install: TTS needs the voice extra
    np = None


@unittest.skipIf(np is None, "numpy not installed (voice extra)")
class TTSTests(unittest.TestCase):
    def setUp(self):
        from omen.voice import tts

        self.tts = tts

    def engine(self, delay=0.0, rate=1000):
        test = self

        class Fake:
            name, sample_rate = "fake", rate
            said: list = []

            def synthesize(self, text):
                time.sleep(delay)
                self.said.append(text)
                return np.full(rate // 10, 0.5, dtype=np.float32)  # 100 ms per sentence

        test.fake = Fake()
        test.fake.said = []
        return test.fake

    def output(self):
        written = []

        class Out:
            def write(self, data):
                written.append(data)
                time.sleep(0.005)

            def close(self):
                pass

        return written, (lambda rate: Out())

    def test_sentences(self):
        self.assertEqual(self.tts.sentences("Hi there. How are you? Fine!"), ["Hi there.", "How are you?", "Fine!"])
        long = "word, " * 100
        self.assertTrue(all(len(c) <= 300 for c in self.tts.sentences(long)))

    def test_to_float32(self):
        out = self.tts.to_float32(np.array([0, 16384, -32768], dtype=np.int16))
        self.assertEqual(out.dtype, np.float32)
        self.assertAlmostEqual(float(out[1]), 0.5)

    def test_speaker_plays_every_sentence(self):
        written, output = self.output()
        speaker = self.tts.Speaker(self.engine(), output)
        speaker.start("One. Two. Three.")
        speaker.thread.join(5)
        self.assertEqual(self.fake.said, ["One.", "Two.", "Three."])
        self.assertEqual(sum(len(w) for w in written), 3 * 100 * 2)  # 3 x 100 samples x int16

    def test_stop_cuts_playback_and_start_replaces_it(self):
        written, output = self.output()
        speaker = self.tts.Speaker(self.engine(delay=0.05), output)
        speaker.start("A. B. C. D. E. F. G. H.")
        time.sleep(0.12)
        speaker.stop()
        self.assertFalse(speaker.is_playing)
        played = len(written)
        time.sleep(0.2)
        self.assertEqual(len(written), played)  # nothing after stop
        self.assertLess(len(self.fake.said), 8)
        speaker.start("New.")
        speaker.thread.join(5)
        self.assertEqual(self.fake.said[-1], "New.")

    def test_pause_holds_and_play_resumes(self):
        written, output = self.output()
        speaker = self.tts.Speaker(self.engine(), output)
        speaker.start("One. Two. Three. Four.")
        time.sleep(0.03)
        speaker.pause()
        time.sleep(0.05)
        held = len(written)
        time.sleep(0.1)
        self.assertEqual(len(written), held)
        speaker.play()
        speaker.thread.join(5)
        self.assertEqual(sum(len(w) for w in written), 4 * 100 * 2)

    def test_unknown_engine_and_wav(self):
        with self.assertRaises(KeyError):
            self.tts.make_engine("nope")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.wav")
            self.tts.write_wav(path, np.zeros(2400, dtype=np.float32), 24000)
            with wave.open(path) as f:
                self.assertEqual((f.getframerate(), f.getnframes()), (24000, 2400))


if __name__ == "__main__":
    unittest.main()
