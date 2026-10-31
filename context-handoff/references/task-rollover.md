# Task rollover

Read this reference before any lifecycle operation or message to a predecessor. These are agent procedures, not an installed controller.

## Manual-paste V1 routing exception

If the user explicitly chooses creating a new task and pasting the handoff line as confirmation, follow [manual-confirmation.md#manual-paste-v1](manual-confirmation.md#manual-paste-v1) instead of the creation/transfer/archival sequence below. Check the exact predecessor's activity, recorded background work and workspace read-only, then let the new task read and acknowledge the checkpoint. Record unavailable observations as unverified, with their limits; unknown observations alone do not block this manual takeover or require a user question. Ask one concrete question only for an observed anomaly, pausing the affected shared writes until it is resolved. Do not add sandbox write-range certification, a controller/epoch protocol, or compulsory archival to that mode. The user retains the predecessor but stops using it. The sections below, including their unknown-in-flight and isolation gates, remain unchanged for other explicitly authorized rollover modes; they do not override this manual-paste V1 exception.

## Authorization, trigger and mode

If rollover follows a pre-compaction veto, first apply [manual-confirmation.md](manual-confirmation.md). Do not require another model turn in the stopped predecessor to finish missing work, count a warning as native stop evidence, or let the successor resume unprotected. Human confirmation authorizes handoff only within its stated scope, never compaction.

A current user request or governing project rule must authorize one same-chain successor and predecessor archival. Standing same-chain authorization is sufficient; loading a Skill or publishing a checkpoint alone is not. Respect separately applicable new-task consent gates. A successor reading a handoff is not another rollover trigger.

Creation and archival are coupled stages, not an atomic operation. Temporary visibility of two tasks is acceptable; overlapping execution of the transferred resources is not. Only a newer explicit instruction can retain a predecessor unarchived. Retention still does not authorize parallel execution.

Use manual/user-triggered rollover when supported native operations and a surviving closure actor are available. Automatic rollover additionally requires the independently validated controller and host gates in [automation-readiness.md](automation-readiness.md). Do not infer that a tool available inside the current task is callable by a background hook.

## Scope identity and durable boundary

- At enrollment, confirm the business/resource boundary under the user's actual request; generate and persist an opaque work scope ID, rather than asking the user to invent an ID. Never derive identity from a title or an incomplete task list.
- Keep that ID immutable across normal same-scope handoffs. Record canonical repository/worktree locations and external resource identifiers, scope approval reference and resource-overlap checks. Different IDs do not make overlapping resources independent.
- Refinements within an approved boundary update its description/policy version. A change of ownership, resources or permission boundary requires an explicit scope migration/split: quiesce overlapping work, close the old scope allocation, register the new scope(s), recheck permissions and conflicts, and preserve lineage. Do not call this an ordinary rollover or silently reset the old lock.
- Rollover generation increments once per new direct-predecessor boundary; retries keep it. Owner epoch increments on actual execution-owner changes, not on lease expiry. A new scope starts its own generation/epoch only after the prior allocation is closed.
- Persist a boundary ID and one successor slot keyed by host, project, scope, predecessor ID and generation. Write creation intent before calling the host and retain its returned setup/client ID and real task ID.
- A lost create response is `unknown`, not failure permission to retry. Reconcile using exact IDs or supported request correlation. If no reliable reconciliation exists, stop in `CREATE_OUTCOME_UNKNOWN`, preserve the predecessor and do not create another task. Titles never prove identity.

For manual operation, the canonical record plus native receipts may serve as a serialized ledger. An automatic controller needs its own crash-safe transactional ledger; this package supplies no such runtime.

## Preserve working state before readiness

A digest identifies content but does not preserve it. Inventory all task-required tracked changes, untracked/binary files, relevant ignored artifacts and external in-flight work. Do not force commit, stash, clean, discard or publish business code under documentation-only permission.

Record `Working tree disposition` (working_tree_disposition):

- `clean`: source revision is reachable by the successor and all required non-Git artifacts are separately available.
- `committed:<sha>`: an already authorized commit exists and is readable from the target; a local-only hash is not proof of target access.
- `patch:<published-ref>`: explicitly authorized artifact storage, manifest/base revision and tested reconstruction exist. Ordinary text patches may omit binary/untracked files. Never assume the documentation repository permits business-code publication.
- `shared-worktree-verified`: both task environments resolve to the same actual worktree/storage identity, verified source state and necessary artifact manifest. Equal path strings on different hosts are not proof. Verify the host will preserve access after predecessor archival; share only after business writes are quiescent.
- `blocked` or `unverified`: state cannot yet be transferred safely.

Default: unpreserved dirty artifacts plus a new successor worktree blocks readiness, takeover and archival. Keep the predecessor environment intact and ask for the narrow preservation choice; do not force a commit-or-discard choice. A host unexpectedly providing a fresh worktree must trigger re-verification, not downgrade the manifest check. Record destination reconstruction/shared-access evidence, not just source hashes.

## Execution isolation and evidence

Before ownership changes, drain or reconcile actual in-flight side effects and prevent the old owner from issuing new overlapping writes. An idle UI, expired lease, owner field, agent promise, or missing list entry is not proof. Cover existing shell sessions, background processes and external actions where they can still affect the scope.

Maintain a coverage inventory identifying each write route/resource, enforcement point, test/observation, and excluded or unknown routes. Reachable uncontrolled routes block automatic transfer; exclude/disable them or use a separately verified operator-controlled handoff. Merely documenting the hole does not close it. Unknown in-flight status blocks transfer in either mode. No finite test suite proves universal zero dual writes.

Append [../assets/rollover-safety-template.md](../assets/rollover-safety-template.md) as `## Transfer safety` before rollover. Fields describe actual evidence:
- `Execution mode`: `manual` or `automatic`; reminder-only is not rollover.
- `Successor workspace`: `new`, `shared`, or `unknown` until resolved.
- `Create outcome`: `not-started`, `pending`, `confirmed`, `unknown`.
- `Write isolation`: `verified` or `unverified`.
- `Uncovered write paths`: `none`, `excluded`, `present`, `unknown`; `excluded` requires actual exclusion evidence.
- Evidence fields use native results, manifest/receipt references and observation time; `pending`/`unknown` honestly represent incomplete work.
- `Archive executor`: exact surviving actor ID, or `pending-successor` before creation only. The predecessor cannot own its own archive-and-post-archive closure.
- `Controller evidence`: required for automatic mode; otherwise `not-applicable`.

Use `validate_handoff.py <path> --require-lifecycle --require-transfer-safety` before the creation/transfer boundary. Old documents remain readable, but missing new fields are not permission to skip readiness. PASS validates declarations only, not evidence authenticity, complete coverage or enforceability.

## Task lifecycle record

Keep exact task IDs (no title annotations) in Identity. Roll the direct pair forward only at a genuine next boundary; preserve older pairs in dated history.

Maintain the six `## Task lifecycle` fields:
- `Policy source`: latest applicable user/rule reference and date.
- `Predecessor disposition`: `not-applicable`, `archive-after-takeover`, or `retain-by-explicit-request`.
- `Predecessor observed state`: `not-applicable`, `unknown`, `active` (unarchived, not necessarily running), or `archived`.
- `Archive verification`: `not-applicable` before rollover, otherwise `pending` or timestamped native evidence for the exact predecessor.
- `Successor policy acknowledgement`: `not-applicable` before rollover, otherwise `pending` or a response bound to the latest policy, owner and this boundary. Sent/queued is not acknowledgement.
- `Result destination`: `current-task-user`; no mandatory predecessor relay.

## Transfer sequence

1. Resolve authority, scope, environment and the surviving closure actor. Set one boundary/generation, record intent, preserve artifacts, quiesce business writes and verify actual isolation. Prepare the final source checkpoint and safety record before declaring `handoff-ready`. Unresolved user approvals/answers must be recorded, not stranded in chat.
2. Validate and publish only the authorized handoff paths to the specified documentation repository/ref. Follow branch/PR rules; verify successor-readable publication. In automatic mode, the independent controller must durably accept the checkpoint before the predecessor's model obligations end. Preparation, quiescence, publication and that local acceptance are the predecessor's token budget; later waits are controller time/retry budgets. Waiting elapsed time alone is not context consumption.
3. Use the supported native task creation operation once, in the actual saved project/host and host-prescribed environment. A new task is not a request to clone the old full conversation. Preserve working state through supported options, never assume a fresh worktree contains dirty files. Record the host's exact IDs; pending/unknown outcomes prevent another create.
4. Give the successor the boundary ID, scope ID, predecessor ID, canonical path/revision/hash and readable ref, source/environment/manifest expectations and latest authority. Instruct it to use this Skill, verify those facts read-only, report its own exact task ID, next action and discrepancies, and wait for a verified transfer record. It must not edit business state or the canonical handoff during this check.
5. Accept only a response bound to this boundary, checkpoint, current policy and verified target artifacts. If any discrepancy, consent gate or required publication remains unresolved, do not transfer or archive. Preserve the actual existing owner; after transfer failures never restore dual execution.
6. Transfer execution ownership only after real quiescence/isolation. For automatic mode the controller changes owner/epoch transactionally in its ledger, then the successor becomes the sole canonical writer and publishes the transfer evidence. The predecessor performs no later model step. For manual mode the serialized coordinator records the acknowledged transfer and sends it before retirement; if that coordinator is the predecessor, this is its final canonical write and it delegates all closure to the verified surviving actor. The successor rereads the transfer record before business writes.
7. The surviving actor validates archive impact and archives only the exact predecessor. Do not assume host archive operations exclude descendants: ensure the successor/unrelated tasks cannot be included. If the host cannot establish safe scope, block archival. Under a newer explicit retention exception, retain the predecessor unarchived but non-executing.
8. By exact ID, the surviving actor verifies predecessor disposition and successor availability. The successor records closure, removes stale active instructions, runs `validate_handoff.py <path> --require-closed-rollover`, and publishes as required. It reports directly to the user and performs the next real work step, or identifies a genuine business/permission blocker; either way the report ends with the progress-contract closing block from SKILL.md. Transfer-ready, archive requested, or successful offline checks alone are not completion.

Make the unique successor entry point visible using the host's required format. Never require the predecessor to return from self-archival to read state, send results or finalize evidence. If no surviving authorized actor/tool exists, preserve the predecessor and use the explicit fallback; do not silently leave an unverified handoff.

## Changed policy and failures

A later user policy replaces obsolete current instructions, not just an appended note. Forward the exact new source and target IDs to the live successor; its acknowledgement must match the changed policy. The current document owner performs the update. If the predecessor is archived, do not reopen it for coordination.

An archived-target message failure ends that route. Report in the successor, not by unarchiving, restarting or creating a replacement task. Restoration requires a newer explicit request for that exact archived task and a fresh ownership reconciliation; old retention wording and rollover permission are insufficient.

Before archival, failed preservation, creation, setup, publication, policy acknowledgement or takeover blocks archival. After successful archival, a reporting/sync failure is pending closure, not permission to revive the predecessor. Do not delete tasks, force-push, reset generation on retry, or let the successor immediately roll over merely because it loaded a handoff.
