#!/usr/bin/env python3
"""Stop hook: once context usage crosses a threshold, ask for a handoff once.

  python -S -B context_budget_guard.py [--threshold 0.85]

Advisory and fail-open: any error, missing data or out-of-scope session returns {}.
Blocks at most one continuation per stop (stop_hook_active) and stays quiet after the
task replied with CONTEXT_HANDOFF_READY since its last compaction. Heartbeat turns,
guardian/subagent and automation threads are skipped.
Reads the event, the first line and a bounded tail of transcript_path only. Never
writes files, starts processes, calls a model/network or creates tasks.
"""
import json
import os
import sys
import handoff_config

READY_MARKER = "CONTEXT_HANDOFF_READY"
MAX_EVENT_BYTES = 8 * 1024 * 1024
HEAD_BYTES = 256 * 1024
TAIL_BYTES = 4 * 1024 * 1024
SKIP_THREAD_SOURCES = {"guardian_review", "subagent", "automation"}
COMPACTION_TYPES = {"compaction", "context_compacted"}


def parse_threshold(args):
    try:
        return parse_settings(args)[0]["context_threshold"]
    except (ValueError, OSError):
        return None


def parse_settings(args):
    options = {}
    if len(args) % 2:
        raise ValueError("incomplete settings arguments")
    for key, value in zip(args[::2], args[1::2]):
        if key not in ("--config", "--threshold") or key in options:
            raise ValueError("invalid settings arguments")
        options[key] = value
    threshold = float(options["--threshold"]) if "--threshold" in options else None
    return handoff_config.load_settings(options.get("--config"), threshold), options.get("--config")


def is_ready(message):
    if not isinstance(message, str):
        return False
    # Mentioning the marker in prose or a code sample is not a readiness receipt.
    first = message.strip().splitlines()
    return bool(first and first[0].split(maxsplit=1)[0] == READY_MARKER)


def read_first_record(path):
    with open(path, "rb") as handle:
        line = handle.readline(HEAD_BYTES)
    record = json.loads(line.decode("utf-8"))
    return record if isinstance(record, dict) else {}


def read_tail_records(path):
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        handle.seek(max(0, size - TAIL_BYTES))
        data = handle.read(TAIL_BYTES)
    lines = data.decode("utf-8", "ignore").splitlines()
    if size > TAIL_BYTES:
        lines = lines[1:]  # drop the partial first line
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def payload(record):
    value = record.get("payload")
    return value if isinstance(value, dict) else {}


def message_text(item):
    parts = item.get("content")
    if not isinstance(parts, list):
        return ""
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str))


def is_compaction(record):
    return record.get("type") == "compacted" or payload(record).get("type") in COMPACTION_TYPES


def skipped_thread(meta):
    info = payload(meta)
    source = info.get("source")
    return (info.get("thread_source") in SKIP_THREAD_SOURCES
            or (isinstance(source, dict) and "subagent" in source))


def latest_usage(records):
    for record in reversed(records):
        if is_compaction(record):
            return None
        item = payload(record)
        if record.get("type") == "event_msg" and item.get("type") == "token_count":
            info = item.get("info")
            if not isinstance(info, dict):
                continue
            last = info.get("last_token_usage")
            used = last.get("input_tokens") if isinstance(last, dict) else None
            window = info.get("model_context_window")
            if type(used) is int and type(window) is int and used > 0 and window > 0:
                return used, window
    return None


def latest_turn_is_heartbeat(records):
    start = None
    for index in range(len(records) - 1, -1, -1):
        item = payload(records[index])
        if records[index].get("type") == "event_msg" and item.get("type") == "task_started":
            start = index
            break
    if start is None:
        return False
    for record in records[start + 1:]:
        item = payload(record)
        if record.get("type") == "response_item" and item.get("type") == "message" and item.get("role") == "user":
            return message_text(item).lstrip().startswith("<heartbeat>")
    return False


def ready_since_last_compaction(records):
    for record in reversed(records):
        if is_compaction(record):
            return False
        item = payload(record)
        if (record.get("type") == "response_item" and item.get("type") == "message"
                and item.get("role") == "assistant" and is_ready(message_text(item))):
            return True
    return False


def reason(percent, threshold_percent, settings=None, config_path=None):
    settings = settings or handoff_config.load_settings()
    config_note = (" 所有交接脚本使用同一 --config 参数：" + json.dumps(config_path, ensure_ascii=False)) if config_path else ""
    return ("上下文已用约 %d%%（交接提醒阈值 %d%%）。这是轮末提前提醒，不保证一定先于自动压缩。"
            "请立即暂停新的开发，只做交接：1) 用 $context-handoff 把唯一交接文档更新到当前进度；"
            "超过 %d 字节或当前状态超过 %d 个非空行先瘦身（历史保全到同目录文件）。"
            "2) 运行 context-handoff 的 scripts/write_task_pointer.py --canonical <唯一交接文档绝对路径>，"
            "生成本任务定位入口和接班行。3) 回复第一行写 %s，接着给出该接班行，"
            "并按推进契约请用户在同一项目新任务的聊天输入框粘贴，不是PowerShell。不要继续新开发，不要自行创建、归档或删除任务。"
            "若本任务已经完成或无需延续，以 %s 开头说明原因并停止，不要求用户另建任务。"
            % (percent, threshold_percent, settings["max_document_bytes"], settings["max_current_state_lines"], READY_MARKER, READY_MARKER)
            + config_note)


def evaluate(event, threshold, settings=None, config_path=None):
    if not isinstance(event, dict) or event.get("hook_event_name") != "Stop" or event.get("stop_hook_active"):
        return {}
    message = event.get("last_assistant_message")
    if isinstance(message, str) and (message.lstrip().startswith("<heartbeat>") or is_ready(message)):
        return {}
    path = event.get("transcript_path")
    if not isinstance(path, str) or not path or not os.path.isfile(path):
        return {}
    meta = read_first_record(path)
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id or payload(meta).get("id") != session_id:
        return {}
    if meta.get("type") != "session_meta" or skipped_thread(meta):
        return {}
    records = read_tail_records(path)
    if latest_turn_is_heartbeat(records):
        return {}
    usage = latest_usage(records)
    if usage is None:
        return {}
    used, window = usage
    if used / window < threshold:
        return {}
    if ready_since_last_compaction(records):
        return {}
    return {"decision": "block", "reason": reason(round(100 * used / window), round(100 * threshold), settings, config_path)}


def run(args, input_stream, output_stream):
    result = {}
    try:
        settings, config_path = parse_settings(args)
        raw = input_stream.read(MAX_EVENT_BYTES + 1)
        if isinstance(raw, bytes) and 0 < len(raw) <= MAX_EVENT_BYTES:
            result = evaluate(json.loads(raw.decode("utf-8")), settings["context_threshold"], settings, config_path)
    except Exception:
        result = {}
    try:
        output_stream.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
        output_stream.flush()
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:], sys.stdin.buffer, sys.stdout.buffer))
    except (AttributeError, OSError):
        raise SystemExit(1)
