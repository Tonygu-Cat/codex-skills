# Task Operations Stop Hook

The guard requires a nonempty `用户操作：` / `User action:` field on opted-in final replies, including successful milestones. For common failure, unfinished-work, pending-authorization and pending-choice wording, it also requires nonempty current-goal and next-step fields. It checks structure, not semantic completion or permission validity; not every paraphrase is detectable.

## Behavior

- It activates only after the task transcript contains the Skill receipt `TASK_OPS_ACTIVE=1`.
- It reads `last_assistant_message` on the `Stop` event.
- It blocks at most once because it exits without another continuation when `stop_hook_active` is true.
- It never executes a recovery action, grants permission, broadens scope, or marks a goal complete.
- It passes completed responses with an explicit user-action field and tasks that did not opt in. Optional recommendation and resolved-failure clauses do not count as required work.
- It reads UTF-8 stdin and emits ASCII-escaped JSON, independent of the Windows console encoding.
- If the transcript path is absent or unreadable and the current message does not contain the receipt, it fails open rather than enforcing task-operations on a task that may have declined it.

The transcript check deliberately searches only for the stable receipt string. Quoted receipts can also match; this is a delivery-quality aid, not a consent or security authority. Codex documents `transcript_path` as convenient but not a stable transcript schema, so the script does not parse transcript records. A missing activation receipt still bypasses the guard: installation must preserve the receipt instruction and confirm explicit Skill loading.

## User-level configuration

Install `scripts/stop_guard.py` with the Skill, then add a `Stop` entry to the existing user-level `~/.codex/hooks.json`. Merge with existing hooks rather than overwriting them, and replace both placeholders with trusted absolute paths:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"<ABSOLUTE_PYTHON_PATH>\" \"<ABSOLUTE_SKILL_PATH>/scripts/stop_guard.py\"",
            "commandWindows": "& \"<ABSOLUTE_PYTHON_PATH>\" \"<ABSOLUTE_SKILL_PATH>/scripts/stop_guard.py\"",
            "timeout": 10,
            "statusMessage": "Checking task continuation contract"
          }
        ]
      }
    ]
  }
}
```

Codex requires review and trust for new or changed non-managed hooks. Inspect and trust the exact definition through the host's hook review surface before relying on it.

The Windows override above targets PowerShell: quoted executable paths require the `&` invocation operator. Verify the actual host shell; merely parsing JSON or launching Python directly does not test this shell boundary. A host with a different shell needs its native command syntax.

## Installation consistency and rollback

Pin the source to an exact commit of this repository. Install into the current `$CODEX_HOME/skills/task-operations`, defaulting to `~/.codex/skills/task-operations`. Inspect legacy `~/.agents/skills/task-operations` copies; preserve their local changes in backups and synchronize discoverable duplicates from that same pinned source. Point the Hook at the canonical installed script, not a different version. Preserve explicit-only invocation policy; omission from automatically supplied Skill metadata alone is not proof of installation failure.

Before replacement, preserve whole installed Skill directories, Hook configuration and relevant trust configuration outside Skill discovery directories. Retain immediate-prechange snapshots and user-requested historical versions. Verify file hashes, script subprocess behavior and host Active status separately; Active alone is not behavioral acceptance. Reopen a host session to verify persisted trust. Disclose whether a fresh opted-in task has been tested.

Rollback only this Skill's files and Hook entry. Preserve unrelated changes made since backup; never restore an entire old config over new unrelated settings. Restored definitions may require trust review. Disable this Hook when restoring an instruction-only version without its script. Do not manufacture trust hashes or silently follow a moving branch.

Official behavior reference: [Codex hooks](https://learn.chatgpt.com/docs/hooks).
