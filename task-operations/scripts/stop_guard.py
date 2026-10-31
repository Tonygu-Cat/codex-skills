#!/usr/bin/env python3
"""Check opted-in final handoffs; request at most one corrective continuation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ACTIVATION_RECEIPT = "TASK_OPS_ACTIVE=1"
FAILURE_PATTERN = re.compile(
    r"(?:已失败|失败关闭|仍未完成|无法继续|当前阻塞|"
    r"状态\s*[:：]\s*(?:失败|阻塞|未完成)|"
    r"\bstatus\s*:\s*(?:failed|blocked|incomplete)\b|"
    r"\b(?:attempt|step|task|operation|run|tests?)\s+(?:has\s+)?failed\b|"
    r"\b(?:task|operation)\s+is\s+blocked\b)",
    re.IGNORECASE,
)
PENDING_PATTERN = re.compile(
    r"(?:尚待|有待|仍需|还需|还剩|待办|待授权|待批准|待确认|待选择|待合并|待部署|"
    r"未部署|未合并|未完成|未通过|需要.{0,12}(?:授权|批准|确认|选择)|"
    r"等待.{0,12}(?:授权|批准|确认|选择)|"
    r"\b(?:todo|pending|awaiting|unfinished|incomplete|blocked)\b|"
    r"\bstill (?:needs?|requires?|remains?)\b|\b(?:needs?|requires?) approval\b)",
    re.IGNORECASE,
)
OPTIONAL_PATTERN = re.compile(r"(?:可选|非必需|非必做|不在本次范围|\boptional\b|out.of.scope)", re.I)
RESOLVED_PATTERN = re.compile(
    r"(?:无(?:待办|剩余|未完成)|没有(?:待办|剩余)|无需|不需要|已解决|现已通过|"
    r"\bno (?:pending|remaining|outstanding)\b|\bnow pass\b|\bresolved\b)", re.I
)


def _field(message: str, label: str) -> str:
    match = re.search(rf"(?:{label})[ \t]*\**[ \t]*[:：][ \t]*\**([^\n\r；;]*)", message, re.I)
    return match.group(1).strip(" *`\t。.") if match else ""


def _has_pending_work(message: str) -> bool:
    # Optional recommendations and resolved failures are not unfinished scope.
    for clause in re.split(r"[\n。；;]|(?<=[.!?])\s+", message):
        if OPTIONAL_PATTERN.search(clause) or RESOLVED_PATTERN.search(clause):
            continue
        if FAILURE_PATTERN.search(clause) or PENDING_PATTERN.search(clause):
            return True
    return False


def _emit(payload: dict[str, Any]) -> None:
    # Keep the hook wire independent of Windows console encodings.
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=True).encode("ascii"))


def _is_active(transcript_path: object, message: str) -> bool:
    if ACTIVATION_RECEIPT in message:
        return True
    if not isinstance(transcript_path, str) or not transcript_path:
        return False
    try:
        return ACTIVATION_RECEIPT in Path(transcript_path).read_text(
            encoding="utf-8", errors="ignore"
        )
    except OSError:
        return False


def evaluate(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("hook_event_name") != "Stop" or event.get("stop_hook_active"):
        return {}

    message = event.get("last_assistant_message")
    if isinstance(message, str) and message.lstrip().startswith("<heartbeat>"):
        # Host heartbeat replies follow the host's own NOTIFY/DONT_NOTIFY format.
        return {}
    if not isinstance(message, str) or not _is_active(event.get("transcript_path"), message):
        return {}
    missing = []
    action = _field(message, r"用户操作|user action")
    pending = _has_pending_work(message)
    if pending:
        if not _field(message, r"当前目标|current goal"):
            missing.append("当前目标")
        if not _field(message, r"下一步|next step"):
            missing.append("下一步")
    if not action:
        missing.append("用户操作（无需，或具体动作/准确回复）")
    elif pending and re.search(r"^(?:需要|待|等待|请|需|required|needed|pending)$", action, re.I):
        missing.append("具体用户操作，不能只写需要或待确认")
    if not missing:
        return {}

    fields = "、".join(missing)
    return {
        "decision": "block",
        "reason": (
            f"任务运营检查：当前结束回复缺少{fields}。"
            "若目标仍可实现，继续同一目标；仍在授权范围内则直接执行，"
            "需要新授权或选择时给出唯一下一步和最短准确回复。"
            "已完成则明确写用户操作：无需；不要制造待办或执行范围外建议。"
            "这只是一次交付检查，不构成重试、合并或部署的新授权。"
        ),
    }


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        _emit({})
        return 0
    _emit(evaluate(event if isinstance(event, dict) else {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
