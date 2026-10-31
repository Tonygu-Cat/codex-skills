#!/usr/bin/env python3
"""Publish an agent-prepared concise draft only after preserving the full original.

Not a semantic summarizer. The agent reads and condenses the document; this helper
enforces identity, protected requirements, limits and exact-byte history retention.
Default is dry-run. Only the authorized sole document writer may apply a draft.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from handoff_config import load_settings, slimming_targets
from handoff_entry import MAX_CANONICAL_BYTES, read_bytes, same_path
from validate_handoff import metadata_value, section_bodies, validate_text

PROTECTED = ("Objective and completion criteria", "Scope and constraints",
             "Blockers, risks, and permissions", "Next exact actions")
IDENTITY = ("Project", "Task or thread", "Canonical document", "Workspace",
            "Source repository", "Documentation repository", "Predecessor task",
            "Successor task", "Rollover generation", "Status")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_separate_history(history, canonical, candidate):
    if history.is_symlink():
        raise ValueError("history must not be a linked document")
    for source in (canonical, candidate):
        if same_path(str(history), str(source)) or (
                history.exists() and os.path.samefile(history, source)):
            raise ValueError("history must not overlap the canonical or draft")


def prepare(canonical, candidate, task, expected, settings):
    if not canonical.is_absolute() or not candidate.is_absolute():
        raise ValueError("paths must be absolute")
    if canonical.is_symlink() or candidate.is_symlink():
        raise ValueError("do not replace a linked document")
    if same_path(str(canonical), str(candidate)) or canonical.resolve().parent != candidate.resolve().parent:
        raise ValueError("draft must be a separate file beside the canonical")
    original = read_bytes(canonical, MAX_CANONICAL_BYTES)
    draft = read_bytes(candidate, MAX_CANONICAL_BYTES)
    if digest(original) != expected:
        raise ValueError("canonical changed; stop and reconcile")
    old, new = original.decode("utf-8-sig"), draft.decode("utf-8-sig")
    old_errors, _ = validate_text(old, settings=settings, byte_size=len(original))
    if any("slimming threshold" not in error for error in old_errors):
        raise ValueError("original has structural or secret errors")
    errors, _ = validate_text(new, settings=settings, byte_size=len(draft))
    if errors:
        raise ValueError("draft invalid: " + "; ".join(errors))
    before, after = section_bodies(old), section_bodies(new)
    old_id, new_id = before["Identity"], after["Identity"]
    if metadata_value(old_id, "Task or thread") != task:
        raise ValueError("original task identity mismatch")
    if not same_path(metadata_value(old_id, "Canonical document"), str(canonical)):
        raise ValueError("canonical identity path mismatch")
    for field in IDENTITY:
        if metadata_value(old_id, field) != metadata_value(new_id, field):
            raise ValueError("draft changes identity: " + field)
    revision = int(metadata_value(old_id, "Handoff revision"))
    if int(metadata_value(new_id, "Handoff revision")) != revision + 1:
        raise ValueError("draft must advance revision exactly once")
    for section in PROTECTED:
        if before[section] != after[section]:
            raise ValueError("draft changes protected requirements: " + section)
    # Slimming never rewrites direction: an existing card survives byte for byte.
    if "Direction card" in before and before["Direction card"] != after.get("Direction card"):
        raise ValueError("draft changes protected requirements: Direction card")
    targets = slimming_targets(settings)
    lines = len([line for line in after["Current state"].splitlines() if line.strip()])
    if len(draft) > targets["document_bytes"] or lines > targets["current_state_lines"]:
        raise ValueError("draft exceeds effective slimming targets")
    history = canonical.with_name("HISTORY_THROUGH_R%d.md" % revision)
    require_separate_history(history, canonical, candidate)
    if history.name not in new or expected not in new:
        raise ValueError("draft must index history filename and original SHA256")
    if history.exists() and read_bytes(history, MAX_CANONICAL_BYTES) != original:
        raise ValueError("history name already belongs to other content")
    return original, draft, history


def execute(canonical, candidate, task, expected, settings, apply=False):
    original, draft, history = prepare(canonical, candidate, task, expected, settings)
    result = {"mode": "dry-run", "canonical": str(canonical), "history": str(history),
              "original_sha256": digest(original), "candidate_sha256": digest(draft),
              "original_bytes": len(original), "candidate_bytes": len(draft)}
    if not apply:
        return result
    lock = canonical.with_name(canonical.name + ".slim.lock")
    # Coordinates this helper, not arbitrary external writers or OS permissions.
    with lock.open("xb") as handle:
        handle.write(expected.encode("ascii"))
    temporary = None
    try:
        if read_bytes(canonical, MAX_CANONICAL_BYTES) != original:
            raise ValueError("canonical changed before preservation")
        require_separate_history(history, canonical, candidate)
        if history.exists():
            if read_bytes(history, MAX_CANONICAL_BYTES) != original:
                raise ValueError("history conflict")
        else:
            with history.open("xb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
        if read_bytes(history, MAX_CANONICAL_BYTES) != original:
            raise ValueError("history readback failed; canonical untouched")
        with tempfile.NamedTemporaryFile(dir=canonical.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(draft)
            handle.flush()
            os.fsync(handle.fileno())
        if read_bytes(canonical, MAX_CANONICAL_BYTES) != original:
            raise ValueError("canonical changed before publication; history retained")
        require_separate_history(history, canonical, candidate)
        os.replace(temporary, canonical)
        temporary = None
        if read_bytes(canonical, MAX_CANONICAL_BYTES) != draft:
            raise ValueError("publication result unknown; do not repeat")
        if read_bytes(history, MAX_CANONICAL_BYTES) != original:
            raise ValueError("history result unknown after publication; do not repeat")
        result["mode"] = "applied"
        return result
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()  # only this invocation's unpublished temporary file
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if not re.fullmatch("[0-9a-f]{64}", args.expected_sha256):
            raise ValueError("expected SHA256 must be lowercase hexadecimal")
        result = execute(args.canonical, args.candidate, args.task_id, args.expected_sha256,
                         load_settings(args.config), args.apply)
    except (OSError, ValueError, UnicodeError) as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
