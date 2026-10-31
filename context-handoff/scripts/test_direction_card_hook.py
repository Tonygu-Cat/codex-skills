#!/usr/bin/env python3
"""Offline fixtures only: synthetic transcripts and documents under temporary folders."""
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import direction_card_hook as hook
import handoff_entry
import write_task_pointer as writer
from handoff_config import load_settings
from test_support import document

SCRIPT = Path(__file__).with_name("direction_card_hook.py")
TASK = "01a0fixture-0000-7000-8000-000000000001"
OTHER = "01a0fixture-0000-7000-8000-000000000002"
T = "2026-09-27T10:00:00.000Z"


def line(record):
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def meta(source="user"):
    return {"timestamp": T, "type": "session_meta", "payload": {"id": TASK, "thread_source": source}}


def user(text, kinds=("user.text",)):
    return {"timestamp": T, "ordinal": 1, "type": "response_item",
            "payload": {"type": "message", "id": "msg_fixture", "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                        "internal_chat_message_metadata_passthrough": {"content_item_kinds": list(kinds)}}}


def started(trigger, turn="t"):
    return {"timestamp": T, "ordinal": 0, "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": turn,
                        "turn_attribution": {"turn_id": turn, "turn_trigger": trigger}}}


def assistant(text):
    return {"timestamp": T, "ordinal": 5, "type": "response_item",
            "payload": {"type": "message", "id": "msg_reply", "role": "assistant",
                        "content": [{"type": "output_text", "text": text}]}}


def relayed_message(text):
    # How another task's message arrives (send_message_to_thread output), not a user message.
    return {"timestamp": T, "ordinal": 6, "type": "response_item",
            "payload": {"type": "function_call_output", "id": "fco", "name": "send_message_to_thread", "output": text}}


def injection(text, turn):
    return {"timestamp": T, "ordinal": 4, "type": "response_item",
            "payload": {"type": "message", "id": "msg_hook", "role": "developer",
                        "content": [{"type": "input_text", "text": text}],
                        "internal_chat_message_metadata_passthrough": {"turn_id": turn,
                                                                       "content_item_kinds": ["hooks.additional_context"]}}}


def compacted(number):
    history = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<heartbeat> old"}]}]
    return {"timestamp": T, "ordinal": 2, "type": "compacted",
            "payload": {"message": "", "replacement_history": history, "window_number": number}}


def tokens(used, window=258400):
    return {"timestamp": T, "ordinal": 3, "type": "event_msg",
            "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": used},
                                                        "model_context_window": window}}}


class DirectionCardHookTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="direction-card-")
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.canonical = os.path.join(self.workspace, "docs", "handoffs", "CURRENT_HANDOFF.md")
        os.makedirs(os.path.dirname(self.canonical))
        self.config = os.path.join(self.workspace, "settings.json")
        Path(self.config).write_text(json.dumps({
            "max_document_bytes": 61440, "max_current_state_lines": 80, "handoff_reminder_compactions": 3,
            "handoff_reminder_residue": 0.25, "direction_card_max_chars": 300}), encoding="utf-8")
        self.settings = load_settings(self.config)
        self.transcript = os.path.join(self.workspace, "rollout.jsonl")
        # A private Codex home keeps the by-ID transcript lookup away from this machine's sessions.
        self.codex_home = os.path.join(self.workspace, "codex-home")
        os.makedirs(os.path.join(self.codex_home, "sessions"))
        previous = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = self.codex_home
        self.addCleanup(lambda: os.environ.__setitem__("CODEX_HOME", previous) if previous is not None
                        else os.environ.pop("CODEX_HOME", None))

    def handoff(self, *extra, **fields):
        Path(self.canonical).write_text(document(self.canonical, **dict({"task": TASK}, **fields)), encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = writer.main(["--canonical", self.canonical, "--task-id", TASK, "--workspace", self.workspace, *extra])
        self.assertEqual(rc, 0)

    def records(self, *records):
        Path(self.transcript).write_text("\n".join(line(item) for item in (meta(),) + records) + "\n", encoding="utf-8")

    def event(self, **changes):
        return dict({"hook_event_name": "SessionStart", "source": "compact", "session_id": TASK,
                     "cwd": self.workspace, "transcript_path": None, "model": "fixture",
                     "permission_mode": "default"}, **changes)

    def context(self, **changes):
        result = hook.build(self.event(**changes), self.settings)
        if not result:
            return None
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "SessionStart")
        return result["hookSpecificOutput"]["additionalContext"]

    def test_only_compact_session_start_events(self):
        self.handoff()
        for changes in ({"source": "startup"}, {"source": "resume"}, {"source": "clear"}, {"source": "fork"},
                        {"hook_event_name": "PreCompact"}, {"session_id": "bad id"}, {"cwd": "relative/dir"}):
            with self.subTest(changes=changes):
                self.assertEqual(hook.build(self.event(**changes), self.settings), {})

    def test_injects_card_from_routine_locator(self):
        self.handoff()
        context = self.context()
        self.assertIn(hook.MARKER, context)
        self.assertIn("<direction_card>\n- Goal: synthetic fixture only.", context)
        self.assertIn("revision 1", context)
        self.assertIn(self.canonical.replace("\\", "/"), context)
        self.assertNotIn("Handoff reminder", context)

    def test_sealed_pointer_also_injects(self):
        self.handoff("--seal")
        self.assertIn("synthetic fixture only", self.context())

    def test_card_derived_from_objective_when_section_missing(self):
        self.handoff(card=None)
        context = self.context()
        self.assertIn("derived from Objective/Scope/Next", context)
        self.assertIn("Objective and completion criteria:", context)
        self.assertIn("First next action: 1. [agent] Continue synthetic fixture only.", context)

    def test_card_truncated_to_configured_limit(self):
        self.handoff(card="- Goal: " + "long direction " * 60)
        card = re.search(r"<direction_card>\n(.*)\n</direction_card>", self.context(), re.DOTALL).group(1)
        self.assertLessEqual(len(card), 300)
        self.assertTrue(card.endswith("[truncated; read the canonical document]"))

    def test_no_card_for_foreign_owner_closed_task_or_other_session(self):
        self.handoff()
        self.assertIsNone(self.context(session_id=OTHER))
        Path(self.canonical).write_text(document(self.canonical, OTHER), encoding="utf-8")
        self.assertIsNone(self.context())
        Path(self.canonical).write_text(document(self.canonical, TASK).replace("`active`", "`complete`"), encoding="utf-8")
        self.assertIsNone(self.context())

    def test_successor_owning_a_transferred_document_gets_its_card(self):
        # Real case 2026-10-19: after manual-paste takeover the successor owns a "transferred" document.
        self.handoff()
        Path(self.canonical).write_text(document(self.canonical, TASK).replace("`active`", "`transferred`"), encoding="utf-8")
        self.assertIn("synthetic fixture only", self.context())
        Path(self.canonical).write_text(document(self.canonical, OTHER).replace("`active`", "`transferred`"), encoding="utf-8")
        self.assertIsNone(self.context(), "the predecessor never gets the successor's card")

    def test_reminder_at_compaction_threshold(self):
        self.handoff()
        self.records(user("继续"), compacted(2), tokens(0))
        self.assertNotIn("Handoff reminder", self.context(transcript_path=self.transcript))
        self.records(user("继续"), compacted(2), tokens(0), tokens(20000), compacted(3), tokens(0))
        context = self.context(transcript_path=self.transcript)
        self.assertIn("compaction #3 of this thread", context)
        self.assertIn("Handoff reminder (soft fallback): this thread has compacted 3 times.", context)
        self.assertIn("synthetic fixture only", context)

    def test_reminder_on_high_residue_of_previous_compaction(self):
        self.handoff()
        for used, reminded in ((80000, True), (40000, False)):
            with self.subTest(used=used):
                self.records(user("继续"), compacted(1), tokens(0), tokens(used), tokens(200000), compacted(2), tokens(0))
                context = self.context(transcript_path=self.transcript)
                self.assertEqual("Handoff reminder" in context, reminded)
                if reminded:
                    self.assertIn("the previous compaction still left 31% of the context window in use", context)

    def test_unflushed_compaction_counts_one_more(self):
        self.handoff()
        self.records(user("继续"), compacted(2), tokens(0), tokens(70000))
        context = self.context(transcript_path=self.transcript)
        self.assertIn("compacted 3 times and the previous compaction still left 27%", context)

    def test_heartbeat_turn_keeps_card_without_reminder(self):
        self.handoff()
        heartbeat = user("<heartbeat>\r\n  <automation_id>fixture</automation_id>")
        skill = user("<skill>\n<name>context-handoff</name>", kinds=("skills.selected_skill_instructions",))
        hook_prompt = user('<hook_prompt hook_run_id="stop:0">', kinds=("unknown",))
        self.records(user("继续"), heartbeat, skill, hook_prompt, compacted(5), tokens(0))
        context = self.context(transcript_path=self.transcript)
        self.assertIn("synthetic fixture only", context)
        self.assertNotIn("Handoff reminder", context)
        self.records(heartbeat, skill, user("下一步做什么"), compacted(5), tokens(0))
        self.assertIn("Handoff reminder", self.context(transcript_path=self.transcript))

    def test_heartbeat_tagged_by_kind_keeps_card_without_reminder(self):
        # Newer desktop builds tag the heartbeat prompt "user.heartbeat" and add environment context after it.
        self.handoff()
        heartbeat = user("<heartbeat>\r\n  <automation_id>fixture</automation_id>", kinds=("user.heartbeat",))
        environment = user("<environment_context>\n  <current_date>", kinds=("environments.environment_context",))
        self.records(user("继续"), heartbeat, environment, compacted(5), tokens(0))
        context = self.context(transcript_path=self.transcript)
        self.assertIn("synthetic fixture only", context)
        self.assertNotIn("Handoff reminder", context)
        self.records(heartbeat, environment, user("下一步做什么"), compacted(5), tokens(0))
        self.assertIn("Handoff reminder", self.context(transcript_path=self.transcript))

    def test_turn_trigger_decides_when_recorded(self):
        # Real case 2026-10-14: a heartbeat, then turns relayed by another task that add no user text.
        self.handoff()
        heartbeat = user("<heartbeat>\r\n  <automation_id>fixture</automation_id>", kinds=("user.heartbeat",))
        cases = (("automation_heartbeat_scheduled", (user("继续"),), False),
                 ("app_tool_send_message", (heartbeat,), True),
                 ("composer", (heartbeat, user("继续")), True))
        for trigger, inputs, reminded in cases:
            with self.subTest(trigger=trigger):
                self.records(*inputs, started(trigger), compacted(5), tokens(0))
                self.assertEqual("Handoff reminder" in self.context(transcript_path=self.transcript), reminded)

    def test_reminder_without_document_asks_to_create_one_first(self):
        self.records(user("继续"), compacted(3), tokens(0))
        context = self.context(transcript_path=self.transcript)
        self.assertIn("Handoff reminder", context)
        self.assertIn("No handoff document is registered", context)
        self.assertNotIn("<direction_card>", context)

    def test_guardian_subagent_and_automation_threads_get_nothing(self):
        self.handoff()
        for source in ("guardian_review", "subagent", "automation"):
            with self.subTest(source=source):
                Path(self.transcript).write_text(line(meta(source)) + "\n" + line(compacted(9)) + "\n", encoding="utf-8")
                self.assertIsNone(self.context(transcript_path=self.transcript))

    def test_desktop_extended_length_paths_are_accepted(self):
        # The desktop app reports paths as \\?\D:\...; 2026-09-27..10-14 this silently disabled reminders.
        self.handoff()
        self.records(user("继续"), compacted(3), tokens(0))
        context = self.context(transcript_path="\\\\?\\" + self.transcript, cwd="\\\\?\\" + self.workspace)
        self.assertIn("synthetic fixture only", context)
        self.assertIn("Handoff reminder (soft fallback): this thread has compacted 3 times.", context)
        unc = "\\\\?\\UNC\\server\\share\\rollout.jsonl"
        self.assertEqual(handoff_entry.plain_path(unc), unc)
        self.assertFalse(handoff_entry.local_absolute(handoff_entry.plain_path(unc)))

    def test_transcript_found_by_session_id_when_path_missing_or_unusable(self):
        folder = os.path.join(self.codex_home, "sessions", "2026", "10", "14")
        os.makedirs(folder)
        self.transcript = os.path.join(folder, "rollout-2026-10-14T00-00-00-%s.jsonl" % TASK)
        self.records(user("继续"), compacted(3), tokens(0))
        for path in (None, "relative/rollout.jsonl", os.path.join(self.workspace, "missing.jsonl")):
            with self.subTest(path=path):
                self.assertIn("compacted 3 times", self.context(transcript_path=path))
        self.assertIsNone(self.context(session_id=OTHER), "another session's rollout is never used")

    def test_escaped_records_inside_messages_are_not_counted(self):
        self.records(user('{"type":"compacted","payload":{"window_number":99}}'), tokens(250000))
        self.assertIsNone(self.context(transcript_path=self.transcript))

    def prompt(self, text="继续", turn="cur", **changes):
        event = dict({"hook_event_name": "UserPromptSubmit", "session_id": TASK, "cwd": self.workspace,
                      "transcript_path": self.transcript, "model": "fixture", "permission_mode": "default",
                      "prompt": text, "turn_id": turn}, **changes)
        result = hook.build(event, self.settings)
        if not result:
            return None
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        return result["hookSpecificOutput"]["additionalContext"]

    RED = "🔴 **交接提醒：本会话已压缩 3 次，上下文越来越满，建议在当前步骤完成后交接。**\n\n正文……"

    def test_unanswered_reminder_escalates_on_next_user_turn_then_every_repeat(self):
        # User rule 2026-10-19: missed -> red bold on the next reply, then every 4 of the user's own replies,
        # anchored on our reply that carried the red line; heartbeats and relayed messages do not count.
        normal = injection("Handoff reminder (soft fallback): this thread has compacted 3 times.", "t1")
        self.records(started("composer", "t1"), compacted(3), tokens(0), tokens(9000), normal, assistant("建议交接。"))
        context = self.prompt(turn="t2")
        self.assertIn(hook.ESCALATION_MARKER, context)
        self.assertIn("🔴 **交接提醒：本会话已压缩 3 次", context)
        history = [started("composer", "t1"), compacted(3), tokens(0), tokens(9000), normal,
                   started("composer", "t2"), assistant(self.RED)]
        others = [started("automation_heartbeat_scheduled", "hb%d" % n) for n in range(3)] + \
                 [started("app_tool_send_message", "relay%d" % n) for n in range(3)]
        for done, due in ((0, False), (1, False), (2, False), (3, True)):
            with self.subTest(own_turns_after=done):
                own = [started("composer", "t%d" % (3 + n)) for n in range(done)]
                self.records(*(history + others + own))
                self.assertEqual(self.prompt(turn="now") is not None, due)

    def test_missing_red_line_in_our_reply_is_raised_again(self):
        normal = injection("Handoff reminder (soft fallback): this thread has compacted 3 times.", "t1")
        self.records(started("composer", "t1"), compacted(3), tokens(0), normal,
                     started("composer", "t2"), assistant("没有写红线的回复"), started("composer", "t3"))
        self.assertIsNotNone(self.prompt(turn="t4"))

    def test_mentioning_handoff_pauses_until_the_next_compaction_reminder(self):
        normal = injection("Handoff reminder (soft fallback): this thread has compacted 3 times.", "t1")
        answered = [started("composer", "t1"), compacted(3), tokens(0), normal,
                    started("composer", "t2"), user("暂不交接，先把这个阶段做完"), assistant("好的")]
        later = [started("composer", "t%d" % n) for n in range(3, 12)]
        self.records(*(answered + later))
        self.assertIsNone(self.prompt(turn="now"), "answered: no red line however many turns pass")
        again = injection("Handoff reminder (soft fallback): this thread has compacted 4 times.", "t12")
        self.records(*(answered + later + [compacted(4), tokens(0), again]))
        self.assertIsNotNone(self.prompt(turn="now"), "a new compaction reminder restarts the cycle")
        relayed = [started("composer", "t1"), compacted(3), tokens(0), normal,
                   started("app_tool_send_message", "r1"), relayed_message("交接文档已更新")]
        self.records(*relayed)
        self.assertIsNotNone(self.prompt(turn="now"), "another task's words are not the user's answer")

    def test_relayed_turn_itself_never_gets_the_red_line(self):
        normal = injection("Handoff reminder (soft fallback): this thread has compacted 3 times.", "t1")
        self.records(started("composer", "t1"), compacted(3), tokens(0), normal, started("app_tool_send_message", "cur"))
        self.assertIsNone(self.prompt(turn="cur"))

    def test_escalation_skips_handoff_prompts_heartbeats_sealed_and_small_threads(self):
        normal = injection("Handoff reminder (soft fallback): this thread has compacted 3 times.", "t1")
        self.records(started("composer", "t1"), compacted(3), tokens(0), normal)
        self.assertIsNone(self.prompt("交接"))
        self.assertIsNone(self.prompt("<heartbeat>\n<automation_id>x</automation_id>"))
        self.records(started("composer", "t1"), compacted(3), tokens(0), normal, started("automation_heartbeat_scheduled", "cur"))
        self.assertIsNone(self.prompt(turn="cur"), "automation turns never escalate")
        self.records(started("composer", "t1"), compacted(2), tokens(0), tokens(9000))
        self.assertIsNone(self.prompt(), "below both thresholds")
        self.records(started("composer", "t1"), compacted(3), tokens(0), normal)
        self.handoff("--seal")
        self.assertIsNone(self.prompt(), "a sealed handoff is already under way")

    def test_repeat_interval_setting_is_validated(self):
        from handoff_config import ConfigError, DEFAULTS, validate_settings
        self.assertEqual(validate_settings(dict(DEFAULTS))["handoff_reminder_repeat_turns"], 4)
        for bad in (0, 101, "4", True, 2.0):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                validate_settings(dict(DEFAULTS, handoff_reminder_repeat_turns=bad))

    def test_escalation_without_any_earlier_reminder_in_the_tail(self):
        self.records(user("继续"), compacted(1), tokens(0), tokens(90000))
        context = self.prompt()
        self.assertIn("上次压缩后仍占用 35%", context)

    def test_reads_only_a_bounded_tail(self):
        original = hook.TAIL_BYTES
        hook.TAIL_BYTES = 4096
        self.addCleanup(setattr, hook, "TAIL_BYTES", original)
        filler = [user("filler " * 40) for _ in range(60)]
        self.records(compacted(7), tokens(0), *filler)
        self.assertIsNone(self.context(transcript_path=self.transcript), "a compaction outside the tail is not seen")
        self.records(*filler, compacted(7), tokens(0))
        self.assertIn("compacted 7 times", self.context(transcript_path=self.transcript))

    def test_cli_fails_open_and_emits_context(self):
        self.handoff()
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        cases = ((["--config", self.config], b"not json", {}),
                 (["--config", os.path.join(self.workspace, "missing.json")], json.dumps(self.event()).encode(), {}),
                 (["--unknown"], json.dumps(self.event()).encode(), {}))
        for args, stdin, expected in cases:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, "-S", "-B", str(SCRIPT), *args], input=stdin,
                                        capture_output=True, timeout=20, env=env)
                self.assertEqual((result.returncode, json.loads(result.stdout)), (0, expected))
        result = subprocess.run([sys.executable, "-S", "-B", str(SCRIPT), "--config", self.config],
                                input=json.dumps(self.event()).encode(), capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("synthetic fixture only", json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
