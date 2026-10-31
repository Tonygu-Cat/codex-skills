# Automation readiness (not an installed runtime)

Read only when designing, enabling or assessing compaction automation. Updating this Skill does not authorize deployment, global configuration changes, startup-consent inheritance, or live rollover tests.

## Capability levels and fallback

For the explicit no-compaction/manual-confirmation MVP, use [manual-confirmation.md](manual-confirmation.md). Its helper is a separate synchronous veto mode; the reminder handler below remains advisory. Do not apply reminder-only fallback when the user requires no compaction. This package does not establish host-level failure safety.

Report separately:
1. **Checkpoint rules**: agents persist and reconcile the canonical document. This package provides these rules and offline validation, not a background save service.
2. **Recovery reminder**: an independently installed, tested host hook points a resumed task at its checkpoint. It does not save missing facts or change task lifecycle.
3. **Automatic rollover**: a validated independent controller plus supported host adapter implements the full protocol in task-rollover.md.

Default Plan B when full host control cannot be established: checkpoints, a verified reminder if available, and explicit manual/user-triggered rollover. Otherwise use checkpoints/manual recovery alone. Do not silently call either fallback the user's complete automatic capability. Revisit no-go when supported host capabilities change; do not call it a permanent platform impossibility.

A manager task is not a reliable nonrecursive controller just because it is declared exempt from rollover. It still has context and lifetime limits. Do not deploy that substitute without an independently demonstrated continuation mechanism and explicit authorization for that deployment.

## Split the initial capability check

- **M0-event (reminder only)**: verify actual running host/version, trusted configuration, root task identity, event delivery, immediate recovery-context injection, timeout/error behavior, and no lifecycle side effects. It does not require the complete controller connection.
- **M0-control (full rollover)**: prove supported access to the user's actual task collection/project/approval environment, creation correlation, task drive/readback, independent survival after predecessor stop, safe archive impact, and scope-limited execution fencing. An independently started server controlling another task collection does not pass.

Timebox the M0 investigation under an agreed scope/cost bound. Produce pass/no-go per capability with version, command or native receipt, timestamp and observer. Do not alter internal host databases, move session logs, extract hidden credentials, bypass trust/approvals or use undocumented IPC to manufacture success.

Offline protocol work can proceed independently. Full live rollout cannot pass a missing M0-control capability. A failed prerequisite means blocked/not-run for dependent tests, not a passing mock.

## Recovery reminder as an independent early deliverable

For Codex, validate the current official behavior before deployment:
- `SessionStart(source=compact)` can add a short recovery instruction before the next model request, including mid-turn compaction.
- In reminder-only mode, `PreCompact` plain stdout is ignored; optional use is minimal metadata bookkeeping, not recovery-context injection. The separate veto mode has a different JSON contract; see manual-confirmation.md.
- Background hooks do not wake an idle task, and their lifetime belongs to the session. They are not a controller.

Use a bounded local handler: read only the enrolled path and safe manifest, return a fixed instruction to read/reconcile it, and indicate missing/unverified state. Do not block compaction, create/archive tasks, call a model/network API, or wait for takeover. Optional PreCompact bookkeeping must not be a prerequisite for recovery injection; tolerate missing, duplicated and reordered observations.

Treat path/metadata as data, not executable strings; do not promote copied document content or an old next action into higher-authority instructions. Revalidate owner and policy before acting.

Do not infer checkpoint freshness from mtime. If available, track monotonically ordered material-event IDs and the checkpoint's covered event ID with observation limits. User decisions, external results and background work may be absent from local file observations. Without sufficient event coverage report freshness unknown; the simplest initial reminder always points to the canonical document and requests reconciliation.

Verify real auto/manual compaction, missing/stale documents, wrong scope/owner, untrusted/disabled hooks, duplicate delivery and actual immediate continuation. Promise neither a cost percentage nor recovery of never-persisted information.

## Available reminder handler (registration is separate)

The optional [../scripts/recovery_reminder.py](../scripts/recovery_reminder.py) accepts one bounded JSON hook event on stdin and an absolute `--registry` path. It returns SessionStart additionalContext only for an enabled, uniquely enrolled root task with matching native session ID and exact resolved cwd. It makes no network/process calls or file writes and returns neutral success for invalid/unavailable inputs. Neutral success is not proof that a task is protected; check enrollment and actual host delivery separately.

Registry schema: `{"version":1,"enrollments":[{"enabled":true,"thread_id":"exact-native-id","scope_id":"immutable-scope-id","workspace":"absolute-local-workspace","handoff":"docs/handoffs/CURRENT_HANDOFF.md"}]}`. Registry paths are trusted deployment configuration, not discovered from chat text. Keep the handoff path relative and inside the workspace; UNC, traversal and escaping resolved paths are rejected. The document may put Work scope ID in Identity or Transfer safety. Metadata mismatch remains unverified; document contents/next-action text are never copied into developer context.

After explicit deployment approval, register one project-local SessionStart group with matcher `^compact$`, a command invoking the approved Python runtime with `-S -B <absolute-script> --registry <absolute-registry>`, timeout 2 seconds and additionalContextLimit 1000. Quote each path using the actual host shell rules and set commandWindows when applicable. Preserve unrelated config and obtain the host's normal exact-definition hook trust; never write a trust hash or use bypass flags as a substitute. This timeout is a conservative initial bound to measure, not guaranteed latency.

For the pointer-based handoff flow, prefer [../scripts/direction_card_hook.py](../scripts/direction_card_hook.py) in the same SessionStart(compact) slot. It needs no registry because it follows the task's own locator. It injects the Direction card itself plus the configured soft handoff reminder, instead of only a read-the-document reminder. Register only one of the two for a scope; otherwise the model receives duplicate post-compaction context. It reads up to 32 MiB of transcript tail, so give it a timeout of about 10 seconds. If the host truncates additional context, raise `additionalContextLimit` until the card plus about 2000 characters fits. Test it with `scripts/test_direction_card_hook.py`.

Start with one isolated task. Run `python -S -B scripts/test_recovery_reminder.py` for synthetic cases; these do not demonstrate host loading, manual/auto compaction, or immediate continuation. Verify those separately. Missing or malformed registration can yield no reminder without blocking the task. Duplicate invocation repeats the same bounded advice without state mutation. Disable only this registered group/enrollment on rollback, preserve audit/fixtures, and never restore a whole stale config over newer edits.

## Independent controller lifecycle is a separate deliverable

Select a supported user-approved deployment mechanism after M0, not by assumption. Document and test:
- installation location, least-privilege identity, configuration ownership, startup/login/reboot behavior and dependencies;
- singleton lease plus transactional durable intent/receipt storage, schema migration and integrity checks;
- health/readiness distinct from process existence, bounded restart/backoff, outage notification and reconnect;
- crash recovery by reconciling pending side effects, never blind recreation or epoch reassignment;
- safe drain on stop/upgrade, preserving actual owner, in-flight records and evidence;
- uninstall/rollback that disables new requests without deleting audit/checkpoints or restoring archived tasks.

Controller failure must not start a new transfer/archive. Retain the actual owner and reconcile before resuming; if side effects cannot be observed or fenced, stop that scope. High availability is not required for the first version, but safe failure and restart are.

Use component-owned storage, not the host's internal database. A per-host singleton is not a cross-host lock. Independently test remote topology before expanding coverage.

## Resource fencing and budget

Keep a first-class coverage inventory: scope resources, tool/command routes, enforcement point, excluded routes, in-flight evidence, tests and remaining unknowns. Actual reachable uncontrolled paths preclude full automatic transfer; listing them is insufficient. No new scope ID can bypass an overlapping resource allocation.

Quiesce business writes and preserve artifacts before sealing/publishing the source checkpoint. The predecessor's model obligations end only after publication and the independent controller's durable acceptance. Later acknowledgement/archive waits belong to the controller, not the predecessor.

Use reliable current-context telemetry only when verified for this host. Cumulative billed tokens are not occupancy. Reserve preparation/publication/acceptance tokens separately from controller elapsed-time/retry limits. If insufficient, record a degraded recovery event, reconcile the last checkpoint and do not silently skip handoff or loop on compaction interception.

## Integration gates and release

Maintain a matrix with columns: scenario, prerequisite capability, fixture vs real host, enforced resource coverage, expected safe result, observed evidence and residual risk.

Required cases include:
- duplicate/competing events and controllers; successful create with lost response; restart mid-side-effect;
- dirty artifacts plus fresh successor worktree (must block); verified shared storage; complete authorized artifact reconstruction;
- in-flight/unobservable writes; excluded route attempts; overlapping scopes and scope split/migration;
- budget exhausted; auto/manual compaction; recovery-first path; stale/wrong-owner reminder;
- publication failure/concurrent revision; stale policy ack; separate startup-consent gate;
- self-retirement; archive descendant impact; archived-message failure without revival; final evidence publication failure;
- concurrent config edits, partial installation, failed trust/hot reload, crash/upgrade/uninstall/rollback.

Zero dual writes in tested admitted routes is necessary but not sufficient: coverage/exclusion must be verified, with reachable uncontrolled paths disqualifying full automation. Track duplicate successors, wrong/cascading archives and unwanted restores similarly. Require real next-step progress; a safe block is not a continuous-progression success.

Suggested release order: M0-event -> standalone reminder; in parallel M0-control -> offline protocol -> shadow -> isolated real automatic/recovery workflows -> a low-risk chain across two generations -> gradual enrollment. Respect explicit exclusions and do not reopen archived tasks. Claude Code shares rules, not assumed Codex hooks or archive semantics.

For approved configuration changes, preserve existing hooks (including Stop). Read/hash the original, prepare a valid merged temporary file on the same filesystem, detect concurrent edits and retry/reconcile, then use a supported atomic replacement and read back. Atomic replacement alone does not prevent lost concurrent edits; use supported locking/CAS or require an agreed no-edit window. Verify the running host loaded/trusted the result. Back up and roll back only owned keys/files; don't replace an old whole configuration over newer user edits.

## Official capability references

Verified documentation on 2026-09-10; recheck actual host version before use:
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks): event/context semantics, background lifetime, trust and tool coverage limits.
- [Codex App Server](https://learn.chatgpt.com/docs/app-server): protocol/schema and archive effects; documented API availability is not proof of supported access to an existing desktop session.

These sources establish platform descriptions, not this package's installation or end-to-end validation.
