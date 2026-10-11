import unittest

from evals.extract import check, run_extract_suite
from omen.ui.extract import Extractor


class ExtractEvalTests(unittest.IsolatedAsyncioTestCase):
    def test_check(self):
        self.assertEqual(
            check({"values": [1, 2], "title": "pune", "url": None}, {"values": [1.0, 2.0], "title": "Pune city"}), []
        )
        self.assertEqual(len(check({"values": [1, 2]}, {"values": [1.0]})), 1)
        self.assertEqual(len(check({"url": None}, {"url": "https://made.up"})), 1)

    async def test_suite_runs_with_a_scripted_extractor(self):
        async def complete(messages, schema):
            return '{"title": "x", "body": "y", "labels": [], "values": []}'

        code = await run_extract_suite(Extractor(complete=complete))
        self.assertEqual(code, 1)  # scripted answers don't match the expectations


if __name__ == "__main__":
    unittest.main()
