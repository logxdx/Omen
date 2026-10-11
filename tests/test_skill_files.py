import json
import os
import tempfile
import unittest
from pathlib import Path

from agents.tool_context import ToolContext

from omen.config import REPO_ROOT
from omen.core.runtime import OmenContext
from omen.core.session import Session
from omen.core.skills import Skills


class FilesSkillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.dir.name)
        self._old = os.environ.get("OMEN_SANDBOX")
        os.environ["OMEN_SANDBOX"] = str(self.sandbox)
        skills = Skills([REPO_ROOT / "skills"])
        self.tools = {t.name: t for t in skills.skills["files"].tools}
        self.answers: list[str] = []
        (self.sandbox / "notes").mkdir()
        (self.sandbox / "notes" / "todo.md").write_text("- buy milk\n- call Anna\n- buy milk again\n")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("OMEN_SANDBOX", None)
        else:
            os.environ["OMEN_SANDBOX"] = self._old
        self.dir.cleanup()

    async def call(self, name: str, **args):
        async def ask(question, options):
            return self.answers.pop(0)

        raw = json.dumps(args)
        ctx = ToolContext(
            context=OmenContext(session=Session(), ask=ask),
            tool_name=name, tool_call_id="c1", tool_arguments=raw,
        )
        return await self.tools[name].on_invoke_tool(ctx, raw)

    async def test_list_and_read(self):
        listing = await self.call("list_files")
        self.assertTrue(str(listing).startswith("./\n"))
        self.assertIn("notes/", str(listing).splitlines())
        out = await self.call("read_file", path="notes/todo.md", offset=2, limit=1)
        self.assertEqual(str(out), "notes/todo.md (lines 2-2 of 3)\n- call Anna\n[more: read_file(path='notes/todo.md', offset=3)]")

    async def test_write_new_and_confirm_overwrite(self):
        created = await self.call("write_file", path="a/b.txt", content="hello")
        self.assertIn("Created a/b.txt", str(created))
        self.answers = ["no"]
        refused = await self.call("write_file", path="a/b.txt", content="bye")
        self.assertIn("Not written", str(refused))
        self.assertEqual((self.sandbox / "a/b.txt").read_text(), "hello")
        self.answers = ["yes"]
        await self.call("write_file", path="a/b.txt", content="bye")
        self.assertEqual((self.sandbox / "a/b.txt").read_text(), "bye")

    async def test_edit_requires_a_unique_exact_match(self):
        ambiguous = await self.call("edit_file", path="notes/todo.md", old_text="buy milk", new_text="x")
        self.assertEqual(ambiguous.error, "invalid_args")
        self.assertIn("appears 2 times", str(ambiguous))
        missing = await self.call("edit_file", path="notes/todo.md", old_text="walk dog", new_text="x")
        self.assertIn("not found", str(missing))
        done = await self.call("edit_file", path="notes/todo.md", old_text="- call Anna", new_text="- call Anna at 6")
        self.assertEqual(done.details["type"], "diff")
        self.assertIn("call Anna at 6", (self.sandbox / "notes/todo.md").read_text())

    async def test_append_and_grep(self):
        await self.call("append_to_file", path="notes/todo.md", content="- water plants\n")
        found = await self.call("grep", pattern="anna|plants")
        self.assertEqual(str(found), "notes/todo.md:2: - call Anna\nnotes/todo.md:4: - water plants")
        literal = await self.call("grep", pattern="[unclosed")
        self.assertIn("No lines match", str(literal))
        (self.sandbox / "notes" / "cabin.md").write_text("Wi-Fi password: pinecone-42\n")
        loose = await self.call("grep", pattern="wifi")
        self.assertEqual(str(loose), "notes/cabin.md:1: Wi-Fi password: pinecone-42")

    async def test_listing_a_missing_folder_explains(self):
        out = await self.call("list_files", path="new")
        self.assertIsNone(out.error)
        self.assertIn("write_file creates missing folders", str(out))

    async def test_delete_asks_first(self):
        self.answers = ["nope"]
        await self.call("delete_file", path="notes/todo.md")
        self.assertTrue((self.sandbox / "notes/todo.md").exists())
        self.answers = ["yes"]
        await self.call("delete_file", path="notes/todo.md")
        self.assertFalse((self.sandbox / "notes/todo.md").exists())

    async def test_paths_outside_the_sandbox_are_refused(self):
        for path in ("../../etc/passwd", "notes/../../outside.txt"):
            out = await self.call("read_file", path=path)
            self.assertEqual(out.error, "exception", path)
            self.assertIn("outside the sandbox", str(out))

    async def test_absolute_paths_stay_inside_the_sandbox(self):
        (self.sandbox / "etc").mkdir()
        (self.sandbox / "etc" / "passwd").write_text("sandboxed")
        out = await self.call("read_file", path="/etc/passwd")
        self.assertIn("sandboxed", str(out))


if __name__ == "__main__":
    unittest.main()
