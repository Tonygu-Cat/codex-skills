#!/usr/bin/env python3
"""Check handoff structure and declared lifecycle consistency, not live state or authority."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from handoff_config import ConfigError, load_settings, slimming_targets


REQUIRED_SECTIONS = (
    "Identity",
    "Objective and completion criteria",
    "Current state",
    "Scope and constraints",
    "Decisions and rationale",
    "Changed artifacts",
    "Verification evidence",
    "Blockers, risks, and permissions",
    "Next exact actions",
    "Resume protocol",
    "Revision log",
)
# Advisory on routine checkpoints; required before a handoff is sealed.
HANDOFF_SECTIONS = ("Direction card", "Work in progress")
WIP_FIELDS = ("Unfinished work", "Background jobs", "Workspace changes")

ALLOWED_STATUSES = {
    "active",
    "blocked",
    "ready-for-review",
    "handoff-ready",
    "transferred",
    "complete",
}
PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}|\[(?:TODO|TBD|FILL(?: ME)?)\]", re.IGNORECASE)
USER_ACTION = re.compile(r"(?im)^- (?:User action now|用户操作)[ \t]*[:：]")
SECRET_PATTERNS = (
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


def section_bodies(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^## (.+?)\s*$", text))
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        bodies[match.group(1).strip()] = text[match.end() : end].strip()
    return bodies


def metadata_value(identity: str, label: str) -> str | None:
    match = re.search(rf"(?m)^- {re.escape(label)}:[ \t]*(.*?)[ \t]*$", identity)
    if not match:
        return None
    return match.group(1).strip().strip("`")


def concrete(value: str | None) -> bool:
    return value is not None and value.lower() not in {"", "none", "pending", "unknown", "not-applicable", "unverified", "blocked", "pending-successor"}


def ownership_transferred(current: str | None, successor: str | None,
                          status: str | None, observed: str | None) -> bool:
    """Use the same transfer declaration in lifecycle and safety checks."""
    return status == "transferred" or observed == "archived" or (
        concrete(successor) and current == successor
    )


def check_lifecycle(bodies: dict[str, str], require_closed: bool) -> list[str]:
    errors: list[str] = []
    identity = bodies.get("Identity", "")
    lifecycle = bodies.get("Task lifecycle", "")
    values = {label: metadata_value(lifecycle, label) for label in (
        "Policy source", "Predecessor disposition", "Predecessor observed state",
        "Archive verification", "Successor policy acknowledgement", "Result destination",
    )}
    for label, value in values.items():
        if not value:
            errors.append(f"Task lifecycle is missing '{label}'")
    disposition = values["Predecessor disposition"]
    observed = values["Predecessor observed state"]
    if disposition not in {"not-applicable", "archive-after-takeover", "retain-by-explicit-request"}:
        errors.append("invalid Predecessor disposition")
    if observed not in {"not-applicable", "unknown", "active", "archived"}:
        errors.append("invalid Predecessor observed state")
    if values["Result destination"] != "current-task-user":
        errors.append("Result destination must be current-task-user, not the predecessor")

    predecessor = metadata_value(identity, "Predecessor task")
    successor = metadata_value(identity, "Successor task")
    current = metadata_value(identity, "Task or thread")
    generation = metadata_value(identity, "Rollover generation")
    status = metadata_value(identity, "Status")
    if not concrete(current):
        errors.append("Task lifecycle requires a concrete current Task or thread")
    if disposition == "not-applicable":
        if concrete(predecessor) or concrete(successor) or generation != "0":
            errors.append("not-applicable lifecycle requires no predecessor/successor and generation 0")
        for label in ("Policy source", "Predecessor observed state", "Archive verification", "Successor policy acknowledgement"):
            if values[label] != "not-applicable":
                errors.append(f"no rollover requires {label} to be not-applicable")
        if require_closed:
            errors.append("cannot close a rollover marked not-applicable")
        return errors

    if not concrete(predecessor) or not generation or not generation.isdigit() or int(generation) < 1:
        errors.append("rollover lifecycle requires a concrete predecessor and generation >= 1")
    if not concrete(values["Policy source"]):
        errors.append("rollover requires a concrete latest Policy source")
    if observed == "not-applicable":
        errors.append("rollover requires an observed predecessor state or unknown")
    if values["Archive verification"] == "not-applicable" or values["Successor policy acknowledgement"] == "not-applicable":
        errors.append("rollover evidence must be pending or a concrete reference, not not-applicable")
    if concrete(predecessor) and predecessor == successor:
        errors.append("predecessor and successor must be different task IDs")
    if status == "handoff-ready" and current != predecessor:
        errors.append("handoff-ready current owner must be the predecessor")
    if status in {"transferred", "active", "complete", "ready-for-review"} and concrete(successor) and current != successor:
        errors.append("after transfer the current owner must be the successor")
    if ownership_transferred(current, successor, status, observed) and not concrete(values["Successor policy acknowledgement"]):
        errors.append("transferred ownership requires acknowledgement of the latest policy")
    if observed == "archived":
        if not concrete(successor) or current != successor:
            errors.append("archived predecessor requires a concrete successor as current owner")
        if not concrete(values["Archive verification"]):
            errors.append("archived predecessor requires an archive evidence reference")
        if disposition == "retain-by-explicit-request":
            errors.append("retention policy conflicts with archived state; reconcile latest authority, never auto-restore")
    if require_closed:
        if not concrete(successor) or current != successor:
            errors.append("closed rollover requires the successor as current owner")
        if status == "handoff-ready":
            errors.append("handoff-ready is not a closed rollover")
        expected = "archived" if disposition == "archive-after-takeover" else "active"
        if observed != expected:
            errors.append(f"closed rollover requires predecessor state {expected}")
        for label in ("Archive verification", "Successor policy acknowledgement"):
            if not concrete(values[label]):
                errors.append(f"closed rollover requires a concrete {label}")
    return errors


SAFETY_FIELDS = (
    "Work scope ID", "Scope boundary", "Resource overlap check", "Boundary ID",
    "Owner epoch", "Execution mode", "Create outcome", "Successor workspace",
    "Working tree disposition", "Preservation evidence", "Quiescence evidence",
    "Write isolation", "Uncovered write paths", "Coverage evidence",
    "Archive executor", "Archive isolation evidence", "Controller evidence",
)


def check_transfer_safety(bodies: dict[str, str], require_ready: bool) -> list[str]:
    """Check declared prerequisites, never treat references as verified host evidence."""
    errors: list[str] = []
    identity = bodies.get("Identity", "")
    safety = bodies.get("Transfer safety", "")
    values = {label: metadata_value(safety, label) for label in SAFETY_FIELDS}
    for label, value in values.items():
        if not value:
            errors.append(f"Transfer safety is missing '{label}'")
    for label in ("Work scope ID", "Boundary ID"):
        value = values[label]
        if not concrete(value) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value or ""):
            errors.append(f"{label} must be a concrete opaque ID without title annotations")

    epoch = values["Owner epoch"]
    if not epoch or not epoch.isdigit():
        errors.append("Owner epoch must be a non-negative integer")
    enums = {
        "Execution mode": {"manual", "automatic"},
        "Create outcome": {"not-started", "pending", "confirmed", "unknown"},
        "Successor workspace": {"new", "shared", "unknown"},
        "Write isolation": {"verified", "unverified"},
        "Uncovered write paths": {"none", "excluded", "present", "unknown"},
    }
    for label, allowed in enums.items():
        if values[label] not in allowed:
            errors.append(f"invalid {label}")

    disposition = values["Working tree disposition"] or ""
    valid_disposition = disposition in {"clean", "shared-worktree-verified", "blocked", "unverified"}
    if disposition.startswith("committed:"):
        valid_disposition = bool(re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", disposition[10:]))
    if disposition.startswith("patch:"):
        valid_disposition = concrete(disposition[6:].strip())
    if not valid_disposition:
        errors.append("invalid Working tree disposition")
    if disposition == "shared-worktree-verified" and values["Successor workspace"] != "shared":
        errors.append("shared-worktree preservation requires a verified shared successor workspace")

    predecessor = metadata_value(identity, "Predecessor task")
    successor = metadata_value(identity, "Successor task")
    current = metadata_value(identity, "Task or thread")
    status = metadata_value(identity, "Status")
    observed = metadata_value(bodies.get("Task lifecycle", ""), "Predecessor observed state")
    outcome = values["Create outcome"]
    if outcome == "confirmed" and not concrete(successor):
        errors.append("confirmed creation requires the real successor task ID")
    if outcome in {"not-started", "pending", "unknown"} and concrete(successor):
        errors.append("a real successor ID requires confirmed creation; preserve setup IDs as evidence instead")
    transferred = ownership_transferred(current, successor, status, observed)
    require_ready = require_ready or status == "handoff-ready"
    if transferred:
        require_ready = True
        if outcome != "confirmed":
            errors.append("transferred ownership requires confirmed creation")
        if not epoch or not epoch.isdigit() or int(epoch) < 1:
            errors.append("transferred ownership requires Owner epoch >= 1")
    executor = values["Archive executor"]
    if concrete(predecessor) and executor == predecessor:
        errors.append("predecessor cannot be its own archive-and-closure executor")
    if require_ready:
        for label in (
            "Scope boundary", "Resource overlap check", "Preservation evidence",
            "Quiescence evidence", "Coverage evidence", "Archive isolation evidence",
        ):
            if not concrete(values[label]):
                errors.append(f"safe transfer requires a concrete {label}")
        if disposition in {"blocked", "unverified"}:
            errors.append("unpreserved working state blocks transfer and archival")
        if values["Successor workspace"] == "unknown":
            errors.append("safe transfer requires a resolved successor workspace")
        if values["Write isolation"] != "verified":
            errors.append("safe transfer requires verified write isolation")
        if values["Uncovered write paths"] not in {"none", "excluded"}:
            errors.append("reachable uncontrolled or unknown write paths block transfer")
        if outcome == "unknown":
            errors.append("CREATE_OUTCOME_UNKNOWN requires reconciliation, not another create")
        if executor == "pending-successor":
            if concrete(successor) or transferred:
                errors.append("resolve the surviving archive executor before ownership transfer")
        elif not concrete(executor):
            errors.append("safe transfer requires a surviving archive executor")
        if values["Execution mode"] == "automatic" and not concrete(values["Controller evidence"]):
            errors.append("automatic transfer requires independent controller evidence")
    return errors


def check_handoff_sections(bodies: dict[str, str], settings, require: bool) -> list[str]:
    """Direction card and wrap-up record; a sealed handoff needs them, a checkpoint only should."""
    issues: list[str] = []
    for section in HANDOFF_SECTIONS:
        if not re.sub(r"<!--.*?-->", "", bodies.get(section, ""), flags=re.DOTALL).strip():
            issues.append(f"missing or empty section: ## {section}")
    card = re.sub(r"<!--.*?-->", "", bodies.get("Direction card", ""), flags=re.DOTALL).strip()
    limit = settings.get("direction_card_max_chars", 1500)
    if len(card) > limit:
        issues.append(f"Direction card has {len(card)} characters; keep it within {limit} "
                      "(stable goal, done-when, phase, scope, non-goals and fixed user decisions only)")
    if require:
        wip = bodies.get("Work in progress", "")
        for label in WIP_FIELDS:
            if not metadata_value(wip, label):
                issues.append(f"Work in progress is missing '{label}' (write 'none' when nothing applies)")
    return issues


def validate(path: Path, max_lines: int, require_lifecycle: bool = False,
             require_closed_rollover: bool = False,
             require_transfer_safety: bool = False, settings=None,
             require_handoff: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        settings = load_settings() if settings is None else settings
    except ConfigError as exc:
        return [str(exc)], warnings

    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return [f"cannot read {path}: {exc}"], warnings

    return validate_text(text, max_lines, require_lifecycle, require_closed_rollover,
                         require_transfer_safety, settings, byte_size=len(raw),
                         require_handoff=require_handoff)


def validate_text(text, max_lines=600, require_lifecycle=False,
                  require_closed_rollover=False, require_transfer_safety=False, settings=None,
                  byte_size=None, require_handoff=False):
    errors, warnings = [], []
    try:
        settings = load_settings() if settings is None else settings
    except ConfigError as exc:
        return [str(exc)], warnings
    if not re.search(r"(?m)^# Project Handoff\s*$", text):
        errors.append("missing '# Project Handoff' title")

    bodies = section_bodies(text)
    for heading, count in Counter(re.findall(r"(?m)^## (.+?)[ \t]*$", text)).items():
        if count > 1:
            errors.append(f"duplicate section: ## {heading}")
    for section in ("Identity", "Task lifecycle", "Transfer safety"):
        for label, count in Counter(re.findall(r"(?m)^- ([^:\n]+):", bodies.get(section, ""))).items():
            if count > 1:
                errors.append(f"duplicate metadata in {section}: {label}")
    for section in REQUIRED_SECTIONS:
        body = bodies.get(section)
        if body is None:
            errors.append(f"missing section: ## {section}")
        elif not body or not re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip():
            errors.append(f"empty section: ## {section}")
    handoff_issues = check_handoff_sections(bodies, settings, require_handoff)
    (errors if require_handoff else warnings).extend(handoff_issues)

    next_actions = bodies.get("Next exact actions")
    if next_actions and not USER_ACTION.search(next_actions):
        warnings.append(
            "Next exact actions lacks 'User action now'; record the user's pending action or 'none' "
            "so a resuming agent can tell the user what to do"
        )

    placeholders = sorted(set(PLACEHOLDER.findall(text)))
    if placeholders:
        errors.append("unfilled placeholders: " + ", ".join(placeholders[:8]))

    identity = bodies.get("Identity", "")
    revision = metadata_value(identity, "Handoff revision")
    if revision is None:
        errors.append("Identity is missing 'Handoff revision'")
    elif not revision.isdigit() or int(revision) < 1:
        errors.append("Handoff revision must be a positive integer")

    updated_at = metadata_value(identity, "Updated at")
    if updated_at is None:
        errors.append("Identity is missing 'Updated at'")
    else:
        try:
            datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("Updated at must be an ISO 8601 timestamp")

    status = metadata_value(identity, "Status")
    if status is None:
        errors.append("Identity is missing 'Status'")
    elif status not in ALLOWED_STATUSES:
        errors.append("Status must be one of: " + ", ".join(sorted(ALLOWED_STATUSES)))

    predecessor = metadata_value(identity, "Predecessor task")
    successor = metadata_value(identity, "Successor task")
    generation = metadata_value(identity, "Rollover generation")
    if generation is not None and (not generation.isdigit() or int(generation) < 0):
        errors.append("Rollover generation must be a non-negative integer")

    if status in {"handoff-ready", "transferred"}:
        if predecessor is None or predecessor.lower() in {"", "none", "pending"}:
            errors.append(f"Status '{status}' requires a concrete Predecessor task")
        if generation is None or not generation.isdigit() or int(generation) < 1:
            errors.append(f"Status '{status}' requires Rollover generation >= 1")

    if status == "handoff-ready" and successor != "pending" and not concrete(successor):
        errors.append("Status 'handoff-ready' requires pending or an already-created Successor task ID")

    if status == "transferred" and (
        successor is None or successor.lower() in {"", "none", "pending"}
    ):
        errors.append("Status 'transferred' requires a concrete Successor task")

    if "Task lifecycle" in bodies:
        errors.extend(check_lifecycle(bodies, require_closed_rollover))
    elif require_lifecycle or require_closed_rollover or require_transfer_safety:
        errors.append("missing section: ## Task lifecycle (required for lifecycle operations)")
    elif concrete(predecessor) or status in {"handoff-ready", "transferred"}:
        warnings.append("legacy handoff lacks Task lifecycle; add it before lifecycle operations")

    if "Transfer safety" in bodies:
        errors.extend(check_transfer_safety(bodies, require_transfer_safety or require_closed_rollover))
    elif require_transfer_safety or require_closed_rollover:
        errors.append("missing section: ## Transfer safety (required before rollover)")
    elif concrete(predecessor) or status in {"handoff-ready", "transferred"}:
        warnings.append("legacy handoff lacks Transfer safety; reconcile before rollover")

    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"possible secret detected: {label}")

    size = len(text.encode("utf-8")) if byte_size is None else byte_size
    current_lines = len([line for line in bodies.get("Current state", "").splitlines() if line.strip()])
    if size > settings["max_document_bytes"] or current_lines > settings["max_current_state_lines"]:
        targets = slimming_targets(settings)
        errors.append(
            f"handoff exceeds the slimming threshold ({size} bytes, Current state {current_lines} lines; "
            f"limits {settings['max_document_bytes']} bytes / {settings['max_current_state_lines']} lines): slim it now - keep "
            f"Current state within {targets['current_state_lines']} lines and document within {targets['document_bytes']} bytes, move superseded history to HISTORY_THROUGH_R<revision>.md "
            "beside this document, and keep decisions and evidence as references"
        )

    line_count = len(text.splitlines())
    if line_count > max_lines:
        warnings.append(
            f"document has {line_count} lines; consider replacing stale narrative while preserving decisions, evidence, and Git history"
        )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, help="Path to the handoff Markdown file")
    parser.add_argument("--config", type=Path, help="absolute shared settings JSON")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=600,
        help="Warn when the document exceeds this many lines (default: 600)",
    )
    parser.add_argument("--require-lifecycle", action="store_true",
                        help="Require lifecycle metadata before task lifecycle operations")
    parser.add_argument("--require-closed-rollover", action="store_true",
                        help="Also require declared final state, archive evidence, and policy acknowledgement")
    parser.add_argument("--require-transfer-safety", action="store_true",
                        help="Require safe transfer declarations; does not verify actual host evidence")
    parser.add_argument("--require-handoff", action="store_true",
                        help="Require the Direction card and Work in progress that sealing a handoff needs")
    args = parser.parse_args()

    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors, warnings = validate(args.handoff, args.max_lines, args.require_lifecycle,
                                args.require_closed_rollover, args.require_transfer_safety, settings,
                                args.require_handoff)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        print(f"FAIL: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(f"PASS (document checks only; verify authority and live state separately): {args.handoff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
