#!/usr/bin/env python3
"""Offline fixtures only: writes pointers under a temporary workspace."""
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import precompact_guard as guard
import write_task_pointer as writer
from test_support import document

SCRIPT = Path(__file__).with_name("write_task_pointer.py")
TASK = "01a0fixture-0000-7000-8000-000000000001"
OTHER = "01a0fixture-0000-7000-8000-000000000002"


class WritePointerTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="task-pointer-")
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.canonical = os.path.join(self.workspace, "docs", "handoffs", "CURRENT_HANDOFF.md")
        os.makedirs(os.path.dirname(self.canonical))
        Path(self.canonical).write_text(document(self.canonical, TASK), encoding="utf-8")
        self.root = guard.normalized_root(self.workspace)
        # A private Codex home with an empty goals table keeps --seal independent of this machine.
        self.codex_home = tempfile.mkdtemp(prefix="codex-home-")
        self.addCleanup(shutil.rmtree, self.codex_home, ignore_errors=True)
        self.goals("CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        previous = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = self.codex_home
        self.addCleanup(lambda: os.environ.__setitem__("CODEX_HOME", previous) if previous is not None
                        else os.environ.pop("CODEX_HOME", None))

    def goals(self, statement, parameters=()):
        # Close explicitly: a sqlite3 context manager only commits, and Windows keeps the file locked.
        connection = sqlite3.connect(os.path.join(self.codex_home, "goals_1.sqlite"))
        try:
            with connection:
                connection.execute(statement, parameters)
        finally:
            connection.close()

    def set_goal(self, status):
        self.goals("INSERT OR REPLACE INTO thread_goals VALUES (?, ?)", (TASK, status))

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = writer.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def write(self, *extra):
        return self.call("--canonical", self.canonical, "--task-id", TASK, "--workspace", self.workspace, *extra)

    def test_default_writes_unsealed_locator_only(self):
        rc, out, err = self.write()
        self.assertEqual((rc, err), (0, ""))
        pointer = Path(guard.task_pointer_path(self.root, TASK))
        text = pointer.read_text(encoding="utf-8")
        self.assertIn("- Task or thread: `%s`" % TASK, text)
        self.assertIn("- Workspace: `%s`" % self.root, text)
        self.assertIn("- Canonical document: `%s`" % self.canonical.replace("\\", "/"), text)
        self.assertIn("- Updated at: `", text)
        self.assertNotIn("Canonical SHA256", text)
        self.assertNotIn("Handoff revision", text)
        self.assertEqual(out.splitlines(), ["LOCATOR " + pointer.as_posix()])

    def test_seal_writes_exact_pointer_and_prints_paste_line(self):
        rc, out, err = self.write("--seal")
        self.assertEqual((rc, err), (0, ""))
        pointer = Path(guard.task_pointer_path(self.root, TASK))
        text = pointer.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^- Canonical SHA256: `[0-9a-f]{64}`$")
        self.assertIn("- Handoff revision: `1`", text)
        lines = out.splitlines()
        self.assertEqual(lines[0], "POINTER " + pointer.as_posix())
        entry, _ = json.JSONDecoder().raw_decode(lines[1][lines[1].index("{"):])
        self.assertEqual(entry["predecessor"], TASK)
        self.assertEqual(entry["handoff"], pointer.as_posix())
        self.assertFalse(Path(str(pointer) + ".tmp").exists())

    def test_only_a_sealed_pointer_stops_the_task(self):
        raw = json.dumps({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": TASK,
                          "cwd": self.workspace}, ensure_ascii=False).encode("utf-8")
        self.assertEqual(guard.decide(raw, guard.ALL_SESSIONS), {})
        self.assertEqual(self.write()[0], 0)
        self.assertEqual(guard.decide(raw, guard.ALL_SESSIONS), {}, "a routine locator must not stop compaction")
        self.assertEqual(self.write("--seal")[0], 0)
        self.assertIs(guard.decide(raw, guard.ALL_SESSIONS).get("continue"), False)
        Path(self.canonical).write_text(document(self.canonical, TASK, revision=2), encoding="utf-8")
        self.assertEqual(guard.decide(raw, guard.ALL_SESSIONS), {}, "any later edit releases the seal")
        self.assertEqual(self.write()[0], 0)
        self.assertEqual(guard.decide(raw, guard.ALL_SESSIONS), {}, "a routine refresh replaces the seal")

    def test_seal_refuses_while_goal_is_active(self):
        self.set_goal("active")
        self.assertEqual(self.write()[0], 0, "a routine locator ignores goals")
        rc, out, err = self.write("--seal")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("goal is still active", err)
        self.assertNotIn("Canonical SHA256",
                         Path(guard.task_pointer_path(self.root, TASK)).read_text(encoding="utf-8"))
        for status in ("paused", "blocked", "usage_limited", "budget_limited", "complete"):
            with self.subTest(status=status):
                self.set_goal(status)
                self.assertEqual(self.write("--seal")[:3:2], (0, ""))

    def test_seal_warns_when_goal_state_is_unreadable(self):
        os.remove(os.path.join(self.codex_home, "goals_1.sqlite"))
        rc, out, err = self.write("--seal")
        self.assertEqual(rc, 0)
        self.assertIn("WARNING: cannot read this task's goal state", err)
        self.assertTrue(out.startswith("POINTER "))

    def test_successor_can_seal_its_transferred_document_but_complete_cannot(self):
        # Shape of a real manual-paste takeover (2026-10-19 r411): successor owns a "transferred" document.
        transferred = document(self.canonical, TASK).replace("- Status: `active`", (
            "- Predecessor task: `%s`\n- Successor task: `%s`\n- Rollover generation: `1`\n- Status: `transferred`" % (OTHER, TASK)))
        Path(self.canonical).write_text(transferred, encoding="utf-8")
        self.assertEqual(self.write("--seal")[0], 0)
        Path(self.canonical).write_text(document(self.canonical, TASK).replace("`active`", "`complete`"), encoding="utf-8")
        rc, out, err = self.write("--seal")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("completed task does not need another handoff", err)

    def test_guard_finds_seal_when_cwd_has_extended_length_prefix(self):
        self.assertEqual(self.write("--seal")[0], 0)
        raw = json.dumps({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": TASK,
                          "cwd": "\\\\?\\" + self.workspace}, ensure_ascii=False).encode("utf-8")
        self.assertIs(guard.decide(raw, guard.ALL_SESSIONS).get("continue"), False)

    def test_locator_accepts_unslimmed_document_but_seal_refuses(self):
        state = "\n".join("- synthetic line %d" % index for index in range(120))
        Path(self.canonical).write_text(document(self.canonical, TASK, state=state), encoding="utf-8")
        self.assertEqual(self.write()[0], 0)
        rc, out, err = self.write("--seal")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("slimming", err)
        self.assertNotIn("Canonical SHA256",
                         Path(guard.task_pointer_path(self.root, TASK)).read_text(encoding="utf-8"))

    def test_refresh_overwrites_in_place(self):
        for extra in ((), ("--seal",), ()):
            self.assertEqual(self.write(*extra)[0], 0)
        folder = Path(guard.task_pointer_path(self.root, TASK)).parent
        self.assertEqual(len(list(folder.iterdir())), 1)

    def test_rejects_pointer_same_as_canonical_and_preserves_document(self):
        pointer = Path(guard.task_pointer_path(self.root, TASK))
        pointer.parent.mkdir(parents=True)
        original = document(pointer, TASK).encode("utf-8")
        pointer.write_bytes(original)
        for extra in ((), ("--seal",)):
            with self.subTest(extra=extra):
                rc, out, err = self.call("--canonical", str(pointer), "--task-id", TASK,
                                         "--workspace", self.workspace, *extra)
                self.assertEqual(rc, 2)
                self.assertIn("overlap", err)
                self.assertEqual(out, "")
                self.assertEqual(pointer.read_bytes(), original)
                self.assertEqual(list(pointer.parent.iterdir()), [pointer])

    def test_rejects_pointer_hardlinked_to_canonical(self):
        pointer = Path(guard.task_pointer_path(self.root, TASK))
        pointer.parent.mkdir(parents=True)
        os.link(self.canonical, pointer)
        original = Path(self.canonical).read_bytes()
        for extra in ((), ("--seal",)):
            with self.subTest(extra=extra):
                rc, out, err = self.write(*extra)
                self.assertEqual(rc, 2)
                self.assertIn("overlap", err)
                self.assertEqual(out, "")
                self.assertEqual(pointer.read_bytes(), original)
                self.assertEqual(Path(self.canonical).read_bytes(), original)
                self.assertTrue(os.path.samefile(self.canonical, pointer))
                self.assertEqual(list(pointer.parent.iterdir()), [pointer])

    def test_task_id_defaults_to_codex_thread_id(self):
        previous = os.environ.get("CODEX_THREAD_ID")
        os.environ["CODEX_THREAD_ID"] = TASK
        try:
            rc, _, _ = self.call("--canonical", self.canonical, "--workspace", self.workspace)
        finally:
            if previous is None:
                os.environ.pop("CODEX_THREAD_ID", None)
            else:
                os.environ["CODEX_THREAD_ID"] = previous
        self.assertEqual(rc, 0)
        self.assertTrue(Path(guard.task_pointer_path(self.root, TASK)).is_file())

    def test_rejects_bad_inputs_without_writing(self):
        relative = "docs/handoffs/CURRENT_HANDOFF.md"
        for extra in ((), ("--seal",)):
            for argv in (["--canonical", self.canonical, "--task-id", "bad id", "--workspace", self.workspace],
                         ["--canonical", self.canonical, "--task-id", "", "--workspace", self.workspace],
                         ["--canonical", self.canonical, "--task-id", OTHER, "--workspace", self.workspace],
                         ["--canonical", os.path.join(self.workspace, "missing.md"), "--task-id", TASK, "--workspace", self.workspace],
                         ["--canonical", relative, "--task-id", TASK, "--workspace", self.workspace],
                         ["--canonical", self.canonical, "--task-id", TASK, "--workspace", os.path.join(self.workspace, "nope")]):
                with self.subTest(argv=argv, extra=extra):
                    rc, _, err = self.call(*argv, *extra)
                    self.assertEqual(rc, 2)
                    self.assertIn("ERROR", err)
        self.assertFalse((Path(self.workspace) / "docs" / "handoffs" / "by-task").exists())

    def test_cli_process(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        for extra, prefix in (([], "LOCATOR "), (["--seal"], "POINTER ")):
            with self.subTest(extra=extra):
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--canonical", self.canonical,
                                         "--task-id", TASK, "--workspace", self.workspace, *extra],
                                        capture_output=True, timeout=20, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.decode("utf-8").startswith(prefix))

    def test_utf8_locator_preserves_unicode_paths_under_non_utf8_locale(self):
        workspace = Path(self.workspace) / "中文路径-\U0001f9ea"
        workspace.mkdir()
        canonical = workspace / "交接.md"
        canonical.write_text(document(canonical, TASK), encoding="utf-8")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONIOENCODING="gbk", PYTHONUTF8="0")
        command = [sys.executable, "-S", "-B", str(SCRIPT), "--canonical", str(canonical),
                   "--task-id", TASK, "--workspace", str(workspace)]
        result = subprocess.run(command, capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        pointer = Path(guard.task_pointer_path(guard.normalized_root(str(workspace)), TASK))
        self.assertEqual(result.stdout.decode("utf-8").splitlines(), ["LOCATOR " + pointer.as_posix()])
        result = subprocess.run(command + ["--seal"], capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.decode("utf-8").splitlines()
        locator, _ = json.JSONDecoder().raw_decode(lines[1][lines[1].index("{"):])
        self.assertEqual(locator["workspace"], workspace.as_posix())
        self.assertEqual(locator["predecessor"], TASK)
        self.assertTrue(Path(locator["handoff"]).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
