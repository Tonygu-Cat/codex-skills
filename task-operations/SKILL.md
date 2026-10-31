---
name: task-operations
description: Apply user-approved task operating rules that keep work advancing to verified completion, surface required permissions or consequential choices proactively, and make remaining user actions explicit. Loaded explicitly by the user's global startup rule for tasks that edit files or run multi-step work, unless the user declines it for the current task.
---

# Task Operations

The user's global AGENTS.md startup rule is the standing opt-in: it loads this Skill for tasks that edit files or run multi-step work. Do not load it for one-off questions or simple status checks, or when the user declines it for the current task.

After reading the operating contract, emit this activation receipt once and continue the user's original request in the same turn:

`任务运营：已加载 task-operations（TASK_OPS_ACTIVE=1）`

Never claim that the Skill is active unless the contract was actually read in the current task. Do not repeat the receipt after context compaction.

## Operate the task

1. Read [references/autonomy-rules.md](references/autonomy-rules.md) and treat it as the authoritative operating contract for the rest of the current task.
2. Keep the user's requested outcome, scope, and safety constraints fixed. Authorization to continue does not authorize a broader objective.
3. Continue safe, in-scope work while a meaningful next step remains. Inspect, edit, validate, diagnose failures, apply in-scope fixes, and rerun validation without asking the user to prompt each step.
4. Preserve the current goal across failed attempts. If the goal remains feasible, continue it automatically when authorized; otherwise keep the same goal active and proactively give the exact permission, choice, or reply needed to resume it. A failed stage is not a completed or blocked goal.
5. Stop only at a real decision boundary: a required permission, consequential choice, missing user-only information, irreversible external action, or external-state blocker.
6. At a decision boundary, request the permission through the host's native approval flow when available. Otherwise tell the user exactly what is blocked, whether the current goal remains active, the next step, the exact action or choice required, the recommended option, the impact of alternatives, and the shortest valid reply.
7. Before declaring completion, audit the requested outcome, validation evidence, unresolved required work, current goal state, and remaining user action. Never label a partial milestone or failed attempt as the completed task.

On every final response after opt-in, include a nonempty `用户操作：` or `User action:` field: `无需` / `none` when no user input remains, otherwise the concrete action or shortest exact reply. A brief answer can use one short sentence. When required work remains (including a successful milestone with pending permission or a choice), also include nonempty `当前目标：` / `Current goal:` and `下一步：` / `Next step:` fields. Do not end a turn just to list work you can already execute. Optional suggestions are not required work.

Do not create artificial TODOs for trivial requests. Do not commit, push, deploy, publish, add production dependencies, contact people, or mutate third-party systems unless those actions are in scope and authorized.

## Configure or validate

- When installing or updating this operating model, read [references/configuration-v2.md](references/configuration-v2.md).
- When verifying behavior or reviewing a change, run the scenarios in [references/acceptance-tests.md](references/acceptance-tests.md).
- When configuring deterministic stop-time enforcement, read [references/stop-hook.md](references/stop-hook.md).

