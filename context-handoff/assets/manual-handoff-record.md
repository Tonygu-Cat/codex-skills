# Manual handoff record

Append this as a section of the existing canonical handoff, not a second canonical.
These fields are a human-maintained record, not executable state or permission.
Reuse the same boundary and successor slot on repeated notices.

- Boundary ID: pending
- Work scope ID: pending
- Generation / owner epoch: pending
- Current host/project and exact predecessor ID: pending
- Guard enrollment ID and script/config version: pending
- Guard request marker and observation time: pending
- Native stop / no-compaction evidence: unverified
- Latest user policy and handoff confirmation: pending
- Checkpoint path, revision, hash and readable publication ref: pending
- Covered material-event boundary / known uncovered tail: unverified
- Working tree disposition and target-access evidence: unverified
- Quiescence / in-flight / isolation evidence: unverified
- Single create intent and outcome: not-started
- Unique successor slot / native ID: none
- Startup consent gate result: pending
- Successor read-only acknowledgement / next action: pending
- Successor guard registration and runtime evidence: unverified
- Ownership transfer evidence: pending
- Surviving archive executor: pending
- Exact predecessor archive / successor-available evidence: pending
- Current permitted next action: review only; no creation, archival or business by this template

## Phase-specific gates

Requirements below are cumulative. Only evidence required by the current phase
must be concrete; later results remain pending. Never prefill expected success.

1. **Before creation:** confirm boundary/scope/generation/current host and predecessor,
   guard version/marker and native stop evidence, current user handoff authority,
   readable checkpoint and material-event coverage, preserved source artifacts
   and a feasible target-access plan, plus source quiescence/isolation.
   Record one creation intent before calling the host. The outcome may then be pending;
   an unknown outcome blocks retries. The unique successor ID, startup/acknowledgement,
   target readback, successor protection, transfer result and archive result may
   still be pending/unverified/none. Select the surviving archive executor plan;
   pending-successor is allowed until the real successor is known.
2. **Before ownership transfer:** creation must be confirmed with one exact successor
   ID; resolve its startup consent, read-only acknowledgement bound to the current
   checkpoint/policy, actual target artifact access, guard registration/runtime
   evidence, and a concrete surviving archive executor. Recheck source
   quiescence/isolation. Ownership transfer and archive results remain pending
   and do not block beginning this phase's authorized transfer.
3. **Before archival:** record completed ownership transfer and the successor's
   readback, confirm the exact predecessor-only archive impact and the surviving
   actor's authority. The archive/successor-availability result remains pending
   until archival and subsequent native readback actually occur. If transfer
   evidence is missing, do not archive.
4. **Before closure:** require exact predecessor disposition and successor-available
   evidence, a consistent sole owner, final validation and required publication.
   A requested archive is not an archive result. Failed closure must not restore
   dual execution or cause a second creation.

Missing requirements for the current phase block only its next action.
Fields not yet due do not block earlier phases; all safety and authority gates
still apply. A newer explicit retention policy uses the rollover protocol's
verified retained-but-nonexecuting disposition, not fabricated archive evidence.
Use the existing lifecycle and Transfer safety sections and validator as well;
this supplemental record does not replace their gates.
