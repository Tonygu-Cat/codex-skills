from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "stop_guard.py"
SPEC = importlib.util.spec_from_file_location("stop_guard", SCRIPT)
assert SPEC and SPEC.loader
stop_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stop_guard)


def event(message: str, *, active: bool = True, repeated: bool = False) -> dict:
    return {
        "hook_event_name": "Stop",
        "stop_hook_active": repeated,
        "last_assistant_message": (
            f"{stop_guard.ACTIVATION_RECEIPT}\n{message}" if active else message
        ),
    }


class StopGuardTests(unittest.TestCase):
    def test_inactive_task_passes(self) -> None:
        self.assertEqual(stop_guard.evaluate(event("T4-R2 已失败关闭。", active=False)), {})

    def test_failure_without_continuation_fields_is_blocked(self) -> None:
        result = stop_guard.evaluate(event("T4-R2 已失败关闭，未重试。"))
        self.assertEqual(result["decision"], "block")
        self.assertIn("当前目标", result["reason"])
        self.assertIn("下一步", result["reason"])
        self.assertIn("用户操作", result["reason"])

    def test_complete_failure_handoff_passes(self) -> None:
        message = """状态：T4-R2 已失败关闭。
当前目标：active，目标仍可继续。
下一步：执行 T4-R3 恢复。
用户操作：需要新的单次授权。
请回复：批准执行 T4-R3。"""
        self.assertEqual(stop_guard.evaluate(event(message)), {})

    def test_success_response_passes(self) -> None:
        self.assertEqual(stop_guard.evaluate(event("任务已完成并验证。用户操作：none。")), {})

    def test_resolved_failure_wording_does_not_false_positive(self) -> None:
        message = "All previously failed tests now pass. User action: none."
        self.assertEqual(stop_guard.evaluate(event(message)), {})

    def test_prior_transcript_receipt_activates_later_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "rollout.jsonl"
            transcript.write_text(stop_guard.ACTIVATION_RECEIPT, encoding="utf-8")
            result = stop_guard.evaluate(
                {
                    "hook_event_name": "Stop",
                    "stop_hook_active": False,
                    "transcript_path": str(transcript),
                    "last_assistant_message": "Status: failed.",
                }
            )
        self.assertEqual(result["decision"], "block")

    def test_second_stop_never_loops(self) -> None:
        self.assertEqual(
            stop_guard.evaluate(event("T4-R2 已失败关闭。", repeated=True)), {}
        )


    def test_success_without_user_action_is_corrected(self) -> None:
        self.assertEqual(stop_guard.evaluate(event("代码修改完成。"))["decision"], "block")

    def test_success_milestone_with_pending_authorization_is_corrected(self) -> None:
        for text in ("已完成代码修改，部署尚待授权。", "Implementation complete; deployment pending approval.",
                     "已完成，仍需选择最终方案。", "代码已完成。待办：运行验收。"):
            with self.subTest(text=text):
                result = stop_guard.evaluate(event(text + "\n用户操作：请回复批准。"))
                self.assertEqual(result["decision"], "block")
                self.assertIn("下一步", result["reason"])

    def test_pending_milestone_with_concrete_handoff_passes(self) -> None:
        text = "代码已完成，部署尚待授权。\n当前目标：等待部署授权。\n下一步：批准后部署已验证版本。\n用户操作：请回复‘批准部署’。"
        self.assertEqual(stop_guard.evaluate(event(text)), {})

    def test_optional_followup_is_not_a_required_blocker(self) -> None:
        for text in ("任务已完成。可选建议：部署需另行授权。用户操作：无需。",
                     "Done. Optional TODO: add a theme. User action: none.",
                     "任务已完成，无待办。用户操作：无需。"):
            with self.subTest(text=text):
                self.assertEqual(stop_guard.evaluate(event(text)), {})

    def test_nonempty_fields_required(self) -> None:
        for text in ("代码已完成。用户操作：", "已失败。当前目标：\n下一步：\n用户操作：请回复批准。"):
            with self.subTest(text=text):
                self.assertEqual(stop_guard.evaluate(event(text))["decision"], "block")

    def test_bold_fields_accepted(self) -> None:
        self.assertEqual(stop_guard.evaluate(event("Done.\n**User action:** none.")), {})

    def test_heartbeat_reply_is_not_checked(self) -> None:
        reply = ("<heartbeat>\n  <automation_id>example-automation</automation_id>\n"
                 "  <decision>DONT_NOTIFY</decision>\n  <message>无变化，仍待授权。</message>\n</heartbeat>")
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "rollout.jsonl"
            transcript.write_text(stop_guard.ACTIVATION_RECEIPT, encoding="utf-8")
            def stop(message: str) -> dict:
                return {"hook_event_name": "Stop", "stop_hook_active": False,
                        "transcript_path": str(transcript), "last_assistant_message": message}
            self.assertEqual(stop_guard.evaluate(stop(reply)), {})
            self.assertEqual(stop_guard.evaluate(stop("  " + reply)), {})
            # The same pending text outside a heartbeat reply is still checked.
            self.assertEqual(stop_guard.evaluate(stop("无变化，仍待授权。"))["decision"], "block")

    def test_short_answer_without_opt_in_passes(self) -> None:
        self.assertEqual(stop_guard.evaluate(event("北京。", active=False)), {})

    def test_wrong_event_and_missing_message_pass(self) -> None:
        self.assertEqual(stop_guard.evaluate({"hook_event_name": "Stop"}), {})
        self.assertEqual(stop_guard.evaluate(dict(event("失败。"), hook_event_name="SessionEnd")), {})

    def test_missing_transcript_does_not_activate(self) -> None:
        payload = event("当前阻塞。", active=False)
        payload["transcript_path"] = str(Path(tempfile.gettempdir()) / "nonexistent-task-ops-transcript-2538.jsonl")
        self.assertEqual(stop_guard.evaluate(payload), {})

    def test_utf8_wire_under_gbk_console(self) -> None:
        env = dict(os.environ, PYTHONIOENCODING="gbk")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)], input=json.dumps(
            event("已完成代码修改，部署尚待授权。"), ensure_ascii=False).encode("utf-8"),
            capture_output=True, env=env, check=True)
        self.assertEqual(json.loads(result.stdout.decode("ascii"))["decision"], "block")

    def test_malformed_wire_fails_open(self) -> None:
        for data in (b"not json", b"\xff", b"[]"):
            with self.subTest(data=data):
                result = subprocess.run([sys.executable, "-B", str(SCRIPT)], input=data,
                                        capture_output=True, check=True)
                self.assertEqual(json.loads(result.stdout), {})

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell integration")
    def test_powershell_quoted_command_invokes_guard(self) -> None:
        shell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(shell, "Windows installation needs its host shell tested")
        def quoted(path: str) -> str:
            return "'" + path.replace("'", "''") + "'"
        command = "& " + quoted(sys.executable) + " -B " + quoted(str(SCRIPT))
        result = subprocess.run([shell, "-NoProfile", "-Command", command],
                                input=json.dumps(event("代码完成，部署尚待授权。"), ensure_ascii=False).encode("utf-8"),
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
