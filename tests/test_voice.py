import asyncio
import unittest

from agents import Agent

from omen.core import Runtime
from omen.core.events import UserQuestion
from omen.voice.frontend import SPOKEN_LIMIT, VoiceSession, run_voice, speech_text
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_text_message


async def utterances(*texts):
    for text in texts:
        yield text
        await asyncio.sleep(0)


class Speaker:
    def __init__(self):
        self.spoken, self.stops = [], 0

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stops += 1


class SpeechTextTests(unittest.TestCase):
    def test_markdown_becomes_plain_sentences(self):
        reply = (
            "## Weather\n**Pune** is *26°C* today, e.g. warm. See [the forecast](https://x.org/f).\n"
            "- light rain later\n- humid\n<ui:card>"
        )
        self.assertEqual(
            speech_text(reply),
            "Weather. Pune is 26°C today, for example warm. See the forecast. light rain later. humid.",
        )

    def test_code_and_tables_are_left_on_screen(self):
        reply = "Here:\n```python\nprint(1)\n```\n| a | b |\n|---|---|\n| 1 | 2 |\nDone"
        self.assertEqual(speech_text(reply), "Here: The code is on screen. The table is on screen. Done.")


class FakeRuntime:
    """Just the routing surface VoiceSession uses."""

    def __init__(self, running=False, question=None):
        self.running, self.pending_question = running, question
        self.sent, self.answers = [], []

    def send(self, text):
        self.sent.append(text)

    def answer(self, text):
        self.answers.append(text)
        return True


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_utterance_runs_and_the_reply_is_spoken_clean(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([[get_text_message("**Done.** It's 26°C.\n<ui:card>")]])
        speaker = Speaker()
        session = VoiceSession(Runtime(Agent(name="a", model=model)), speaker.speak, speaker.stop, say=lambda t: None)
        await session.run(utterances("weather?"))
        self.assertEqual(speaker.spoken, ["Done. It's 26°C."])

    async def test_talking_while_it_works_steers_and_stops_speech(self):
        runtime, speaker = FakeRuntime(running=True), Speaker()
        await VoiceSession(runtime, speaker.speak, speaker.stop, say=lambda t: None).run(utterances("make it shorter", "  "))
        self.assertEqual(runtime.sent, ["make it shorter"])
        self.assertEqual(speaker.stops, 1)  # the blank utterance is ignored

    async def test_a_pending_question_takes_the_next_utterance(self):
        runtime = FakeRuntime(running=True, question=UserQuestion("q1", "Which city?", ["Pune", "Delhi"]))
        speaker = Speaker()
        await VoiceSession(runtime, speaker.speak, speaker.stop, say=lambda t: None).run(utterances("Pune"))
        self.assertEqual((runtime.answers, runtime.sent), (["Pune"], []))

    async def test_long_replies_get_a_spoken_briefing(self):
        calls = []

        async def summarize(request, reply):
            calls.append(request)
            return "- Three temples, all open late."

        session = VoiceSession(FakeRuntime(), Speaker().speak, Speaker().stop, summarize=summarize, say=lambda t: None)
        self.assertEqual(await session.spoken("temples?", "word " * 100), "Three temples, all open late.")
        self.assertEqual(calls, ["temples?"])
        short = "A short answer."
        self.assertEqual(await session.spoken("q", short), short)
        self.assertLess(len(short), SPOKEN_LIMIT)

        async def broken(request, reply):
            raise ConnectionError("down")

        session.summarize = broken
        self.assertTrue((await session.spoken("q", "word " * 100)).startswith("word word"))

    async def test_overlong_speech_is_cut_at_a_sentence(self):
        session = VoiceSession(FakeRuntime(), Speaker().speak, Speaker().stop, say=lambda t: None)
        spoken = await session.spoken("q", "This is one sentence of the reply. " * 40)
        self.assertLessEqual(len(spoken), SPOKEN_LIMIT * 2 + 30)
        self.assertTrue(spoken.endswith("reply. The rest is on screen."))
        self.assertEqual(speech_text("Read https://x.org/a now."), "Read the link on screen now.")


class FallbackTests(unittest.TestCase):
    def test_missing_speech_packages_fall_back_to_text(self):
        try:
            import pyaudio  # noqa: F401

            self.skipTest("speech packages are installed")
        except ImportError:
            pass
        self.assertFalse(run_voice(runtime=None, render=lambda event: None))


if __name__ == "__main__":
    unittest.main()
