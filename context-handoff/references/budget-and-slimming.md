# Adjustable thresholds and safe slimming

## One settings source

The component's `settings.json` holds four required fields and one optional field:

```json
{"max_document_bytes": 61440, "max_current_state_lines": 80,
 "handoff_reminder_compactions": 10, "handoff_reminder_residue": 0.25,
 "direction_card_max_chars": 1500}
```

| Field | Used by | Meaning |
| --- | --- | --- |
| `max_document_bytes`, `max_current_state_lines` | validator, slimmer, pointer writer, guard | slimming triggers |
| `handoff_reminder_compactions` | direction-card hook | remind once this thread has compacted this many times (1-1000) |
| `handoff_reminder_residue` | direction-card hook | remind when the previous compaction left at least this share of the window in use |
| `direction_card_max_chars` (optional) | hook, validator | card length; the hook truncates, sealing refuses (200-8000) |
| `handoff_reminder_repeat_turns` (optional) | UserPromptSubmit hook | after an unanswered reminder, repeat a red bold first line every this many user turns (1-100, default 4) |

These are the initial defaults, not fixed policy. Change them only at the user's request.
Ratios must be finite numbers strictly between 0 and 1; byte/line limits must be
positive integers. Unknown, missing or duplicate fields, booleans and NaN are errors.
File-size limits count actual saved bytes, including CRLF and a UTF-8 BOM;
current-state limits count nonempty lines. Equality is allowed; only excess triggers slimming.
`python -S -B scripts/handoff_config.py` shows the effective values and derived
slimming targets. All scripts also accept `--config ABS_PATH`; use that identical
source in hook definitions, validator, slimmer and pointer writer.

Default targets are min(40 KiB, 2/3 of configured byte limit) and min(60, 3/4 of
configured line limit), rounded down with minimum 1. Never relax the configured
limit because essential current requirements do not fit: stop and explain.

The 85% context-budget Stop hook (`context_budget_guard.py`) was retired on 2026-09-27.
It asked for a handoff at nearly every compaction cycle, which was too frequent.
`context_threshold` is now optional and read only by that retired script and its
tests. Do not register it again without a new user decision.

Reminder data comes from the transcript tail. The compaction count is the
`window_number` of the latest `compacted` record, plus one if the model has
already run after that record, meaning the triggering compaction was not flushed
yet. The residue is `input_tokens / model_context_window` of the first non-zero
`token_count` after the previous compaction. Server-side compaction makes the
post-compaction baseline grow over a thread's life. The measured medians are
about 10% for compactions 1-10, 13% for 11-20, 17% for 21-50 and 37% beyond that,
so both defaults target long, bloated threads rather than normal work. The hook
reads at most 32 MiB of the tail. A compaction outside that window is not
counted, which errs toward no reminder.

Each invocation reads settings afresh. A settings-value edit applies at the next
script invocation, not retroactively to an in-flight run. Changing a hook command
or config path requires normal exact-definition review/trust and verifying that
each affected host loaded the new definition. File edits do not prove that an
already-open task runs the hook. Do not change trust storage.

Invalid settings: read-only hook handlers release the event; the settings inspector,
validator, pointer writer and slimmer report failure and do not publish. No fallback
to guessed values. The reminder is advice after a compaction, never a stop.

## Safe slimming workflow

Only the authorized sole document writer performs this workflow. It does not
authorize taking over another task or archiving a task.

1. Read the full canonical and effective settings. Record the raw-byte SHA256 and
   revision. Decide what is superseded; retain current goal, authority, blockers
   and exact next action in full. Preserve all original evidence.
2. Draft a separate Markdown file beside the canonical. Keep identity/ownership,
   the four protected sections and any existing Direction card unchanged, advance
   revision by one and update time.
   Condense current state and history semantically, not by truncation. Include the
   original hash and a reference to `HISTORY_THROUGH_R<old_revision>.md`.
3. Run `slim_handoff.py --canonical ABS --candidate ABS --task-id EXACT_ID
   --expected-sha256 LOWERCASE_SHA256` with the same `--config` if selected.
   This is a dry-run and changes nothing. Read the candidate to check it remains
   sufficient for a successor; structural PASS does not prove that.
4. If approved scope and sole-writer conditions still hold, repeat with `--apply`.
   The helper preserves every original byte in the history file before atomic
   publication and readback. It refuses conflicting history, stale input, changed
   ownership/authority, invalid structure, excess targets or detected concurrent
   edits. The helper lock only coordinates other helper invocations, not arbitrary
   writers. Do not treat it as OS fencing.
5. Re-read canonical and history/hash; retain the draft until outcome is known.
   An error after history creation leaves that history intact. Unknown outcomes
   require read-only reconciliation, never a blind second apply. Refresh the
pointer only after the final document is validated.

The pointer writer emits its pasteable locator as UTF-8, including when Windows
redirected Python defaults to GBK. Capture/decode this output as UTF-8 and paste it
in the chat composer; do not transcode paths or execute the line in PowerShell.

The canonical must be separate from its generated task pointer and history file.
Before writing, helpers reject matching resolved paths or existing filesystem
aliases (including hard links); the slimmer also rejects linked history files.
Keep the canonical, draft and history as distinct files. A collision stops the
operation without overwriting the input: do not retry unchanged paths or treat
the error as a completed handoff. These checks do not fence arbitrary writers.

The runtime guard reads at most 8 KiB for a pointer and 2 MiB for its canonical.
Larger or non-regular files are not eligible for veto. The slimmer shares this
bounded reader and stops instead of truncating an oversized input; report that
limit and retain the original. Never call this a successful slimming.

## Prepared-entry compatibility

Routine pointers hold Task or thread, Workspace, Canonical document and Updated at.
They locate the document for the direction-card hook and a successor and never
veto. `--seal`, used only for a confirmed handoff, adds Canonical SHA256 and
Handoff revision after a `--require-handoff` validation. Only a matching sealed
version can veto. Legacy three-field pointers behave like routine ones.
Never revive retired tasks or rewrite their pointers for migration.
Canonical changes or takeover invalidate the predecessor seal and release its
future compaction; this does not authorize using the stopped predecessor again.
