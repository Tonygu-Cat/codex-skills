#!/usr/bin/env python3
"""Read and validate the one settings source; never edits configuration."""
import argparse
import json
import math
from pathlib import Path

# Required fields: every settings file states them explicitly.
DEFAULTS = {"max_document_bytes": 61440, "max_current_state_lines": 80,
            "handoff_reminder_compactions": 10, "handoff_reminder_residue": 0.25}
# Optional fields, filled in when absent. context_threshold only feeds the retired,
# undeployed context_budget_guard.py and is kept so older fixtures still load.
OPTIONAL = {"context_threshold": 0.85, "direction_card_max_chars": 1500, "handoff_reminder_repeat_turns": 4}
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "settings.json"


class ConfigError(ValueError):
    pass


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate configuration field")
        result[key] = value
    return result


def _ratio(values, field):
    ratio = values[field]
    if type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 < ratio < 1:
        raise ConfigError(field + " must be a finite ratio strictly between 0 and 1")


def _integer(values, field, low=1, high=None):
    value = values[field]
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ConfigError(field + " must be an integer " + (f"between {low} and {high}" if high else f">= {low}"))


def validate_settings(values):
    if not isinstance(values, dict):
        raise ConfigError("configuration must be a JSON object")
    if set(DEFAULTS) - set(values) or set(values) - set(DEFAULTS) - set(OPTIONAL):
        raise ConfigError("configuration must contain the four required fields and only known optional fields")
    merged = dict(OPTIONAL, **values)
    _ratio(merged, "context_threshold")
    _ratio(merged, "handoff_reminder_residue")
    _integer(merged, "max_document_bytes")
    _integer(merged, "max_current_state_lines")
    _integer(merged, "handoff_reminder_compactions", 1, 1000)
    _integer(merged, "direction_card_max_chars", 200, 8000)
    _integer(merged, "handoff_reminder_repeat_turns", 1, 100)
    return merged


def load_settings(path=None, threshold=None):
    source = Path(path) if path is not None else DEFAULT_PATH
    if not source.is_absolute():
        raise ConfigError("settings path must be absolute")
    try:
        with source.open("rb") as handle:
            raw = handle.read(8193)
        if len(raw) > 8192:
            raise ConfigError("settings file too large")
        values = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError("cannot load valid handoff settings") from exc
    values = validate_settings(values)
    # Compatibility for existing test hooks. No other threshold is overridden.
    if threshold is not None:
        values = validate_settings(dict(values, context_threshold=threshold))
    return values


def slimming_targets(settings):
    return {"document_bytes": min(40960, max(1, settings["max_document_bytes"] * 2 // 3)),
            "current_state_lines": min(60, max(1, settings["max_current_state_lines"] * 3 // 4))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
    except ConfigError as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps({"source": str(args.config or DEFAULT_PATH), "settings": settings,
                      "slimming_targets": slimming_targets(settings)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
