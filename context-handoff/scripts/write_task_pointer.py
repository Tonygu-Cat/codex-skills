#!/usr/bin/env python3
"""Write or refresh this task's handoff locator, or seal it for a deliberate handoff.

  python write_task_pointer.py --canonical ABS_PATH [--seal] [--task-id ID] [--workspace ABS_DIR]

Default (routine): an unsealed locator with the exact task ID, workspace and
canonical document. It lets the post-compaction direction-card hook and a successor
find the handoff, and it never stops compaction.

--seal (deliberate handoff only): also binds the validated document's SHA256 and
revision, so the pre-compaction guard stops this task until the handoff is taken;
prints the handoff line for the user. Any later edit to the document releases it.

--task-id defaults to CODEX_THREAD_ID and --workspace to the current directory.
Writes only <workspace>/docs/handoffs/by-task/task-<sha256(id)>.md; never creates,
archives or messages tasks.
"""
import argparse
import datetime
import os
import sqlite3
import sys
import hashlib
import tempfile
from pathlib import Path
import handoff_entry
from handoff_config import load_settings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import precompact_guard as guard  # noqa: E402


def fail(message):
    print("ERROR: " + message, file=sys.stderr)
    return 2


def goal_status(task):
    """This task's Codex goal status ('none' without a goal), or None when unreadable."""
    if os.environ.get("CODEX_HOME"):
        homes = [os.environ["CODEX_HOME"]]
    else:
        homes = [str(Path(__file__).resolve().parents[3]), os.path.join(os.path.expanduser("~"), ".codex")]
    for home in homes:
        database = os.path.join(home, "goals_1.sqlite")
        if not os.path.isfile(database):
            continue
        try:
            connection = sqlite3.connect("file:" + Path(database).as_posix() + "?mode=ro", uri=True, timeout=2)
            try:
                row = connection.execute("SELECT status FROM thread_goals WHERE thread_id = ?", (task,)).fetchone()
            finally:
                connection.close()
        except sqlite3.Error:
            return None
        return row[0] if row else "none"
    return None


def require_separate_pointer(pointer, canonical, root):
    if not Path(pointer).resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("pointer directory resolves outside the workspace")
    if handoff_entry.same_path(pointer, canonical) or (
            os.path.exists(pointer) and os.path.samefile(pointer, canonical)):
        raise ValueError("pointer must not overlap the canonical document")


def main(argv=None):
    # Codex captures tool output as UTF-8. Windows redirected Python may default
    # to GBK, which corrupts a literal Unicode locator before the user can paste it.
    # Configure only these process-local streams, never the host environment.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--canonical", required=True, help="absolute path of the one canonical handoff")
    parser.add_argument("--seal", action="store_true",
                        help="deliberate handoff: seal the validated revision so compaction stops this task")
    parser.add_argument("--config", help="absolute shared settings JSON")
    parser.add_argument("--task-id", default=os.environ.get("CODEX_THREAD_ID"),
                        help="exact native task ID (default: CODEX_THREAD_ID)")
    parser.add_argument("--workspace", default=os.getcwd(), help="task workspace (default: current directory)")
    args = parser.parse_args(argv)

    if not guard.valid_id(args.task_id):
        return fail("missing or invalid task ID; pass --task-id or run inside the Codex task (CODEX_THREAD_ID)")
    if not os.path.isdir(args.workspace):
        return fail("workspace is not an existing directory")
    root = guard.normalized_root(os.path.abspath(args.workspace))
    if root is None:
        return fail("workspace must be a local absolute path without control characters or '..'")
    if not os.path.isabs(args.canonical) or not os.path.isfile(args.canonical):
        return fail("--canonical must be the absolute path of an existing handoff document")
    canonical = os.path.abspath(args.canonical).replace("\\", "/")
    if args.seal:
        # A sealed task is stopped at every compaction; an active goal would keep
        # auto-continuing into that stop (the 2026-09-27 loop of ~17,000 empty turns).
        status = goal_status(args.task_id)
        if status == "active":
            return fail("this task's goal is still active; pause it first so it cannot auto-continue into the sealed stop")
        if status is None:
            print("WARNING: cannot read this task's goal state; make sure no goal is active before handing off",
                  file=sys.stderr)
    try:
        if args.seal:
            info = handoff_entry.canonical_info(canonical, args.task_id, load_settings(args.config))
        else:
            info = handoff_entry.canonical_identity(canonical, args.task_id)
        if info["workspace"] is not None and not handoff_entry.same_path(info["workspace"], root):
            return fail("canonical workspace identity mismatch")
    except (OSError, ValueError, UnicodeError) as exc:
        return fail(str(exc))

    pointer = guard.task_pointer_path(root, args.task_id)
    try:
        require_separate_pointer(pointer, canonical, root)
    except (OSError, ValueError) as exc:
        return fail(str(exc))
    updated = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    fields = ("- Task or thread: `%s`\n- Workspace: `%s`\n- Canonical document: `%s`\n"
              % (args.task_id, root, canonical))
    if args.seal:
        fields += "- Canonical SHA256: `%s`\n- Handoff revision: `%s`\n" % (info["sha256"], info["revision"])
        note = ("Sealed for a deliberate handoff: compaction stops this task until the handoff is taken. "
                "Follow this pointer once and verify the canonical document's identity before any takeover.\n")
    else:
        note = ("Unsealed locator: used by the post-compaction direction card and by a successor. "
                "It never stops compaction. Follow it once and verify identity before any takeover.\n")
    content = "# Handoff pointer\n\n" + fields + "- Updated at: `%s`\n\n" % updated + note
    os.makedirs(os.path.dirname(pointer), exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=os.path.dirname(pointer), delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if args.seal and hashlib.sha256(handoff_entry.read_bytes(
                canonical, handoff_entry.MAX_CANONICAL_BYTES)).hexdigest() != info["sha256"]:
            return fail("canonical changed during pointer preparation; stop and reconcile")
        require_separate_pointer(pointer, canonical, root)
        os.replace(temporary, pointer)
        temporary = None
    except (OSError, ValueError) as exc:
        return fail(str(exc))
    finally:
        if temporary is not None:
            os.unlink(temporary)

    if args.seal:
        print("POINTER " + pointer)
        print(guard.paste_line(args.task_id, root))
    else:
        print("LOCATOR " + pointer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
