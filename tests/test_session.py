import tempfile
import unittest
from pathlib import Path

from omen.core.session import Session


def msg(role, content):
    return {"role": role, "content": content}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "s.jsonl"

    def tearDown(self):
        self.dir.cleanup()

    def test_roundtrip(self):
        s = Session(self.path)
        s.add_message(msg("user", "hi"))
        s.add_message(msg("assistant", "hello"))
        reloaded = Session(self.path)
        self.assertEqual(reloaded.messages(), [msg("user", "hi"), msg("assistant", "hello")])
        self.assertEqual(reloaded.leaf, s.leaf)

    def test_branching_keeps_old_branch(self):
        s = Session(self.path)
        first = s.add_message(msg("user", "q1"))
        s.add_message(msg("assistant", "bad answer"))
        s.branch(first)
        s.add_message(msg("assistant", "good answer"))
        self.assertEqual([m["content"] for m in s.messages()], ["q1", "good answer"])
        self.assertEqual(len(s.children(first)), 2)
        reloaded = Session(self.path)
        self.assertEqual([m["content"] for m in reloaded.messages()], ["q1", "good answer"])

    def test_branch_to_root(self):
        s = Session()
        s.add_message(msg("user", "q1"))
        s.branch(None)
        s.add_message(msg("user", "fresh"))
        self.assertEqual([m["content"] for m in s.messages()], ["fresh"])

    def test_labels_do_not_move_leaf(self):
        s = Session(self.path)
        a = s.add_message(msg("user", "q1"))
        b = s.add_message(msg("assistant", "a1"))
        s.label(a, "start")
        self.assertEqual(s.leaf, b)
        self.assertEqual(Session(self.path).leaf, b)
        self.assertEqual(Session(self.path).labels(), {a: "start"})

    def test_unknown_ids_raise(self):
        s = Session()
        with self.assertRaises(KeyError):
            s.branch("nope")
        with self.assertRaises(KeyError):
            s.label("nope", "x")

    def test_create_makes_file_on_first_append(self):
        s = Session.create(Path(self.dir.name) / "sessions")
        self.assertFalse(s.path.exists())
        s.add_message(msg("user", "hi"))
        self.assertTrue(s.path.exists())


if __name__ == "__main__":
    unittest.main()
