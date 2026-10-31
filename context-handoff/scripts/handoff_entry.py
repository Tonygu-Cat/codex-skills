"""Bounded, read-only handoff identity checks shared by pointer writer and veto."""
import hashlib
import os
import re
import stat
import unicodedata
from pathlib import Path
from handoff_config import load_settings
from validate_handoff import metadata_value, section_bodies, validate_text

MAX_POINTER_BYTES = 8192
MAX_CANONICAL_BYTES = 2 * 1024 * 1024


def read_bytes(path, limit):
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise ValueError("handoff input is not a regular file")
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("handoff file exceeds bounded reader limit")
    return data


def plain_path(value):
    """Drop a Windows extended-length prefix (\\\\?\\D:\\...), which the desktop app uses.

    \\\\?\\UNC\\ network paths keep their prefix, so local-only checks still reject them.
    """
    if isinstance(value, str) and value.startswith("\\\\?\\") and not value[4:8].upper() == "UNC\\":
        return value[4:]
    return value


def local_absolute(value):
    return (isinstance(value, str) and os.path.isabs(value)
            and not value.replace("\\", "/").startswith("//")
            and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value)
            and ".." not in value.replace("\\", "/").split("/"))


def same_path(left, right):
    return local_absolute(left) and local_absolute(right) and (
        os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right)))


def canonical_info(path, task, settings=None):
    if not local_absolute(str(path)):
        raise ValueError("canonical path must be local and absolute")
    raw = read_bytes(path, MAX_CANONICAL_BYTES)
    text = raw.decode("utf-8-sig")
    errors, _ = validate_text(text, settings=settings or load_settings(), byte_size=len(raw),
                              require_handoff=True)
    if errors:
        raise ValueError("canonical document is not ready to seal: " + "; ".join(errors[:3]))
    identity = section_bodies(text)["Identity"]
    if metadata_value(identity, "Task or thread") != task:
        raise ValueError("canonical owner does not match this task")
    if not same_path(metadata_value(identity, "Canonical document"), str(path)):
        raise ValueError("canonical identity path mismatch")
    # The owner check above makes a "transferred" document this successor's own, so it may hand off again.
    if metadata_value(identity, "Status") == "complete":
        raise ValueError("completed task does not need another handoff")
    return {"sha256": hashlib.sha256(raw).hexdigest(),
            "revision": metadata_value(identity, "Handoff revision"), "raw": raw,
            "workspace": metadata_value(identity, "Workspace")}


def canonical_identity(path, task):
    """Light owner/path check for an unsealed locator; no size or structure gate."""
    if not local_absolute(str(path)):
        raise ValueError("canonical path must be local and absolute")
    raw = read_bytes(path, MAX_CANONICAL_BYTES)
    text = raw.decode("utf-8-sig")
    identity = section_bodies(text).get("Identity", "")
    if metadata_value(identity, "Task or thread") != task:
        raise ValueError("canonical owner does not match this task")
    if not same_path(metadata_value(identity, "Canonical document"), str(path)):
        raise ValueError("canonical identity path mismatch")
    return {"text": text, "revision": metadata_value(identity, "Handoff revision"),
            "workspace": metadata_value(identity, "Workspace")}


def pointer_fields(pointer, workspace):
    """Parse one task pointer inside the workspace; raise on anything ambiguous."""
    if not Path(pointer).resolve().is_relative_to(Path(workspace).resolve()):
        raise ValueError("pointer outside workspace")
    text = read_bytes(pointer, MAX_POINTER_BYTES).decode("utf-8-sig")
    labels = re.findall(r"(?m)^- ([^:\r\n]+):", text)
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate pointer field")
    pairs = re.findall(r"(?m)^- ([^:\n]+):[ \t]*`([^`\r\n]+)`[ \t\r]*$", text)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("duplicate pointer field")
    return fields


def prepared(pointer, task, workspace, settings=None):
    try:
        fields = pointer_fields(pointer, workspace)
        if fields.get("Task or thread") != task or not same_path(fields.get("Workspace"), workspace):
            return False
        canonical = fields.get("Canonical document")
        if not local_absolute(canonical) or same_path(canonical, pointer):
            return False
        info = canonical_info(canonical, task, settings)
        if info["workspace"] is not None and not same_path(info["workspace"], workspace):
            return False
        # Seal the exact saved version. Old three-field locators remain readable
        # by a successor, but do not qualify for an automatic veto.
        return (fields.get("Canonical SHA256") == info["sha256"]
                and fields.get("Handoff revision") == info["revision"])
    except (OSError, ValueError, UnicodeError, TypeError):
        return False
