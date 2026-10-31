#!/usr/bin/env python3
"""Offline fixtures only: synthetic transcripts in a temporary directory."""
import ast
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import context_budget_guard as budget

SCRIPT = Path(__file__).with_name("context_budget_guard.py")
WINDOW = 258400


def meta(thread_source="user", source="vscode"):
    return {"type": "session_meta", "payload": {"id": "fixture", "thread_source": thread_source, "source": source}}


def started():
    return {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "t"}}


def user(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                  "content": [{"type": "input_text", "text": text}]}}


def assistant(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                  "content": [{"type": "output_text", "text": text}]}}


def tokens(used, window=WINDOW):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "last_token_usage": {"input_tokens": used}, "model_context_window": window}}}


def compacted():
    return {"type": "compacted", "payload": {"message": "summary"}}


class BudgetGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="budget-guard-")
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def transcript(self, *records, first=None, filler=0):
        path = Path(self.directory) / "rollout.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(first or meta(), ensure_ascii=False) + "\n")
            line = json.dumps(assistant("x" * 1000)) + "\n"
            for _ in range(filler):
                handle.write(line)
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return str(path)

    def stop(self, path, message="完成本轮开发。", active=False):
        return {"hook_event_name": "Stop", "session_id": "fixture", "stop_hook_active": active,
                "transcript_path": path, "last_assistant_message": message}

    def high(self, *extra):
        return self.transcript(started(), user("继续开发"), tokens(int(WINDOW * 0.90)), *extra)

    def test_below_threshold_is_quiet(self):
        path = self.transcript(started(), user("继续"), tokens(int(WINDOW * 0.84)))
        self.assertEqual(budget.evaluate(self.stop(path), 0.85), {})

    def test_at_threshold_asks_for_handoff_once(self):
        result = budget.evaluate(self.stop(self.high()), 0.85)
        self.assertEqual(result["decision"], "block")
        self.assertIn("90%", result["reason"])
        self.assertIn("85%", result["reason"])
        self.assertIn(budget.READY_MARKER, result["reason"])
        self.assertIn("write_task_pointer.py", result["reason"])

    def test_continuation_never_loops(self):
        self.assertEqual(budget.evaluate(self.stop(self.high(), active=True), 0.85), {})

    def test_ready_reply_or_earlier_ready_since_compaction_is_quiet(self):
        self.assertEqual(budget.evaluate(self.stop(self.high(), budget.READY_MARKER + "\n接班行"), 0.85), {})
        path = self.transcript(started(), assistant(budget.READY_MARKER + " 已准备"), started(),
                               user("继续"), tokens(int(WINDOW * 0.91)))
        self.assertEqual(budget.evaluate(self.stop(path), 0.85), {})

    def test_ready_before_last_compaction_does_not_count(self):
        path = self.transcript(assistant(budget.READY_MARKER), compacted(), started(),
                               user("继续"), tokens(int(WINDOW * 0.88)))
        self.assertEqual(budget.evaluate(self.stop(path), 0.85)["decision"], "block")

    def test_marker_inside_injected_instruction_is_not_readiness(self):
        path = self.high(user("请回复 " + budget.READY_MARKER))
        self.assertEqual(budget.evaluate(self.stop(path), 0.85)["decision"], "block")

    def test_heartbeat_turns_are_skipped(self):
        self.assertEqual(budget.evaluate(self.stop(self.high(), "<heartbeat>\n<decision>DONT_NOTIFY</decision>"), 0.85), {})
        path = self.transcript(started(), user("<heartbeat>\n<automation_id>x</automation_id>"),
                               user("<skill><name>context-handoff</name>"), tokens(int(WINDOW * 0.93)))
        self.assertEqual(budget.evaluate(self.stop(path, "当前目标：…"), 0.85), {})

    def test_guardian_subagent_and_automation_threads_are_skipped(self):
        for first in (meta("guardian_review"), meta("subagent", {"subagent": {"other": "guardian"}}),
                      meta("automation"), meta("user", {"subagent": {"thread_spawn": {}}})):
            with self.subTest(first=first["payload"]):
                path = self.transcript(started(), user("x"), tokens(int(WINDOW * 0.95)), first=first)
                self.assertEqual(budget.evaluate(self.stop(path), 0.85), {})

    def test_agent_created_threads_are_covered(self):
        path = self.transcript(started(), user("接班"), tokens(int(WINDOW * 0.90)), first=meta("agent_created_thread"))
        self.assertEqual(budget.evaluate(self.stop(path), 0.85)["decision"], "block")

    def test_latest_usage_wins_after_compaction(self):
        path = self.transcript(tokens(int(WINDOW * 0.95)), compacted(), started(), user("继续"),
                               tokens(int(WINDOW * 0.30)))
        self.assertEqual(budget.evaluate(self.stop(path), 0.85), {})

    def test_missing_data_fails_open(self):
        cases = [self.transcript(started(), user("x")),                        # no token_count
                 self.transcript(started(), user("x"), tokens(0)),              # zero usage
                 self.transcript(started(), user("x"), tokens(10, window=0))]   # zero window
        for path in cases:
            with self.subTest(path=path):
                self.assertEqual(budget.evaluate(self.stop(path), 0.85), {})
        missing = os.path.join(self.directory, "missing.jsonl")
        self.assertEqual(budget.evaluate(self.stop(missing), 0.85), {})
        self.assertEqual(budget.evaluate({"hook_event_name": "SessionEnd"}, 0.85), {})
        self.assertEqual(budget.evaluate([], 0.85), {})

    def test_large_transcript_reads_only_tail(self):
        path = self.transcript(started(), user("继续"), tokens(int(WINDOW * 0.90)), filler=5000)
        self.assertGreater(os.path.getsize(path), budget.TAIL_BYTES)
        self.assertEqual(budget.evaluate(self.stop(path), 0.85)["decision"], "block")

    def test_threshold_arguments(self):
        self.assertEqual(budget.parse_threshold([]), 0.85)
        self.assertEqual(budget.parse_threshold(["--threshold", "0.05"]), 0.05)
        for args in (["--threshold"], ["--threshold", "1"], ["--threshold", "0"], ["--threshold", "x"],
                     ["--other", "0.5"], ["--threshold", "0.5", "extra"]):
            with self.subTest(args=args):
                self.assertIsNone(budget.parse_threshold(args))

    def test_run_wire_is_ascii_and_fails_open(self):
        path = self.high()
        out = io.BytesIO()
        raw = json.dumps(self.stop(path), ensure_ascii=False).encode("utf-8")
        self.assertEqual(budget.run([], io.BytesIO(raw), out), 0)
        self.assertEqual(json.loads(out.getvalue().decode("ascii"))["decision"], "block")
        for args, data in (([], b"not json"), ([], b"\xff"), ([], b""), (["--threshold", "2"], raw)):
            with self.subTest(args=args, data=data[:10]):
                out = io.BytesIO()
                self.assertEqual(budget.run(args, io.BytesIO(data), out), 0)
                self.assertEqual(json.loads(out.getvalue()), {})

    def test_reason_never_echoes_transcript_content(self):
        path = self.transcript(started(), user("SYNTHETIC-SECRET-PROMPT"), tokens(int(WINDOW * 0.9)))
        result = budget.evaluate(self.stop(path, "SYNTHETIC-SECRET-REPLY"), 0.85)
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result, ensure_ascii=False))

    def test_cli_under_gbk_console(self):
        env = dict(os.environ, PYTHONIOENCODING="gbk", PYTHONDONTWRITEBYTECODE="1")
        raw = json.dumps(self.stop(self.high()), ensure_ascii=False).encode("utf-8")
        result = subprocess.run([sys.executable, "-S", "-B", str(SCRIPT), "--threshold", "0.85"],
                                input=raw, capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout.decode("ascii"))["decision"], "block")

    def test_script_import_surface_is_stdlib_only(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(modules, {"json", "os", "sys", "handoff_config"})
        self.assertFalse(any(isinstance(n, ast.ImportFrom) for n in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
