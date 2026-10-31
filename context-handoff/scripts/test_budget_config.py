"""New offline safety/parameter/slimming coverage; only private temporary files."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import context_budget_guard as budget
import handoff_config as config
import handoff_entry as entry
import precompact_guard as guard
import slim_handoff as slim
import write_task_pointer as writer
from contextlib import redirect_stdout, redirect_stderr
from test_support import document
from validate_handoff import validate, section_bodies

TASK = "fixture-adjustable-001"


class NewBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="handoff-new-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "handoff.md"
        self.settings = dict(config.DEFAULTS)

    def settings_file(self, **changes):
        path = self.root / "settings.json"
        path.write_text(json.dumps(dict(self.settings, **changes)), encoding="utf-8")
        return path

    def event(self, percent=85, message="done", earlier=None):
        path = self.root / "transcript.jsonl"
        records = [{"type": "session_meta", "payload": {"id": TASK, "thread_source": "user"}}]
        if earlier:
            records.append({"type": "response_item", "payload": {
                "type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": earlier}]}})
        records.append({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": percent * 100}, "model_context_window": 10000}}})
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return {"hook_event_name": "Stop", "session_id": TASK, "transcript_path": str(path),
                "last_assistant_message": message}

    def budget_run(self, args, event):
        output = io.BytesIO()
        self.assertEqual(budget.run(args, io.BytesIO(json.dumps(event).encode()), output), 0)
        return json.loads(output.getvalue())

    def prepare_pointer(self):
        self.path.write_text(document(self.path, TASK), encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = writer.main(["--canonical", str(self.path), "--task-id", TASK, "--workspace", str(self.root), "--seal"])
        self.assertEqual(rc, 0)
        return Path(guard.task_pointer_path(self.root.as_posix(), TASK))

    def veto(self):
        return guard.decide(json.dumps({"hook_event_name": "PreCompact", "trigger": "manual",
                                        "session_id": TASK, "cwd": str(self.root)}).encode(), guard.ALL_SESSIONS)

    def drafts(self, state=None):
        state = state or "\n".join("- Evidence-%d: preserved original observation" % n for n in range(100))
        original = document(self.path, TASK, state)
        self.path.write_text(original, encoding="utf-8")
        expected = slim.digest(self.path.read_bytes())
        concise = document(self.path, TASK, "- Current outcome and remaining blocker preserved.", 2)
        concise += "\nHistorical evidence: HISTORY_THROUGH_R1.md; original SHA256 " + expected + "\n"
        candidate = self.root / "draft.md"
        candidate.write_text(concise, encoding="utf-8")
        return candidate, expected

    def test_slimming_keeps_an_existing_direction_card(self):
        candidate, expected = self.drafts()
        slim.prepare(self.path, candidate, TASK, expected, config.load_settings())
        candidate.write_text(candidate.read_text(encoding="utf-8").replace(
            "- Out of scope: any real task or workspace.", "- Out of scope: nothing."), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Direction card"):
            slim.prepare(self.path, candidate, TASK, expected, config.load_settings())

    def test_exact_85_percent_boundary(self):
        for percent, blocks in ((84, False), (85, True), (86, True)):
            result = self.budget_run([], self.event(percent))
            self.assertEqual(result.get("decision") == "block", blocks)

    def test_configurable_context_threshold_changes_behavior_without_code(self):
        path = self.settings_file(context_threshold=0.90)
        self.assertEqual(self.budget_run(["--config", str(path)], self.event(85)), {})
        self.assertEqual(self.budget_run(["--config", str(path)], self.event(90))["decision"], "block")

    def test_adjusted_document_limits_used_by_reminder_and_validator(self):
        path = self.settings_file(max_document_bytes=4096, max_current_state_lines=4)
        settings = config.load_settings(path)
        result = self.budget_run(["--config", str(path)], self.event())
        self.assertIn("4096", result["reason"])
        self.assertIn("4 个", result["reason"])
        self.path.write_text(document(self.path, TASK, "\n".join("fact" for _ in range(5))), encoding="utf-8")
        self.assertTrue(any("slimming threshold" in e for e in validate(self.path, 600, settings=settings)[0]))
        self.assertEqual(validate(self.path, 600)[0], [])

    def test_invalid_configuration_fails_open_in_hook_but_is_visible_in_cli(self):
        invalid = self.settings_file(context_threshold="85%")
        self.assertEqual(self.budget_run(["--config", str(invalid)], self.event()), {})
        result = subprocess.run([sys.executable, "-S", "-B", str(Path(config.__file__)),
                                 "--config", str(invalid)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr)

    def test_configuration_validation_rejects_boolean_nan_unknown_missing_and_duplicates(self):
        for changes in ({"context_threshold": True}, {"context_threshold": float("nan")},
                        {"context_threshold": 1}, {"max_document_bytes": 0},
                        {"max_current_state_lines": 1.5}, {"unknown": 3}):
            with self.subTest(changes=changes), self.assertRaises(config.ConfigError):
                config.load_settings(self.settings_file(**changes))
        path = self.root / "bad.json"
        for raw in ('{}', '{"context_threshold":0.8,"context_threshold":0.9}', '{'):
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(config.ConfigError):
                config.load_settings(path)

    def test_small_custom_limits_clamp_slimming_targets(self):
        small = dict(self.settings, max_document_bytes=3000, max_current_state_lines=4)
        self.assertEqual(config.slimming_targets(small), {"document_bytes": 2000, "current_state_lines": 3})

    def test_real_file_byte_limit_includes_crlf_and_bom(self):
        raw = b"\xef\xbb\xbf" + document(self.path, TASK).replace("\n", "\r\n").encode("utf-8")
        self.path.write_bytes(raw)
        for limit, over in ((len(raw) - 1, True), (len(raw), False), (len(raw) + 1, False)):
            with self.subTest(limit=limit):
                settings = dict(self.settings, max_document_bytes=limit)
                errors, _ = validate(self.path, 600, settings=settings)
                self.assertEqual(any("slimming threshold" in e for e in errors), over)
                if over:
                    with self.assertRaises(ValueError):
                        entry.canonical_info(self.path, TASK, settings)
                else:
                    self.assertEqual(entry.canonical_info(self.path, TASK, settings)["raw"], raw)

    def test_current_state_limit_ignores_blank_lines_and_blocks_only_above(self):
        for count, over in ((79, False), (80, False), (81, True)):
            with self.subTest(count=count):
                self.path.write_text(document(self.path, TASK, "\n\n".join("fact" for _ in range(count))),
                                     encoding="utf-8")
                errors, _ = validate(self.path, 600)
                self.assertEqual(any("slimming threshold" in e for e in errors), over)

    def test_ready_mention_is_not_a_readiness_receipt(self):
        for text in ("The documentation says CONTEXT_HANDOFF_READY", "```\nCONTEXT_HANDOFF_READY\n```"):
            self.assertEqual(self.budget_run([], self.event(message=text))["decision"], "block")
            self.assertEqual(self.budget_run([], self.event(earlier=text))["decision"], "block")
        self.assertEqual(self.budget_run([], self.event(message="CONTEXT_HANDOFF_READY\nNo continuation.")), {})

    def test_old_usage_before_compaction_is_not_current_usage(self):
        records = [{"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 90}, "model_context_window": 100}}},
                   {"type": "compacted", "payload": {}}]
        self.assertIsNone(budget.latest_usage(records))

    def test_wrong_or_missing_transcript_identity_is_ignored(self):
        event = self.event()
        event["session_id"] = "another-task"
        self.assertEqual(self.budget_run([], event), {})
        del event["session_id"]
        self.assertEqual(self.budget_run([], event), {})

    def test_valid_sealed_pointer_stops_then_content_change_releases(self):
        self.prepare_pointer()
        self.assertIs(self.veto()["continue"], False)
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\nNew material event.\n", encoding="utf-8")
        self.assertEqual(self.veto(), {})

    def test_wrong_owner_and_duplicate_metadata_do_not_create_pointer(self):
        for raw in (document(self.path, "other-task"),
                    document(self.path, TASK).replace("## Identity", "## Identity\n- Task or thread: `other-task`")):
            self.path.write_text(raw, encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rc = writer.main(["--canonical", str(self.path), "--task-id", TASK, "--workspace", str(self.root), "--seal"])
            self.assertEqual(rc, 2)
            self.assertFalse(Path(guard.task_pointer_path(self.root.as_posix(), TASK)).exists())

    def test_unsealed_empty_or_wrong_workspace_pointer_never_stops(self):
        pointer = self.prepare_pointer()
        valid = pointer.read_text(encoding="utf-8")
        for text in ("", "- Task or thread: `" + TASK + "`\n",
                     valid.replace(self.root.as_posix(), "Z:/wrong"),
                     valid + "- Task or thread: `duplicate`\n",
                     valid + "- Task or thread: unquoted-duplicate\n"):
            pointer.write_text(text, encoding="utf-8")
            self.assertEqual(self.veto(), {})

    def test_missing_canonical_releases(self):
        self.prepare_pointer()
        self.path.unlink()  # synthetic fixture only
        self.assertEqual(self.veto(), {})

    def test_slim_dry_run_writes_nothing_then_apply_retains_every_original_byte(self):
        candidate, expected = self.drafts()
        original, draft = self.path.read_bytes(), candidate.read_bytes()
        self.assertTrue(any("slimming threshold" in e for e in validate(self.path, 600)[0]))
        result = slim.execute(self.path, candidate, TASK, expected, self.settings)
        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.root / "HISTORY_THROUGH_R1.md").exists())
        result = slim.execute(self.path, candidate, TASK, expected, self.settings, apply=True)
        self.assertEqual(result["mode"], "applied")
        self.assertEqual(self.path.read_bytes(), draft)
        self.assertEqual((self.root / "HISTORY_THROUGH_R1.md").read_bytes(), original)
        self.assertEqual(validate(self.path, 600)[0], [])
        self.assertIn("Evidence-99", (self.root / "HISTORY_THROUGH_R1.md").read_text(encoding="utf-8"))

    def test_big_byte_document_is_preserved_and_slimmed(self):
        candidate, expected = self.drafts("Historical observation " * 4000)
        self.assertGreater(self.path.stat().st_size, 61440)
        original = self.path.read_bytes()
        slim.execute(self.path, candidate, TASK, expected, self.settings, apply=True)
        self.assertLess(self.path.stat().st_size, 40960)
        self.assertEqual((self.root / "HISTORY_THROUGH_R1.md").read_bytes(), original)

    def test_slim_rejects_history_same_as_canonical_without_writing(self):
        self.path = self.root / "HISTORY_THROUGH_R1.md"
        candidate, expected = self.drafts()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        for apply in (False, True):
            with self.subTest(apply=apply), self.assertRaisesRegex(ValueError, "overlap"):
                slim.execute(self.path, candidate, TASK, expected, self.settings, apply)
            self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_slim_rejects_history_same_as_draft_without_writing(self):
        candidate, expected = self.drafts()
        history = self.root / "HISTORY_THROUGH_R1.md"
        candidate.rename(history)  # unique synthetic draft only
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaisesRegex(ValueError, "overlap"):
            slim.execute(self.path, history, TASK, expected, self.settings, True)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_slim_rejects_hardlinked_history_without_writing(self):
        candidate, expected = self.drafts()
        history = self.root / "HISTORY_THROUGH_R1.md"
        os.link(self.path, history)
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaisesRegex(ValueError, "overlap"):
            slim.execute(self.path, candidate, TASK, expected, self.settings, True)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_slim_rejects_stale_input_and_does_not_overwrite_history(self):
        candidate, expected = self.drafts()
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            slim.execute(self.path, candidate, TASK, expected, self.settings, True)
        self.assertFalse((self.root / "HISTORY_THROUGH_R1.md").exists())
        candidate, expected = self.drafts()
        history = self.root / "HISTORY_THROUGH_R1.md"
        history.write_bytes(b"belongs to someone else")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "other content"):
            slim.execute(self.path, candidate, TASK, expected, self.settings, True)
        self.assertEqual(history.read_bytes(), b"belongs to someone else")
        self.assertEqual(self.path.read_bytes(), before)

    def test_slim_rejects_authority_change_or_missing_history_index(self):
        candidate, expected = self.drafts()
        draft = candidate.read_text(encoding="utf-8")
        for changed in (draft.replace("## Scope and constraints", "## Scope and constraints\nNEW AUTHORITY"),
                        draft.replace("HISTORY_THROUGH_R1.md", "NO_INDEX"),
                        draft.replace(TASK, "other-task")):
            candidate.write_text(changed, encoding="utf-8")
            with self.assertRaises(ValueError):
                slim.execute(self.path, candidate, TASK, expected, self.settings, True)
        self.assertEqual(slim.digest(self.path.read_bytes()), expected)

    def test_failed_publication_preserves_source_and_history_and_does_not_blindly_retry(self):
        candidate, expected = self.drafts()
        original = self.path.read_bytes()
        # Fault injection at the actual publication syscall, not mocking the helper.
        with patch.object(slim.os, "replace", side_effect=OSError("synthetic publication failure")):
            with self.assertRaises(OSError):
                slim.execute(self.path, candidate, TASK, expected, self.settings, True)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual((self.root / "HISTORY_THROUGH_R1.md").read_bytes(), original)
        self.assertFalse(self.path.with_name(self.path.name + ".slim.lock").exists())

    def test_invalid_config_cli_never_replaces_canonical(self):
        candidate, expected = self.drafts()
        invalid = self.settings_file(max_current_state_lines=0)
        result = subprocess.run([sys.executable, "-S", "-B", str(Path(slim.__file__)),
                                 "--canonical", str(self.path), "--candidate", str(candidate),
                                 "--task-id", TASK, "--expected-sha256", expected,
                                 "--config", str(invalid), "--apply"], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(slim.digest(self.path.read_bytes()), expected)

    def test_custom_settings_flow_through_slimming_writer_and_veto(self):
        settings_path = self.settings_file(max_document_bytes=6000, max_current_state_lines=4)
        settings = config.load_settings(settings_path)
        candidate, expected = self.drafts()
        slim.execute(self.path, candidate, TASK, expected, settings, True)
        self.assertLessEqual(self.path.stat().st_size, config.slimming_targets(settings)["document_bytes"])
        self.assertEqual(validate(self.path, 600, settings=settings)[0], [])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = writer.main(["--canonical", str(self.path), "--task-id", TASK,
                              "--workspace", str(self.root), "--config", str(settings_path), "--seal"])
        self.assertEqual(rc, 0)
        raw = json.dumps({"hook_event_name": "PreCompact", "trigger": "auto",
                          "session_id": TASK, "cwd": str(self.root)}).encode()
        output = io.BytesIO()
        self.assertEqual(guard.run(["--all-sessions", "--config", str(settings_path)], io.BytesIO(raw), output), 0)
        self.assertIs(json.loads(output.getvalue())["continue"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
