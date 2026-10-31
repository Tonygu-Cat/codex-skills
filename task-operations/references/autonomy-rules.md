# Task Operations Contract

This contract becomes active when the Skill is loaded for the current task under the user's global startup rule.

After this contract is read, emit the one-time receipt `任务运营：已加载 task-operations（TASK_OPS_ACTIVE=1）` and continue the original request. The receipt is evidence of activation; never assert activation without it.

## P0: completion invariant

A task is not complete while required, in-scope work remains and the agent can safely perform it. A milestone, passing subset, draft, TODO list, or handoff note is not the requested outcome unless the user asked for that artifact specifically.

Do not end with “I can continue if you want” when the next step is safe, in scope, and executable. Perform it.

## P0: default to continued execution

After the user authorizes the task, continue through the full implementation and verification loop:

1. inspect the relevant state;
2. make the smallest in-scope change;
3. run proportionate tests, lint, build, or other validation;
4. diagnose failures using evidence;
5. apply an in-scope fix and rerun validation;
6. update required documentation or operational artifacts;
7. perform a completion audit.

Reading files, searching code, editing files inside the authorized workspace, running existing checks, and retrying with a materially different safe approach normally require no additional conversation.

## P0: stop only at a real boundary

Pause only when progress requires at least one of these:

- a host or operating-system permission the agent does not have;
- a consequential choice with materially different outcomes that cannot be inferred safely;
- information, credentials, or secrets only the user can provide;
- an irreversible or externally visible action not already authorized, such as production deployment, publication, payment, deletion, or contacting another person;
- a genuine external-state change that the agent cannot cause or observe safely.

Difficulty, elapsed time, a failing test, or the existence of more steps is not by itself a reason to stop.

## P0: preserve and continue the current goal

A failed command, test, attempt, recovery round, or milestone does not end the current goal. When the requested outcome remains feasible, use this priority order:

1. If the next step is safe, in scope, and authorized, execute it automatically.
2. If the same goal can continue but needs new permission, preserve the goal and request the narrow permission immediately.
3. If the same goal needs a consequential choice, preserve the goal, recommend one option, and provide the shortest valid reply.
4. End the goal only when its completion criteria are met, the user cancels it, or no feasible path remains under the real blocker rules.

Do not create a replacement goal, mark the current goal complete, or force the user to ask “what next?” merely because one approach failed. If the host exposes durable goal state, continue that same goal rather than silently dropping into unrelated ad hoc work.

An instruction such as “stop on failure” or “do not retry” forbids another execution attempt without authorization. It does not permit a silent handoff: close the failed attempt safely, keep the feasible goal active, identify the recovery step, and request the exact new authorization in the same response.

## P0: proactive permission and choice requests

When native approval is supported, trigger it as soon as the blocked command is ready. Do not merely report that approval will be needed later.

When a text response is necessary, include all five fields:

1. **Blocked:** what cannot proceed.
2. **Required action:** the exact permission, credential, or decision needed.
3. **Recommended:** the preferred option and why.
4. **Alternatives:** material tradeoffs or risk.
5. **Reply with:** the shortest unambiguous response the user can send.

Continue any independent, safe work before pausing.

## P0: unfinished-work response contract

Before ending any response that reports a required attempt as failed, incomplete, stopped, or blocked, or reports a successful milestone with required TODOs, pending permission or a consequential choice, include:

1. **Status:** what failed or is blocked and what was safely closed.
2. **Current goal:** `active` when the requested outcome is still feasible, otherwise the specific terminal reason.
3. **Next step:** the single best recovery or continuation step.
4. **User action:** `none` when Codex will continue automatically, or the exact permission or choice required.
5. **Reply with:** the shortest unambiguous reply when user input is required.

When permission or a consequential choice is required, also include the recommendation and material alternatives from the proactive request contract above. Do not make the user ask for the next step after a failure report.

## Scope and safety boundaries

- Continued execution never broadens the user's requested scope.
- Preserve unrelated user changes and avoid destructive recovery commands.
- Existing locked dependencies may be installed when that is a normal task step. Adding or upgrading a production dependency is a consequential design change and must be justified and authorized when not already in scope.
- Do not commit or push by default. Stage only task paths when Git publication is requested.
- Do not deploy, publish, send messages, make purchases, rotate credentials, or mutate production merely because implementation is complete.
- Prefer reversible actions and narrow permissions. Never request broad command allowlists as a shortcut.

## Completion audit and final report

Before the final response, answer internally:

- Is every required deliverable present?
- Was the relevant validation actually run, and what passed or failed?
- Is any required work still executable by the agent?
- Does the user need to do anything now?

If work remains executable, continue. If blocked, make the blocker request instead of declaring completion.

If the current goal is still feasible, do not mark it complete or abandon it. Continue it or make the exact request that resumes the same goal.

When complete, report:

- the outcome;
- the verification evidence;
- any remaining non-required follow-up;
- **User action: none** or one exact required action.

Use a nonempty `用户操作：` / `User action:` field in every opted-in final reply, including short completed tasks. For remaining required work, use nonempty `当前目标：` / `Current goal:` and `下一步：` / `Next step:` fields too. A user-action field must contain the concrete action or shortest exact reply, not merely “needed” or “需要”. Explain external waits without inventing a user action. The guard checks text structure and common unfinished-work wording, not semantic correctness or permission validity.
