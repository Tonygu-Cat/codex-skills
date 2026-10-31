"""Offline regression tests: no task creation, archival, messages, or network calls."""

import re
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

from validate_handoff import REQUIRED_SECTIONS, validate


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.identity = {
            "Task or thread": "task-new",
            "Predecessor task": "task-old",
            "Successor task": "task-new",
            "Rollover generation": "1",
            "Handoff revision": "3",
            "Updated at": "2026-09-07T12:00:00+08:00",
            "Status": "active",
        }
        self.lifecycle = {
            "Policy source": "user instruction turn-archive, 2026-09-07",
            "Predecessor disposition": "archive-after-takeover",
            "Predecessor observed state": "archived",
            "Archive verification": "native result archive-1: task-old archived at 2026-09-07T11:58:00+08:00",
            "Successor policy acknowledgement": "task-new response ack-1 confirms turn-archive policy",
            "Result destination": "current-task-user",
        }

        self.safety = {
            "Work scope ID": "scope-01", "Scope boundary": "repo:/fixture/source; user-scope-1",
            "Resource overlap check": "allocation receipt overlap-1",
            "Boundary ID": "boundary-01", "Owner epoch": "1",
            "Execution mode": "manual", "Create outcome": "confirmed",
            "Successor workspace": "new", "Working tree disposition": "clean",
            "Preservation evidence": "manifest-1; target revision and artifacts readback-1",
            "Quiescence evidence": "old task stopped; in-flight receipt drain-1",
            "Write isolation": "verified", "Uncovered write paths": "none",
            "Coverage evidence": "resource-route inventory and enforcement receipts fence-1",
            "Archive executor": "task-new", "Archive isolation evidence": "exact target impact receipt archive-scope-1",
            "Controller evidence": "not-applicable",
        }

    def document(self, include_lifecycle=True, include_safety=True):
        parts = ["# Project Handoff"]
        for section in REQUIRED_SECTIONS:
            body = "Verified fixture state; no external actions."
            if section == "Identity":
                body = "\n".join(f"- {key}: `{value}`" for key, value in self.identity.items())
            elif section == "Next exact actions":
                body = ("1. [agent] Continue the verified fixture action.\n\n"
                        "- User action now: none\n- Ready-to-send reply: not needed")
            parts.append(f"## {section}\n\n{body}")
        if include_lifecycle:
            body = "\n".join(f"- {key}: `{value}`" for key, value in self.lifecycle.items())
            parts.insert(2, "## Task lifecycle\n\n" + body)
        if include_safety and self.safety:
            body = "\n".join(f"- {key}: `{value}`" for key, value in self.safety.items())
            parts.insert(2, "## Transfer safety\n\n" + body)
        return "\n\n".join(parts) + "\n"

    def check(self, *, closed=False, strict=True, safety=False, document=None):
        with tempfile.TemporaryDirectory(prefix="handoff-validator-") as directory:
            path = Path(directory) / "handoff.md"
            path.write_text(document if document is not None else self.document(), encoding="utf-8")
            return validate(path, 600, strict, closed, safety)

    def test_verified_archive_closes(self):
        self.assertEqual(self.check(closed=True)[0], [])

    def test_archive_requested_is_not_archive_confirmed(self):
        self.lifecycle["Predecessor observed state"] = "active"
        self.lifecycle["Archive verification"] = "pending"
        self.assertEqual(self.check()[0], [])
        self.assertTrue(self.check(closed=True)[0])

    def test_missing_archive_evidence_rejected(self):
        self.lifecycle["Archive verification"] = "pending"
        self.assertTrue(self.check()[0])

    def test_unacknowledged_policy_not_closed(self):
        self.lifecycle["Successor policy acknowledgement"] = "pending"
        self.assertTrue(self.check(closed=True)[0])

    def test_old_retention_conflicts_with_observed_archive(self):
        self.lifecycle["Predecessor disposition"] = "retain-by-explicit-request"
        self.assertTrue(self.check()[0])

    def test_latest_explicit_retention_is_supported(self):
        self.lifecycle["Predecessor disposition"] = "retain-by-explicit-request"
        self.lifecycle["Predecessor observed state"] = "active"
        self.lifecycle["Archive verification"] = "native lookup state-1: task-old unarchived, 2026-09-07"
        self.assertEqual(self.check(closed=True)[0], [])

    def test_predecessor_message_relay_rejected(self):
        self.lifecycle["Result destination"] = "task-old"
        self.assertTrue(self.check()[0])

    def test_same_id_for_two_generations_rejected(self):
        self.identity["Successor task"] = "task-old"
        self.identity["Task or thread"] = "task-old"
        self.assertTrue(self.check()[0])

    def test_predecessor_cannot_remain_execution_owner(self):
        self.identity["Task or thread"] = "task-old"
        self.assertTrue(self.check()[0])

    def test_retry_preserves_created_successor_while_waiting(self):
        self.identity["Status"] = "handoff-ready"
        self.identity["Task or thread"] = "task-old"
        self.lifecycle["Predecessor observed state"] = "active"
        self.lifecycle["Archive verification"] = "pending"
        self.lifecycle["Successor policy acknowledgement"] = "pending"
        self.assertEqual(self.check()[0], [])
        self.assertTrue(self.check(closed=True)[0])
        self.identity["Successor task"] = "pending"
        self.safety["Create outcome"] = "pending"
        self.assertEqual(self.check()[0], [])

    def test_transfer_requires_policy_acknowledgement(self):
        self.identity["Status"] = "transferred"
        self.lifecycle["Successor policy acknowledgement"] = "pending"
        self.assertTrue(self.check()[0])

    def test_successor_owner_requires_ack_in_every_post_transfer_status(self):
        self.lifecycle.update({"Predecessor observed state": "active",
                               "Archive verification": "pending",
                               "Successor policy acknowledgement": "pending"})
        for status in ("active", "ready-for-review", "complete", "blocked", "transferred"):
            with self.subTest(status=status):
                self.identity["Status"] = status
                self.assertIn("transferred ownership requires acknowledgement of the latest policy",
                              self.check(safety=True)[0])

    def test_successor_owner_with_ack_can_await_archive(self):
        self.lifecycle.update({"Predecessor observed state": "active",
                               "Archive verification": "pending"})
        for status in ("active", "ready-for-review", "complete", "blocked", "transferred"):
            with self.subTest(status=status):
                self.identity["Status"] = status
                self.assertEqual(self.check(safety=True)[0], [])

    def test_archive_observation_requires_ack_even_if_owner_is_inconsistent(self):
        self.identity.update({"Task or thread": "task-old", "Status": "blocked"})
        self.lifecycle["Successor policy acknowledgement"] = "pending"
        self.assertIn("transferred ownership requires acknowledgement of the latest policy",
                      self.check(safety=True)[0])

    def test_transfer_claim_requires_ack_even_if_owner_is_inconsistent(self):
        self.identity.update({"Task or thread": "task-old", "Status": "transferred"})
        self.lifecycle.update({"Predecessor observed state": "active",
                               "Archive verification": "pending",
                               "Successor policy acknowledgement": "pending"})
        self.assertIn("transferred ownership requires acknowledgement of the latest policy",
                      self.check(safety=True)[0])

    def test_placeholder_ack_never_satisfies_transferred_owner(self):
        self.lifecycle.update({"Predecessor observed state": "active",
                               "Archive verification": "pending"})
        for value in ("pending", "unknown", "unverified", "", "none", "not-applicable"):
            with self.subTest(value=value):
                self.lifecycle["Successor policy acknowledgement"] = value
                self.assertIn("transferred ownership requires acknowledgement of the latest policy",
                              self.check(safety=True)[0])

    def test_manual_stages_do_not_require_future_archive_result(self):
        self.identity.update({"Task or thread": "task-old", "Successor task": "pending",
                              "Status": "handoff-ready"})
        self.lifecycle.update({"Predecessor observed state": "active",
                               "Archive verification": "pending",
                               "Successor policy acknowledgement": "pending"})
        self.safety.update({"Create outcome": "not-started", "Archive executor": "pending-successor",
                            "Owner epoch": "0"})
        self.assertEqual(self.check(safety=True)[0], [])
        self.identity["Successor task"] = "task-new"
        self.safety.update({"Create outcome": "confirmed", "Archive executor": "task-new"})
        for status in ("handoff-ready", "blocked"):
            self.identity["Status"] = status
            self.assertEqual(self.check(safety=True)[0], [])
        self.lifecycle["Successor policy acknowledgement"] = "task-new ack for current boundary/policy"
        self.identity.update({"Task or thread": "task-new", "Status": "transferred"})
        self.safety["Owner epoch"] = "1"
        self.assertEqual(self.check(safety=True)[0], [])
        self.assertTrue(self.check(closed=True)[0])
        self.lifecycle.update({"Predecessor observed state": "archived",
                               "Archive verification": "native receipt task-old archived; task-new available"})
        self.assertEqual(self.check(closed=True)[0], [])

    def test_duplicate_current_sections_rejected(self):
        doc = self.document() + "\n## Current state\n\nCompeting current instructions.\n"
        self.assertTrue(self.check(document=doc)[0])

    def test_duplicate_policy_metadata_rejected(self):
        doc = self.document().replace("## Task lifecycle", "## Task lifecycle\n\n- Predecessor disposition: retain-by-explicit-request")
        self.assertTrue(self.check(document=doc)[0])

    def test_empty_field_cannot_consume_next_field(self):
        self.lifecycle["Policy source"] = ""
        self.assertTrue(self.check()[0])

    def test_legacy_read_allowed_but_lifecycle_action_blocked(self):
        doc = self.document(include_lifecycle=False)
        errors, warnings = self.check(strict=False, document=doc)
        self.assertEqual(errors, [])
        self.assertTrue(warnings)
        self.assertTrue(self.check(document=doc)[0])

    def test_new_task_without_rollover(self):
        self.safety = {}
        self.identity.update({"Predecessor task": "none", "Successor task": "none", "Rollover generation": "0"})
        for key in self.lifecycle:
            if key != "Result destination":
                self.lifecycle[key] = "not-applicable"
        self.assertEqual(self.check()[0], [])
        self.assertTrue(self.check(closed=True)[0])

    def test_unknown_state_cannot_close(self):
        self.lifecycle["Predecessor observed state"] = "unknown"
        self.lifecycle["Archive verification"] = "pending"
        self.assertEqual(self.check()[0], [])
        self.assertTrue(self.check(closed=True)[0])

    def test_lifecycle_cannot_hide_an_existing_rollover(self):
        self.lifecycle["Predecessor disposition"] = "not-applicable"
        self.assertTrue(self.check()[0])

    def test_cli_close_flag_returns_real_exit_status(self):
        with tempfile.TemporaryDirectory(prefix="handoff-cli-") as directory:
            path = Path(directory) / "handoff.md"
            script = Path(__file__).with_name("validate_handoff.py")
            path.write_text(self.document(), encoding="utf-8")
            command = [sys.executable, "-S", "-B", str(script), str(path), "--require-closed-rollover"]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.lifecycle["Successor policy acknowledgement"] = "pending"
            path.write_text(self.document(), encoding="utf-8")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)

    def test_existing_placeholder_guard_preserved(self):
        self.assertTrue(self.check(document=self.document() + "\n{{UNFILLED_ACTION}}\n")[0])

    def test_existing_secret_guard_preserved(self):
        self.assertTrue(self.check(document=self.document() + "\n-----BEGIN PRIVATE KEY-----\n")[0])

    def test_invalid_observed_state_rejected(self):
        self.lifecycle["Predecessor observed state"] = "archive-requested"
        self.assertTrue(self.check()[0])

    def test_next_actions_without_user_action_warns_only(self):
        doc = self.document().replace("- User action now: none\n", "")
        errors, warnings = self.check(document=doc)
        self.assertEqual(errors, [])
        self.assertTrue(any("User action now" in warning for warning in warnings))

    def test_oversized_document_must_be_slimmed(self):
        doc = self.document() + "\n" + ("history line " * 10 + "\n") * 500
        self.assertGreater(len(doc.encode("utf-8")), 60 * 1024)
        self.assertTrue(any("slimming threshold" in error for error in self.check(document=doc)[0]))

    def test_long_current_state_must_be_slimmed_but_limit_itself_passes(self):
        original = "## Current state\n\nVerified fixture state; no external actions."
        for count, blocked in ((81, True), (80, False)):
            with self.subTest(count=count):
                body = "\n".join(f"- fact {n}" for n in range(count))
                doc = self.document().replace(original, "## Current state\n\n" + body)
                errors = self.check(document=doc)[0]
                self.assertEqual(any("slimming threshold" in error for error in errors), blocked)

    def test_next_actions_accept_chinese_user_action_label(self):
        doc = self.document().replace("- User action now: none", "- 用户操作：无需")
        self.assertFalse(any("User action now" in warning for warning in self.check(document=doc)[1]))


    def test_legacy_safety_readable_but_not_actionable(self):
        doc = self.document(include_safety=False)
        errors, warnings = self.check(document=doc)
        self.assertEqual(errors, [])
        self.assertTrue(warnings)
        self.assertTrue(self.check(safety=True, document=doc)[0])
        self.assertTrue(self.check(closed=True, document=doc)[0])

    def test_unpreserved_dirty_state_blocks_new_worktree(self):
        for disposition in ("blocked", "unverified"):
            with self.subTest(disposition=disposition):
                self.safety["Working tree disposition"] = disposition
                self.assertTrue(self.check(safety=True)[0])

    def test_hash_without_target_preservation_is_not_ready(self):
        self.safety["Working tree disposition"] = "committed:" + "a" * 40
        self.safety["Preservation evidence"] = "pending"
        self.assertTrue(self.check(safety=True)[0])

    def test_preservation_modes_with_target_evidence(self):
        for disposition in ("clean", "committed:" + "a" * 40, "patch:private-artifacts/revision-1"):
            with self.subTest(disposition=disposition):
                self.safety["Working tree disposition"] = disposition
                self.assertEqual(self.check(safety=True)[0], [])
        self.safety.update({"Working tree disposition": "shared-worktree-verified", "Successor workspace": "shared"})
        self.assertEqual(self.check(safety=True)[0], [])

    def test_claimed_shared_state_in_fresh_worktree_rejected(self):
        self.safety["Working tree disposition"] = "shared-worktree-verified"
        self.assertTrue(self.check(safety=True)[0])

    def test_unknown_quiescence_never_allows_transfer(self):
        self.safety["Quiescence evidence"] = "unknown"
        self.assertTrue(self.check(safety=True)[0])

    def test_owner_fields_cannot_replace_write_fencing(self):
        self.safety["Write isolation"] = "unverified"
        self.assertTrue(self.check(safety=True)[0])

    def test_listing_uncontrolled_paths_does_not_mitigate_them(self):
        for coverage in ("present", "unknown"):
            with self.subTest(coverage=coverage):
                self.safety["Uncovered write paths"] = coverage
                self.assertTrue(self.check(safety=True)[0])
        self.safety["Uncovered write paths"] = "excluded"
        self.assertEqual(self.check(safety=True)[0], [])
        self.safety["Coverage evidence"] = "pending"
        self.assertTrue(self.check(safety=True)[0])

    def test_automatic_mode_needs_separate_controller_evidence(self):
        self.safety["Execution mode"] = "automatic"
        self.assertTrue(self.check(safety=True)[0])
        self.safety["Controller evidence"] = "validated independent host adapter receipt m0-1"
        self.assertEqual(self.check(safety=True)[0], [])

    def test_reminder_mode_cannot_claim_a_rollover(self):
        self.safety["Execution mode"] = "reminder-only"
        self.assertTrue(self.check(safety=True)[0])

    def test_self_archive_closure_is_rejected(self):
        self.safety["Archive executor"] = "task-old"
        self.assertTrue(self.check(safety=True)[0])

    def test_safe_pending_creation_and_unknown_outcome(self):
        self.identity.update({"Task or thread": "task-old", "Successor task": "pending", "Status": "handoff-ready"})
        self.lifecycle.update({"Predecessor observed state": "active", "Archive verification": "pending",
                               "Successor policy acknowledgement": "pending"})
        self.safety.update({"Create outcome": "not-started", "Archive executor": "pending-successor", "Owner epoch": "0"})
        self.assertEqual(self.check(safety=True)[0], [])
        self.safety["Create outcome"] = "pending"
        self.assertEqual(self.check(safety=True)[0], [])
        self.safety["Create outcome"] = "unknown"
        self.assertTrue(self.check(safety=True)[0])
        self.identity["Status"] = "blocked"
        self.assertEqual(self.check()[0], [])
        self.assertTrue(self.check(safety=True)[0])

    def test_confirmation_requires_real_successor(self):
        self.identity.update({"Task or thread": "task-old", "Successor task": "pending", "Status": "blocked"})
        self.lifecycle.update({"Predecessor observed state": "active", "Archive verification": "pending",
                               "Successor policy acknowledgement": "pending"})
        self.assertTrue(self.check()[0])

    def test_unresolved_executor_cannot_close(self):
        self.safety["Archive executor"] = "pending-successor"
        self.assertTrue(self.check(closed=True)[0])

    def test_missing_scope_overlap_or_archive_impact_blocks(self):
        for field in ("Scope boundary", "Resource overlap check", "Archive isolation evidence"):
            with self.subTest(field=field):
                previous = self.safety[field]
                self.safety[field] = "unknown"
                self.assertTrue(self.check(safety=True)[0])
                self.safety[field] = previous

    def test_duplicate_safety_field_rejected(self):
        doc = self.document().replace("## Transfer safety", "## Transfer safety\n\n- Owner epoch: 99")
        self.assertTrue(self.check(document=doc)[0])

    def test_scope_and_boundary_ids_cannot_be_empty_or_title_annotations(self):
        for field in ("Work scope ID", "Boundary ID"):
            for value in ("", "unknown", "scope-1 (old task)"):
                with self.subTest(field=field, value=value):
                    previous = self.safety[field]
                    self.safety[field] = value
                    self.assertTrue(self.check()[0])
                    self.safety[field] = previous

    def test_transferred_epoch_cannot_still_be_zero(self):
        self.safety["Owner epoch"] = "0"
        self.assertTrue(self.check()[0])

    def test_invalid_artifact_references_rejected(self):
        for value in ("committed:abc", "patch:", "patch:pending", "copied"):
            with self.subTest(value=value):
                self.safety["Working tree disposition"] = value
                self.assertTrue(self.check()[0])

    def test_transfer_cli_flag_checks_readiness(self):
        with tempfile.TemporaryDirectory(prefix="handoff-readiness-") as directory:
            path = Path(directory) / "handoff.md"
            script = Path(__file__).with_name("validate_handoff.py")
            command = [sys.executable, "-S", "-B", str(script), str(path), "--require-transfer-safety"]
            path.write_text(self.document(), encoding="utf-8")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.safety["Quiescence evidence"] = "pending"
            path.write_text(self.document(), encoding="utf-8")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)


class HandoffSectionTests(unittest.TestCase):
    """Direction card and Work in progress: advisory for checkpoints, required to seal."""

    def check(self, document, require_handoff=False, card_limit=None):
        from handoff_config import DEFAULTS, validate_settings
        settings = validate_settings(dict(DEFAULTS, **({"direction_card_max_chars": card_limit} if card_limit else {})))
        with tempfile.TemporaryDirectory(prefix="handoff-sections-") as directory:
            path = Path(directory) / "handoff.md"
            path.write_text(document(path), encoding="utf-8")
            return validate(path, 600, settings=settings, require_handoff=require_handoff)

    def test_complete_document_passes_both_modes(self):
        from test_support import document
        for require in (False, True):
            with self.subTest(require=require):
                self.assertEqual(self.check(lambda path: document(path), require), ([], []))

    def test_missing_sections_warn_on_checkpoints_and_block_sealing(self):
        from test_support import document
        legacy = lambda path: document(path, card=None, wip=None)  # noqa: E731
        errors, warnings = self.check(legacy)
        self.assertEqual(errors, [])
        self.assertEqual(sum("## Direction card" in item or "## Work in progress" in item for item in warnings), 2)
        errors = self.check(legacy, require_handoff=True)[0]
        self.assertTrue(any("## Direction card" in error for error in errors))
        self.assertTrue(any("## Work in progress" in error for error in errors))

    def test_sealing_requires_each_wip_field_but_accepts_none(self):
        from test_support import document
        for label in ("Unfinished work", "Background jobs", "Workspace changes"):
            with self.subTest(label=label):
                wip = "\n".join("- %s: none" % item for item in ("Unfinished work", "Background jobs", "Workspace changes")
                                if item != label)
                errors = self.check(lambda path: document(path, wip=wip), require_handoff=True)[0]
                self.assertEqual(errors, ["Work in progress is missing '%s' (write 'none' when nothing applies)" % label])

    def test_oversized_card_warns_then_blocks_sealing(self):
        from test_support import document
        long_card = lambda path: document(path, card="- Goal: " + "x" * 300)  # noqa: E731
        errors, warnings = self.check(long_card, card_limit=200)
        self.assertEqual(errors, [])
        self.assertTrue(any("Direction card has" in warning for warning in warnings))
        self.assertTrue(any("Direction card has" in error for error in self.check(long_card, True, 200)[0]))

    def test_cli_require_handoff_exit_codes(self):
        from test_support import document
        script = Path(__file__).with_name("validate_handoff.py")
        with tempfile.TemporaryDirectory(prefix="handoff-sections-cli-") as directory:
            path = Path(directory) / "handoff.md"
            for wip, code in ((None, 1), ("- Unfinished work: none\n- Background jobs: none\n- Workspace changes: none", 0)):
                with self.subTest(wip=wip):
                    path.write_text(document(path, wip=wip), encoding="utf-8")
                    result = subprocess.run([sys.executable, "-S", "-B", str(script), str(path), "--require-handoff"],
                                            capture_output=True)
                    self.assertEqual(result.returncode, code, result.stderr)


class TemplateTests(unittest.TestCase):
    def test_template_filled_in_can_be_sealed(self):
        template = Path(__file__).resolve().parents[1] / "assets" / "handoff-template.md"
        text = re.sub(r"\{\{[^{}]+\}\}", "filled", template.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="handoff-template-") as directory:
            path = Path(directory) / "handoff.md"
            path.write_text(text, encoding="utf-8")
            errors, warnings = validate(path, 600, require_handoff=True)
        # Filled placeholders are not valid lifecycle values; only the handoff sections matter here.
        self.assertFalse([item for item in errors + warnings if "Direction card" in item or "Work in progress" in item])

    def test_template_next_actions_record_user_action(self):
        template = Path(__file__).resolve().parents[1] / "assets" / "handoff-template.md"
        text = re.sub(r"\{\{[^{}]+\}\}", "filled", template.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="handoff-template-") as directory:
            path = Path(directory) / "handoff.md"
            path.write_text(text, encoding="utf-8")
            warnings = validate(path, 600)[1]
        self.assertFalse([warning for warning in warnings if "User action now" in warning])


if __name__ == "__main__":
    unittest.main()
