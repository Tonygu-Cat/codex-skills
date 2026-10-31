#!/usr/bin/env python3
"""Synchronous PreCompact decision helper; never installs a hook.

Run under Python -S -B with --all-sessions (user level) or --session-id
EXACT_NATIVE_ID (legacy) and one UTF-8 JSON event on stdin.

Only a task with a validated, version-sealed handoff pointer is stopped.
The pointer must bind the exact session/workspace to a readable, structurally
valid canonical document, matching owner, path, revision and SHA256.
Everything else returns {} including missing, invalid or stale pointers.
A guard that cannot identify a prepared task must not freeze sessions.

Reads bounded stdin, component settings, one derived pointer and its single
canonical document. No writes, network, model, task API or child process.
A returned veto is not evidence that a host honored it or that jobs stopped.
"""
import hashlib
import json
import os
import re
import sys
import unicodedata
import handoff_entry

MAX_INPUT_BYTES = 65536
MAX_LOCATION_CHARS = 512
MARKER = "CONTEXT_HANDOFF_PRECOMPACT_V1"
ALL_SESSIONS = "--all-sessions"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)


def veto(message):
    return {
        "continue": False,
        "stopReason": MARKER + ":handoff_required",
        "systemMessage": message,
    }


def normalized_root(cwd):
    # Local absolute paths only; the result is a location hint, not authority.
    cwd = handoff_entry.plain_path(cwd)
    if not (isinstance(cwd, str) and 0 < len(cwd) <= MAX_LOCATION_CHARS
            and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in cwd)
            and (re.match(r"^[A-Za-z]:[\\/]", cwd) or cwd.startswith("/"))
            and not cwd.replace("\\", "/").startswith("//")
            and ".." not in cwd.replace("\\", "/").split("/")):
        return None
    root = cwd.replace("\\", "/").rstrip("/")
    if not root or re.fullmatch(r"[A-Za-z]:", root):
        root += "/"
    return root


def task_pointer_path(root, target):
    # Case-sensitive identity -> portable filename, including on Windows.
    # This is a locator, not authorization or proof that a document exists.
    key = hashlib.sha256(target.encode("ascii")).hexdigest()
    return root.rstrip("/") + "/docs/handoffs/by-task/task-" + key + ".md"


def paste_line(target, root):
    entry = {"mode": "manual-paste-v1", "predecessor": target, "workspace": root,
             "handoff": task_pointer_path(root, target), "locator": "task-pointer-v1"}
    location = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    return ("使用 $context-handoff 按人工粘贴确认模式接班：" + location
            + "；我确认交接并不再使用旧任务。先自行只读核实旧任务已空闲、后台作业已结束、"
              "工作区与交接记录一致，发现异常再问我；然后读交接文档接手并回报，不归档或删除任务。"
              "任务定位入口缺失或身份不符时只读报告，不猜测或改用其他任务文档。")


def handoff_message(target, root):
    return ("已在压缩前停止：本任务已封存交接（以宿主停止状态为准）。"
            "在同一项目新建一个任务，在聊天输入框粘贴下面这一整行即确认交接（不是PowerShell）；"
            "不要再使用旧任务，也不要重复新建。新任务会自行核实旧任务和后台状态，发现异常才会问你。\n"
            + paste_line(target, root))


def valid_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def configured_id(args):
    # Do not use argparse's successful plain-text --help/usage path as a hook.
    if args == [ALL_SESSIONS]:
        return ALL_SESSIONS
    if len(args) != 2 or args[0] != "--session-id" or not valid_id(args[1]):
        return None
    return args[1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("nonstandard JSON number")


def decide(raw, target, settings=None):
    universal = target == ALL_SESSIONS
    if not universal and not valid_id(target):
        return {}
    try:
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_INPUT_BYTES:
            return {}
        event = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        if not isinstance(event, dict):
            return {}
        if event.get("hook_event_name") != "PreCompact":
            return {}
        if event.get("trigger") not in ("auto", "manual"):
            return {}
        session_id = event.get("session_id")
        if not valid_id(session_id):
            return {}
        if not universal and session_id != target:
            return {}
        root = normalized_root(event.get("cwd"))
        # Transcript/approval/document contents cannot authorize or force a stop.
        if root is None or not handoff_entry.prepared(task_pointer_path(root, session_id), session_id, root, settings):
            return {}
        return veto(handoff_message(session_id, root))
    except (ValueError, UnicodeError, RecursionError, TypeError):
        return {}


def run(args, input_stream, output_stream):
    config = None
    if len(args) >= 2 and args[-2] == "--config":
        config, args = args[-1], args[:-2]
    target = configured_id(args)
    if target is None:
        result = {}
    else:
        try:
            settings = handoff_entry.load_settings(config)
            result = decide(input_stream.read(MAX_INPUT_BYTES + 1), target, settings)
        except Exception:
            # Do not echo raw data, exception messages or user paths.
            result = {}
    payload = (json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
    try:
        written = output_stream.write(payload)
        if written != len(payload):
            return 1
        output_stream.flush()
    except Exception:
        # Lost stdout cannot be repaired by claiming the host stopped.
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:], sys.stdin.buffer, sys.stdout.buffer))
    except (AttributeError, OSError):
        raise SystemExit(1)
