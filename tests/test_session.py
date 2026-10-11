import tempfile
import unittest
from pathlib import Path

from omen.core.session import CUSTOM_DATA_KEY, Session


def msg(role, content):
    return {"role": role, "content": content}


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "s.jsonl"

    def tearDown(self):
        self.dir.cleanup()

    async def test_sdk_protocol_roundtrip(self):
        s = Session(self.path)
        await s.add_items([msg("user", "hi"), msg("assistant", "hello")])
        reloaded = Session(self.path)
        self.assertEqual(await reloaded.get_items(), [msg("user", "hi"), msg("assistant", "hello")])
        self.assertEqual(await reloaded.get_items(limit=1), [msg("assistant", "hello")])
        self.assertEqual(reloaded.session_id, self.path.stem)

    async def test_pop_and_clear(self):
        s = Session()
        await s.add_items([msg("user", "a"), msg("assistant", "b")])
        self.assertEqual(await s.pop_item(), msg("assistant", "b"))
        self.assertEqual(await s.get_items(), [msg("user", "a")])
        await s.clear_session()
        self.assertEqual(await s.get_items(), [])

    async def test_branching_keeps_old_branch(self):
        s = Session(self.path)
        await s.add_items([msg("user", "q1")])
        first = s.leaf
        await s.add_items([msg("assistant", "bad answer")])
        s.branch(first)
        await s.add_items([msg("assistant", "good answer")])
        self.assertEqual([i["content"] for i in s.items()], ["q1", "good answer"])
        self.assertEqual(len(s.children(first)), 2)
        self.assertEqual([i["content"] for i in Session(self.path).items()], ["q1", "good answer"])

    async def test_fork_is_detached_and_survives_reload(self):
        s = Session(self.path)
        await s.add_items([msg("user", "main question")])
        main_leaf = s.leaf
        last = s.fork([msg("user", "subtask"), msg("assistant", "sub result")], meta={"persona": "researcher"})
        self.assertEqual(s.leaf, main_leaf)
        self.assertEqual([i["content"] for i in s.items()], ["main question"])
        self.assertEqual([i["content"] for i in s.items(last)], ["main question", "subtask", "sub result"])

        reloaded = Session(self.path)
        self.assertEqual(reloaded.leaf, main_leaf)  # a fork written last never becomes the leaf
        root_of_fork = reloaded.path_to(last)[1]
        self.assertEqual(root_of_fork["meta"], {"persona": "researcher"})
        self.assertTrue(root_of_fork["detached"])

    async def test_labels_do_not_move_leaf(self):
        s = Session(self.path)
        await s.add_items([msg("user", "q1"), msg("assistant", "a1")])
        a = s.path_to()[0]["id"]
        leaf = s.leaf
        s.label(a, "start")
        self.assertEqual(Session(self.path).leaf, leaf)
        self.assertEqual(Session(self.path).labels(), {a: "start"})

    async def test_ui_details(self):
        s = Session()
        await s.add_items([
            {"type": "function_call", "call_id": "w1", "name": "get_weather", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "w1", "output": "18C",
             CUSTOM_DATA_KEY: {"ui": {"type": "weather"}}},
        ])
        self.assertEqual(s.ui_details(), {"w1": {"type": "weather"}})

    async def test_unknown_ids_raise(self):
        s = Session()
        with self.assertRaises(KeyError):
            s.branch("nope")
        with self.assertRaises(KeyError):
            s.label("nope", "x")


if __name__ == "__main__":
    unittest.main()
