---
name: context-handoff
description: Keep long-running project work moving across turns, context compaction, session changes and agent changes. While active, end every work turn by telling the user the next step, who owns it and exactly what they must do (with a ready-to-send reply when approval or a choice is needed), so they never have to ask "下一步做什么" or "我要做什么"; keep going instead of stopping when the next step is already authorized. Maintain one canonical, versioned handoff so a fresh agent can resume without re-deriving decisions; when an authorized long-task rollover is needed, create a successor Codex task and archive its predecessor only after verified takeover. Use for multi-stage, long or continuity-risky project tasks; not for one-off questions, a standalone status summary, or replacing the project's specifications and issue tracker.
---

# Context Handoff

This Skill keeps long project work moving and recoverable. It maintains two outputs for two readers:

- **The closing block of every work turn, for the user:** what happens next, who does it, and exactly what the user must do, if anything.
- **One rolling handoff document, for the next agent:** conclusions, rationale, observed state and exact next actions, so work resumes without the old chat. Do not copy the conversation transcript.

Both matter. A turn that carefully updates the handoff but leaves the user to ask "下一步做什么" has missed the reason this Skill exists: the user should learn the next step from you, not have to extract it.

## Progress contract (every work turn)

Before ending a turn on a long task, decide which case applies:

1. **The next action is already authorized, in scope and safe:** do it now instead of ending the turn. Checkpoint if needed and keep going. Stopping only to report progress and wait for "继续" costs the user a round trip and adds nothing.
2. **The next action needs the user** (approval, a choice, information, a manual step, or forwarding something to an external party): end with the closing block, including the exact text they can send.
3. **Waiting on something external** (CI, a reviewer or PMO, another task, a scheduled run, a vendor): end with the closing block: what you are waiting for, who triggers it and how, and what you will do when it arrives. If nothing is already in motion, it is not waiting: someone has to act, so either act yourself or give the user the exact message and recipient. Before handing a problem to an outside party, exhaust what you can check yourself with the available tools and documentation.
4. **The requested outcome is complete:** state what proves it and write `当前目标：已完成` and `用户操作：无需`. If the handoff lists further planned stages, name the next one and the reply that would start it. Proposing a stage is not starting it, so this does not conflict with scope limits.

End the message with this block, in the user's language:

```text
**当前目标**：<the goal still in progress> | 已完成（<what was completed>）
**下一步**：<exact next action>（由我 / 由你 / 由 <owner> 执行）| 无（<next planned stage, if any>）
**用户操作**：无需（<I will continue / waiting for X>）| <one exact action>
> <ready-to-send reply or authorization text with scope, limits and stop conditions, pasteable unchanged; omit when no reply is needed>
```

- Always write all three labelled lines, even when complete. The task-operations Stop hook checks these labels, and safety notes such as "未部署" count as pending work there, so a missing line costs an extra correction round.
- Write the reply text now: the same text you would give if the user asked "下一步做什么". Recommend one option; name material alternatives in one line.
- `用户操作：无需` must be literally true: the work will progress without the user. If progress depends on anyone, name who does what and when.
- Do not end a turn on an announcement such as "我现在去做 X". Do X, then close with the block; if X failed or was interrupted, say so in the block.
- Give one next step, not a menu. If the user must do several things, give the first and say what follows.
- Handoff or sync status gets at most one short line before the block; it is never the closing line.
- The first item of `Next exact actions` and the `下一步` line must agree on action and owner.
- If a hook or guard ended the previous turn before you could reply, open your next reply with this block.
- Heartbeat automation turns (the host sent a `<heartbeat>` message) are the exception: reply only in the host's `<heartbeat>` format — `DONT_NOTIFY` when nothing changed, `NOTIFY` for changes, failures or missing inputs — and put the next step and user action inside `<message>` when notifying. Do not append the closing block; it would break the host's quiet/notify decision.

Scope, safety and rollover rules decide whether you *execute* a step. None of them is a reason to leave the next step or the user action unstated: "完成即停止" means stop executing, not stop guiding.

## Compaction, direction and handoff

Compaction is normal: Codex compacts automatically and the task keeps working. What must survive it is the direction, not the transcript. Three layers keep it:

1. **Direction card.** The canonical document's `## Direction card` holds the stable goal, done-when, current phase, scope, non-goals and fixed user decisions, within `direction_card_max_chars` (default 1500). Change it only when the user changes direction, and log that in Decisions. Volatile progress belongs in `Current state` and `Work in progress`.
2. **Re-injection after compaction.** Once the canonical exists, write this task's locator: `python <skill-root>/scripts/write_task_pointer.py --canonical <absolute canonical path>` (it uses `CODEX_THREAD_ID` and the current workspace, and never stops compaction). Where the SessionStart(compact) hook `scripts/direction_card_hook.py` is deployed, it re-injects the card after every compaction. On a `CONTEXT_HANDOFF_DIRECTION_V1` block, check the next action against the card before continuing.
3. **Compaction prompt (local compaction only).** `assets/compact_prompt.md` asks the summary to copy the card verbatim. On 2026-09-27 an isolated test showed that Codex's server-side compaction ignores a custom `compact_prompt`, so this layer applies only to local compaction. Layers 1 and 2 do not depend on it.

**When to hand off.** Hand off at a phase boundary, when the phase's exit criterion is met and the next phase is substantial, or when the user asks. The hook's reminder is only a fallback. It fires by default when this thread has compacted 10 times, or when the previous compaction left 25% or more of the window in use. On a reminder, finish the current step, then recommend a handoff in the closing block. If that reminder goes unanswered, the same script, registered as a UserPromptSubmit hook, asks for a red bold first line (`CONTEXT_HANDOFF_ESCALATION_V1`). It does this on the user's next own turn, then again after every `handoff_reminder_repeat_turns` of the user's own turns (default 4), counted from our last reply that carried the line. Automation turns and messages relayed from other tasks do not count. A user message that mentions the handoff (交接) answers the reminder and pauses the line until the next compaction reminder; a sealed handoff stops it. Write that line exactly as given. Start the handoff only after the user confirms. Never start one on your own or on a heartbeat turn.

**How to hand off**, once the user confirms:

1. **Wrap up.** Finish or cleanly pause the current step; leave no half-written file. Stop background jobs this task started. If one must keep running, record why and how to check it. Pause any active goal so it cannot auto-continue.
2. **Record.** Update `Current state`, `Work in progress`, `Next exact actions` and `User action now`. `Work in progress` covers:
   - unfinished work;
   - background jobs: command, PID, output path, and how each one ended;
   - workspace changes from `git status`;
   - external apps or sessions left running, and who owns them.

   If the document is over the slimming threshold, slim it first.
3. **Seal.** Run `validate_handoff.py <path> --require-handoff`, then `write_task_pointer.py --canonical <path> --seal`, which prints the handoff line. The writer refuses while this task's Codex goal is still `active`: a sealed task is stopped at every compaction, and an active goal would keep retrying into that stop. Any later edit releases the seal; re-seal after editing.
4. **Reply.** Start the reply with `CONTEXT_HANDOFF_READY` and give the handoff line. Close with the block asking the user to paste the line into one new task's chat composer in the same project (not PowerShell), and not to use this task again. Start no new work here. If the task truly needs no continuation, say why instead.

While the sealed revision is unchanged, the PreCompact guard stops this task. Every other task compacts normally, including any task whose entry is missing, stale or unverifiable. The successor verifies the handoff itself; see [manual confirmation](references/manual-confirmation.md#manual-paste-v1).

**Settings and slimming.** Thresholds live in `settings.json`, not in these instructions. Read the effective values with `scripts/handoff_config.py` (or its explicit `--config ABS_PATH`), and use the same source for the hook, validator, slimmer, pointer writer and guard. Read [thresholds and safe slimming](references/budget-and-slimming.md) before changing settings or slimming. Changing settings does not authorize installing or trusting hooks.

The default slimming triggers are 60 KiB of UTF-8 text or 80 non-empty `Current state` lines, both configurable. Default targets are 40 KiB and 60 lines; smaller configured limits reduce the targets accordingly. Follow the safe slimming workflow in the linked reference:

1. Read the entire original.
2. Draft a sufficient concise version.
3. Preserve the full original bytes beside it.
4. Validate, then publish with `scripts/slim_handoff.py`.

Keep current authority, goal, blockers and next action in the main document, with history and evidence indexes. Slimming never changes the Direction card. The helper cannot certify semantic completeness, so inspect the draft rather than mechanically truncating it.

## Capability boundary and routing

When the user chooses **manual-paste V1** (create one new task and paste the handoff line as confirmation), use [manual confirmation](references/manual-confirmation.md#manual-paste-v1) as the complete mode-specific workflow. The predecessor is the task named in that line; the user's paste commits not to use it again. Check its activity, recorded background work and workspace against `Work in progress` read-only, by yourself. Record unavailable observations as `unverified`, with their limits; missing observations alone do not block this manual takeover or require a user question. Ask one concrete question only when you observe an actual anomaly, and pause the affected shared writes until it is resolved. Do not require successor sandbox-write-range certification, a controller, automatic creation/transfer, or archival for this mode. Preserve the progress contract above.

For a user requiring no compaction, read [manual confirmation](references/manual-confirmation.md): this package provides a synchronous veto helper and a manual handoff workflow, not a complete host guard or task controller. Separately authorized user-level `--all-sessions` and legacy exact-ID deployment both stop only tasks with validated version-sealed entries; invalid or unverifiable entries are released. Verify actual loading, normal trust and host behavior; the Skill alone does not establish runtime protection or guaranteed zero compaction.

This package supplies instructions, templates, offline checks and optional read-only hook scripts (direction card, recovery reminder, pre-compaction guard). It does **not** register or trust a hook, run a controller, or prove automatic task continuation. Loading it is not deployment.

- Ordinary checkpoints and recovery: use this entrypoint and the main template.
- User-approved continuous checkpoints with an existing veto: read [references/checkpoint-with-guard.md](references/checkpoint-with-guard.md). This is a risk-reduction mode, not strict no-compaction; it preserves existing registrations without expanding them.
- Authorized task creation, takeover or archival: first read [references/task-rollover.md](references/task-rollover.md), including scope, artifact preservation and execution fencing.
- Designing, enabling or assessing compaction automation: also read [references/automation-readiness.md](references/automation-readiness.md). Keep checkpointing, recovery reminders, pre-compaction veto and automatic rollover separate in status reports.
- Explicit no-compaction / human-confirmed handoff: read [references/manual-confirmation.md](references/manual-confirmation.md). Do not replace this request with post-compaction recovery. Await separate deployment and live-verification authority.

If independent host control is unavailable, the fallback is checkpoints plus manual/user-triggered rollover; add recovery reminders only after their separate deployment and verification. Do not silently substitute this fallback for a user's full-automation objective. Do not build a recursive chain of manager tasks or enable hooks while merely updating/using this Skill.

## Invariants

- Persist material state incrementally; do not wait for a final "about to compact" event. Strict no-compaction is an acceptance requirement when requested, not a guarantee from loading this Skill. Verify actual host interception and failure behavior before claiming protection; never promise perfect summaries or recovery of unsaved facts.
- Maintain one canonical handoff for the active project. Update it in place; do not create a new snapshot for every compaction. Git history preserves superseded revisions.
- Treat verified repository and tool state as stronger evidence than either the handoff or conversation memory. Reconcile discrepancies before continuing.
- Keep the current document sufficient to resume work without the old chat. Preserve decisions and evidence, but replace stale summaries and remove redundant narrative after the replacement is safely versioned.
- Within the same instruction authority, the latest applicable user decision supersedes older prompts and handoff instructions. Observed task state is evidence, not permission to change it: an archived predecessor must not be restored merely to send a result or obey an obsolete "keep the old task" instruction.
- After takeover under the selected mode's rules, the successor is the sole execution and handoff-writing owner for the transferred scope and reports directly to the user. For manual-paste V1, apply the read-only checks and unverified-observation handling above, without claiming OS-enforced isolation or treating unknowns as verified facts. Automatic transfer still requires actual quiescence and scope-limited write isolation; unknown in-flight operations or uncontrolled write paths block it.
- Preserve necessary artifacts, not just their hashes. Unpreserved dirty state plus a fresh successor worktree blocks transfer and archival. Do not manufacture a clean state through unauthorized commits, stash, cleanup or upload.
- Task rollover permission does not override a new-task startup consent gate. Inherit task-operations consent only if a separate applicable rule explicitly authorizes chain-level inheritance; otherwise respect the gate and report the wait.
- Never store secrets, credentials, private keys, access tokens, raw sensitive data, or large logs. Record a safe path, run ID, URL, commit, or concise redacted result instead.
- These invariants and the referenced safety gates control state changes and lifecycle actions. They never suppress the closing block: a blocked, paused or guarded turn still tells the user the next step and their exact action.

## Resolve the canonical document

Use this order:

1. Follow an explicit handoff path or documentation-repository instruction from the user or project instructions.
2. Reuse an existing handoff whose identity matches the active project.
3. Discover a configured documentation repository from project files, Git remotes, or an existing local clone. Do not guess that a similarly named repository is the target.
4. If no publication target is discoverable, create or update a local draft at `docs/handoffs/CURRENT_HANDOFF.md` in the project and continue safe work. Ask once for the exact GitHub documentation repository and branch when publication becomes the next boundary.

Never overwrite another task's canonical handoff merely because it uses this default filename. After creating or adopting the canonical, write this task's locator with `scripts/write_task_pointer.py` (see [Compaction, direction and handoff](#compaction-direction-and-handoff)). One locator points to the existing canonical document; it is not a second checkpoint. Missing write authority or an unverifiable identity is a reported preparation gap, not permission to alter another scope.

When creating the document, copy [assets/handoff-template.md](assets/handoff-template.md) and fill every placeholder, including the Direction card and Work in progress. Record both the source repository and the documentation repository so a future session cannot confuse them.

## Lifecycle

### Start or resume

Before substantive work on an existing long task:

1. Read the entire canonical handoff.
2. Inspect the current source branch, commit, task-related working-tree changes, relevant artifacts, and any stated blocker or test result.
3. Reconcile drift, including the latest lifecycle instructions and exact predecessor/successor IDs when a rollover exists. Read [references/task-rollover.md](references/task-rollover.md) before any lifecycle action or attempted message to a predecessor. Label facts that cannot be rechecked as `unverified`; never silently convert old intent into current fact.
4. Resume from `Next exact actions`: do the first still-valid action if it is yours and authorized; if it belongs to the user or an external party, tell the user with the closing block. Then update the timestamp, source commit, status, and revision log.

### Update checkpoints

Update the handoff immediately after any material event:

- scope, acceptance criteria, constraint, decision, or rejected approach changes;
- files, commits, migrations, configuration, or external resources change;
- a test, build, review, deployment, or investigation produces evidence;
- a blocker, permission requirement, risk, or user-only choice appears or clears;
- a background job starts or ends, or work pauses mid-step (update `Work in progress`);
- work is about to wait, delegate, switch agents, end a session, or enter a context-heavy phase;
- the host signals compaction or the conversation has become long enough that compaction is plausible.

Write observed results, not expected results. Keep `Current state` and `Next exact actions` current; append stable decision and evidence entries with dates or identifiers. Timestamp or file mtime alone does not prove freshness. If material events are tracked, record which event sequence the checkpoint covers and the observation limits; otherwise mark freshness unverified where it matters.

In `Next exact actions`, mark each action's owner (`agent`, `user`, or a named external party) and keep `User action now` and `Ready-to-send reply` current. After compaction or rollover they let the resuming agent tell the user what to do without re-deriving it. Write the checkpoint before composing the closing block so both carry the same next action.

When an instruction changes, replace its obsolete form in `Current state`, `Scope and constraints`, permissions, `Next exact actions`, and `Resume protocol`. Do not stack competing "current" versions. Keep necessary history only in dated decisions or the revision log, explicitly marked `superseded` with the replacement decision. Notify an affected live successor of lifecycle-policy changes and obtain its acknowledgement; see the rollover reference for the closure protocol.

### Close a checkpoint before a handoff or reset

Before a deliberate handoff or reset:

1. Reinspect the repository and relevant external state.
2. Ensure the document captures the Direction card, objective and completion criteria, current state, work in progress, scope, decisions with reasons and rejected alternatives, changed artifacts, verification evidence, blockers and permissions, the first exact resume action with its owner, and any pending user action with its ready-to-send reply.
3. Make paths, branch names, commit IDs, commands, run IDs, and owner/action boundaries concrete.
4. Run `python <skill-root>/scripts/validate_handoff.py <handoff-path> --require-handoff` and fix every error. For manual-paste V1, do not add automatic-transfer certification. Other authorized rollover modes also use `--require-lifecycle --require-transfer-safety`. A `PASS` checks document structure and declared field consistency only; independently review the evidence required by the selected mode.
5. Synchronize the validated revision to GitHub when authorized.

### Roll over to a successor task

When the current user or project instructions authorize moving the work into a new task, read [references/task-rollover.md](references/task-rollover.md) and follow it. Loading this Skill or writing a checkpoint alone does not authorize task creation or archival.

For manual-paste V1, stop at the verified successor's direct report and retain the stopped predecessor; do not create or archive tasks automatically. The following creation/archival requirements apply only to other explicitly authorized rollover modes.

In those other modes, creation and archival are coupled stages, not an atomic transaction. Keep one durable boundary record and at most one successor. Verify source preservation, actual takeover and ownership transfer before archival. Required publication or uncertain creation outcomes block archival. Assign archive execution and post-archive verification to an actor that survives predecessor retirement; never require a predecessor to finish closure after archiving itself.

When archival is part of the explicitly authorized mode, do not finish at "archive requested": verify the exact predecessor is archived and the successor remains available. A later policy change must reach the successor and replace stale canonical instructions. Never unarchive the predecessor without a newer explicit user request to restore that exact task.

### Recover after compaction or in a successor task

After compaction in the same task, the Direction card arrives with the hook. Re-read the canonical's `Current state`, `Work in progress` and `Next exact actions`, not the whole document, unless something does not fit. Re-reading everything after every compaction refills the context you just freed. A successor task reads the entire handoff before taking further task action. Verify project/scope identity, current owner, source branch/commit, preserved artifacts, unresolved blockers and checkpoint coverage. Missing or stale facts require safe reconciliation, not invented history. Reuse an existing rollover boundary/successor; a retired predecessor must not resume business writes. Record any already-compacted fallback as recovery/degradation, not successful pre-compaction rollover. Then apply the progress contract: continue the first still-valid authorized action, or give the user the closing block using the handoff's `User action now` and `Ready-to-send reply`.

## GitHub synchronization

- Publication is authorized only when the current task or project instructions explicitly require handoff commits/pushes. A statement such as "publish every handoff for this task" authorizes only this handoff path and target; do not generalize it to other repositories or tasks.
- Follow the documentation repository's branch, commit, review, and pull-request rules. Stage only the handoff and any explicitly required handoff index; preserve unrelated changes.
- Use a focused message such as `docs(handoff): update <project> continuity state`.
- Never force-push. If the remote advanced, fetch and reconcile concurrent edits without discarding either contributor's material facts.
- After pushing, verify that the intended remote branch contains the pushed commit. If synchronization fails, keep the validated local revision, record the exact failure and safe retry point, and do not claim that GitHub is current.
- If publishing requires approval, credentials, a repository choice, or an irreversible policy decision, finish independent local work first and then request the narrow missing action.

## Quality check

The handoff is ready only when a fresh agent could answer all of these from the document and repository alone:

- What outcome is required, and what proves completion?
- What is true now, and which statements remain unverified?
- What changed, why, and which alternatives were rejected?
- What evidence passed or failed, using which exact revision or run?
- What is blocked, who can clear it, and what permission is still valid?
- What is the first exact action to take next, followed by the next few dependent actions?
- Who owns each next action, what must the user do now (or nothing), and what exact reply would unblock the next step?
- If a rollover occurred, did the successor prove takeover before the predecessor was archived?
- Does the current owner know the latest archive policy, report directly to the user, and have no stale instruction to revive or relay through the predecessor?

Apply the same test to every turn-ending message: could the user act on it without asking a follow-up question? If not, add or fix the closing block.

Do not mark a task complete merely because its handoff is current. The handoff records delivery state; it does not replace delivery.
