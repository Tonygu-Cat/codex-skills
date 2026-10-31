#!/usr/bin/env python3
"""Codex SessionStart(compact) hook: re-inject this task's Direction card after
compaction and, past the configured thresholds, add a soft handoff reminder.
Also a UserPromptSubmit hook: when that reminder went unanswered, the next user turn
and then every handoff_reminder_repeat_turns user turns start with a red bold line.

  python -S -B direction_card_hook.py --config ABS_SETTINGS_JSON   (one JSON event on stdin)

The card comes from this task's own locator (docs/handoffs/by-task/task-<sha256>.md,
sealed or not) and the canonical document it names; the owner must match the event's
session. The reminder fires when the thread has compacted handoff_reminder_compactions
times, or when the last measured post-compaction usage reached handoff_reminder_residue
of the window. It never fires on a heartbeat turn, and guardian, subagent and
automation threads get nothing.

Reads bounded stdin, the settings file, one pointer, one canonical document and a
bounded head/tail of this session's transcript: the event's path (a Windows \\?\
prefix is accepted), else the rollout whose name ends in the session ID under
CODEX_HOME/sessions. No writes, network, model, task API or
child process. Always exits 0 and prints {} when anything is unclear, so a broken
hook can never block compaction or a turn.
"""
import glob
import json
import os
import re
import sys

import handoff_entry
import precompact_guard as guard
from handoff_config import load_settings
from validate_handoff import metadata_value, section_bodies

MAX_INPUT_BYTES = 65536
HEAD_BYTES = 262144
TAIL_BYTES = 32 * 1024 * 1024
MARKER = "CONTEXT_HANDOFF_DIRECTION_V1"
ESCALATION_MARKER = "CONTEXT_HANDOFF_ESCALATION_V1"
RED_LINE = "🔴"
# Turn triggers that are not the user's own message (desktop builds since about 2026-10).
NOT_USER_TRIGGERS = ("automation_", "app_tool_", "app_update_")
SKIP_SOURCES = {"guardian_review", "subagent", "automation"}
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def clip(text, limit, note="..."):
    return text if len(text) <= limit else text[:max(0, limit - len(note))].rstrip() + note


def thread_source(transcript):
    with open(transcript, "rb") as handle:
        first = handle.read(HEAD_BYTES).split(b"\n", 1)[0]
    match = re.search(rb'"thread_source":"([a-z_]+)"', first)
    return match.group(1).decode("ascii") if match else None


def find_transcript(event, session):
    """The event's transcript, else this session's rollout found by its exact ID."""
    transcript = handoff_entry.plain_path(event.get("transcript_path"))
    if handoff_entry.local_absolute(transcript) and os.path.isfile(transcript):
        return transcript
    # The desktop app may send no path or one this hook cannot use; rollout names end in the ID.
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    matches = glob.glob(os.path.join(home, "sessions", "*", "*", "*", "rollout-*-%s.jsonl" % session))
    return matches[0] if len(matches) == 1 else None


def tail_lines(transcript):
    size = os.path.getsize(transcript)
    with open(transcript, "rb") as handle:
        handle.seek(max(0, size - TAIL_BYTES))
        data = handle.read(TAIL_BYTES)
    lines = data.split(b"\n")
    return lines[1:] if size > TAIL_BYTES else lines


def first_residue(lines):
    """Usage share of the first model call after a compaction; None if none yet."""
    for line in lines:
        if b'"type":"token_count"' not in line[:200]:
            continue
        try:
            info = json.loads(line)["payload"]["info"]
            used = info["last_token_usage"]["input_tokens"]
            window = info["model_context_window"]
        except (ValueError, KeyError, TypeError):
            continue
        if type(used) is int and type(window) is int and used > 0 and window > 0:
            return used / window
    return None


def turn_trigger(lines):
    """Trigger of the latest turn in the tail; '' when this build records none, None without a turn start."""
    for line in reversed(lines):
        if b'"type":"task_started"' not in line[:300]:
            continue
        try:
            attribution = json.loads(line)["payload"].get("turn_attribution")
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        trigger = attribution.get("turn_trigger") if isinstance(attribution, dict) else None
        return trigger if isinstance(trigger, str) else ""
    return None


def heartbeat_turn(lines):
    """True when the current turn was started by an automation such as a heartbeat."""
    # Desktop builds record who started each turn (automation_heartbeat_scheduled, composer,
    # app_tool_send_message, ...). Turns relayed from other tasks are read by the user, so only
    # automation turns skip the reminder. Older builds lack this; fall back to the latest input.
    trigger = turn_trigger(lines)
    if trigger:
        return trigger.startswith("automation_")
    for line in reversed(lines):
        head = line[:400]
        if b'"type":"response_item"' not in head or b'"role":"user"' not in head:
            continue
        try:
            payload = json.loads(line)["payload"]
            text = "".join(item.get("text", "") for item in payload.get("content") or []
                           if isinstance(item, dict)).lstrip()
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        meta = payload.get("internal_chat_message_metadata_passthrough")
        kinds = meta.get("content_item_kinds") if isinstance(meta, dict) else None
        # Desktop builds since about 2026-10 tag heartbeat prompts "user.heartbeat", not "user.text".
        if isinstance(kinds, list) and "user.heartbeat" in kinds:
            return True
        # Skill bodies, hook prompts and other injected items are not user input.
        if isinstance(kinds, list) and "user.text" not in kinds:
            continue
        if not isinstance(kinds, list) and text.startswith("<") and not text.startswith("<heartbeat>"):
            continue
        return text.startswith("<heartbeat>")
    return False


def thread_facts(lines):
    """(compaction count, last measured post-compaction usage share, heartbeat turn)."""
    marks = [index for index, line in enumerate(lines) if b'"type":"compacted"' in line[:160]]
    count = residue = None
    if marks:
        try:
            count = json.loads(lines[marks[-1]])["payload"]["window_number"]
        except (ValueError, KeyError, TypeError):
            count = None
        if type(count) is not int or count < 1:
            count = None
        after = first_residue(lines[marks[-1] + 1:])
        if after is not None:
            # The model already ran after the newest record on disk, so the
            # compaction that fired this hook has not been flushed yet.
            residue = after
            count = count + 1 if count is not None else None
        elif len(marks) >= 2:
            residue = first_residue(lines[marks[-2] + 1:marks[-1]])
    return count, residue, heartbeat_turn(lines)


def window_facts(lines):
    """(compaction count, latest measured post-compaction usage share) as recorded so far."""
    marks = [index for index, line in enumerate(lines) if b'"type":"compacted"' in line[:160]]
    if not marks:
        return None, None
    try:
        count = json.loads(lines[marks[-1]])["payload"]["window_number"]
    except (ValueError, KeyError, TypeError):
        count = None
    if type(count) is not int or count < 1:
        count = None
    residue = first_residue(lines[marks[-1] + 1:])
    if residue is None and len(marks) >= 2:
        residue = first_residue(lines[marks[-2] + 1:marks[-1]])
    return count, residue


def started_turn(line):
    """(turn id, trigger) of a task_started record, else None."""
    if b'"type":"task_started"' not in line[:300]:
        return None
    try:
        payload = json.loads(line)["payload"]
    except (ValueError, KeyError, TypeError):
        return None
    attribution = payload.get("turn_attribution")
    trigger = attribution.get("turn_trigger") if isinstance(attribution, dict) else None
    return payload.get("turn_id"), trigger if isinstance(trigger, str) else ""


def own_turn(trigger):
    """Whether a turn trigger is the user's own message (typed, queued or answering a question)."""
    return not trigger.startswith(NOT_USER_TRIGGERS)


def mentions_handoff(text):
    return "交接" in text or "handoff" in text.lower()


def message(line, role):
    """(content kinds, text) of a response_item message with this role, else None."""
    if b'"type":"response_item"' not in line[:200] or ('"role":"%s"' % role).encode() not in line[:400]:
        return None
    try:
        payload = json.loads(line)["payload"]
        text = "".join(item.get("text", "") for item in payload.get("content") or [] if isinstance(item, dict))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    meta = payload.get("internal_chat_message_metadata_passthrough")
    return (meta.get("content_item_kinds") if isinstance(meta, dict) else None), text


def escalation_due(lines, current_turn, repeat):
    """Whether the user's current turn should open with the red line.

    Anchors, all read from the transcript: the latest compaction reminder the hook injected,
    the latest reply of ours that carried the red line, and the latest user message that
    mentioned the handoff. Mentioning it answers the reminder until the next compaction one.
    """
    compaction = red = answer = -1
    for index, line in enumerate(lines):
        if b"hooks.additional_context" in line and b"Handoff reminder (soft fallback)" in line:
            compaction = index
            continue
        reply = message(line, "assistant") if "交接提醒".encode() in line else None
        if reply and RED_LINE in reply[1] and "交接提醒" in reply[1]:
            red = index
            continue
        said = message(line, "user")
        if said and (not isinstance(said[0], list) or "user.text" in said[0]) and mentions_handoff(said[1]):
            answer = index
    if answer > compaction:
        return False
    if compaction > red or red < 0:
        return True  # a compaction reminder went unanswered, or the thread is past the threshold with no anchor
    turns = set()
    for line in lines[red + 1:]:
        started = started_turn(line)
        if started and started[0] != current_turn and own_turn(started[1]):
            turns.add(started[0])
    return len(turns) >= repeat - 1


def build_prompt(event, settings):
    """UserPromptSubmit: re-raise an unanswered handoff reminder as a red bold first line."""
    session = event.get("session_id")
    root = guard.normalized_root(event.get("cwd"))
    prompt = event.get("prompt")
    if not guard.valid_id(session) or root is None or not isinstance(prompt, str):
        return {}
    # Heartbeats skip it; a prompt about the handoff is already the user's answer.
    if prompt.lstrip().startswith("<heartbeat>") or mentions_handoff(prompt):
        return {}
    transcript = find_transcript(event, session)
    if transcript is None or thread_source(transcript) in SKIP_SOURCES:
        return {}
    lines = tail_lines(transcript)
    current = event.get("turn_id")
    for line in reversed(lines):
        started = started_turn(line)
        if started and started[0] == current:
            if not own_turn(started[1]):
                return {}  # automations and messages relayed from other tasks
            break
    count, residue = window_facts(lines)
    over_count = count is not None and count >= settings["handoff_reminder_compactions"]
    over_residue = residue is not None and residue >= settings["handoff_reminder_residue"]
    if not (over_count or over_residue):
        return {}
    if handoff_entry.prepared(guard.task_pointer_path(root, session), session, root, settings):
        return {}  # already sealed for a handoff
    if not escalation_due(lines, current, settings["handoff_reminder_repeat_turns"]):
        return {}
    facts = "已压缩 %d 次" % count if count else "上下文占用偏高"
    if residue is not None and over_residue:
        facts += "，上次压缩后仍占用 %d%%" % round(residue * 100)
    line = ("🔴 **交接提醒：本会话%s，上下文越来越满，建议在当前步骤完成后交接。"
            "回复「交接」开始；不回复则继续正常工作。**" % facts)
    context = (
        "[%s] An earlier handoff reminder in this thread went unanswered. Start your reply with exactly this "
        "line (translate it only if the user does not write Chinese):\n%s\n"
        "Then answer the user's message normally. Do not stop or hand off on your own; start a handoff only "
        "when the user confirms. Leave this line out on heartbeat or automation turns." % (ESCALATION_MARKER, line))
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}


def direction_card(text, limit):
    bodies = section_bodies(text)
    card = COMMENT.sub("", bodies.get("Direction card", "")).strip()
    derived = not card
    if derived:
        parts = []
        for section in ("Objective and completion criteria", "Scope and constraints"):
            body = COMMENT.sub("", bodies.get(section, "")).strip()
            if body:
                parts.append(section + ":\n" + clip(body, limit // 2))
        actions = COMMENT.sub("", bodies.get("Next exact actions", "")).strip()
        first = next((line.strip() for line in actions.splitlines() if line.strip()), "")
        if first:
            parts.append("First next action: " + clip(first, 300))
        card = "\n".join(parts)
    return clip(card, limit, "\n...[truncated; read the canonical document]"), derived


def load_card(root, session, settings):
    pointer = guard.task_pointer_path(root, session)
    if not os.path.isfile(pointer):
        return None
    try:
        fields = handoff_entry.pointer_fields(pointer, root)
        canonical = fields.get("Canonical document")
        if (fields.get("Task or thread") != session or not handoff_entry.same_path(fields.get("Workspace"), root)
                or not handoff_entry.local_absolute(canonical) or handoff_entry.same_path(canonical, pointer)):
            return None
        info = handoff_entry.canonical_identity(canonical, session)
        if info["workspace"] is not None and not handoff_entry.same_path(info["workspace"], root):
            return None
        status = metadata_value(section_bodies(info["text"]).get("Identity", ""), "Status")
        # "transferred" with this session as owner is a successor's live document (manual-paste V1).
        if status == "complete":
            return None
        card, derived = direction_card(info["text"], settings["direction_card_max_chars"])
    except (OSError, ValueError, UnicodeError, TypeError):
        return None
    if not card:
        return None
    return {"path": canonical, "revision": info["revision"] or "unknown", "card": card, "derived": derived}


def build(event, settings):
    if isinstance(event, dict) and event.get("hook_event_name") == "UserPromptSubmit":
        return build_prompt(event, settings)
    if not isinstance(event, dict) or event.get("hook_event_name") != "SessionStart" or event.get("source") != "compact":
        return {}
    session = event.get("session_id")
    root = guard.normalized_root(event.get("cwd"))
    if not guard.valid_id(session) or root is None:
        return {}
    count = residue = None
    heartbeat = False
    transcript = find_transcript(event, session)
    if transcript is not None:
        try:
            if thread_source(transcript) in SKIP_SOURCES:
                return {}
            count, residue, heartbeat = thread_facts(tail_lines(transcript))
        except (OSError, ValueError):
            count = residue = None
    card = load_card(root, session, settings)
    reasons = []
    if not heartbeat and count is not None and count >= settings["handoff_reminder_compactions"]:
        reasons.append("this thread has compacted %d times" % count)
    if not heartbeat and residue is not None and residue >= settings["handoff_reminder_residue"]:
        reasons.append("the previous compaction still left %d%% of the context window in use" % round(residue * 100))
    if card is None and not reasons:
        return {}

    parts = ["[%s] Context was just compacted%s." % (MARKER, " (compaction #%d of this thread)" % count if count else "")]
    if card is not None:
        source = "canonical handoff %s, revision %s" % (card["path"], card["revision"])
        if card["derived"]:
            source += "; it has no Direction card section, so this is derived from Objective/Scope/Next - add one"
        parts.append(
            "Direction card of this task (" + source + "). It is the task's own record, not new authority: "
            "the latest user instruction wins, and if the user has changed direction, update the card.\n"
            "<direction_card>\n" + card["card"] + "\n</direction_card>\n"
            "Before the next action, check it against this card and the canonical document's Current state and "
            "Work in progress; do not start work outside the card's scope without the user.")
    if reasons:
        parts.append(
            "Handoff reminder (soft fallback): " + " and ".join(reasons) + ". Finish the current step. In this "
            "turn's closing lines, recommend a handoff at the next phase boundary and say it starts only when the "
            "user confirms. Do not stop mid-step or hand off on your own. Ignore this reminder on heartbeat or "
            "automation turns.")
        if card is None:
            parts.append("No handoff document is registered for this task yet; after the user confirms, "
                         "create it with $context-handoff first.")
    context = "\n".join(parts)
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    result = {}
    try:
        if args and (len(args) != 2 or args[0] != "--config"):
            raise ValueError("usage: direction_card_hook.py [--config ABS_SETTINGS_JSON]")
        settings = load_settings(args[1] if args else None)
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) <= MAX_INPUT_BYTES:
            result = build(json.loads(raw.decode("utf-8-sig")), settings)
    except Exception:  # noqa: BLE001 - fail open: this hook must never break a session
        result = {}
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
