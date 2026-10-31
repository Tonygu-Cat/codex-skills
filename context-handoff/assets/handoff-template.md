# Project Handoff

## Identity

- Project: `{{PROJECT_NAME}}`
- Task or thread: `{{TASK_REFERENCE}}`
- Predecessor task: `{{PREDECESSOR_TASK_OR_NONE}}`
- Successor task: `{{SUCCESSOR_TASK_OR_NONE}}`
- Rollover generation: `{{ROLLOVER_GENERATION}}`
- Source repository: `{{SOURCE_REPOSITORY}}`
- Documentation repository: `{{DOCUMENTATION_REPOSITORY}}`
- Canonical document: `{{CANONICAL_PATH}}`
- Handoff revision: `{{HANDOFF_REVISION}}`
- Updated at: `{{UPDATED_AT_ISO_8601}}`
- Source branch: `{{SOURCE_BRANCH}}`
- Source commit: `{{SOURCE_COMMIT}}`
- Status: `{{STATUS}}`

## Task lifecycle

- Policy source: {{LATEST_APPLICABLE_INSTRUCTION_REFERENCE_AND_DATE_OR_NOT_APPLICABLE}}
- Predecessor disposition: `{{NOT_APPLICABLE_OR_ARCHIVE_AFTER_TAKEOVER_OR_RETAIN_BY_EXPLICIT_REQUEST}}`
- Predecessor observed state: `{{NOT_APPLICABLE_OR_UNKNOWN_OR_ACTIVE_OR_ARCHIVED}}`
- Archive verification: {{NOT_APPLICABLE_OR_PENDING_OR_TIMESTAMPED_NATIVE_EVIDENCE_WITH_TASK_ID}}
- Successor policy acknowledgement: {{NOT_APPLICABLE_OR_PENDING_OR_RESPONSE_REFERENCE_TO_LATEST_POLICY}}
- Result destination: `current-task-user`

## Direction card

<!-- Stable direction only, within direction_card_max_chars (default 1500). Change it only when the user changes direction and log that in Decisions. A hook re-injects this card after every compaction; volatile progress belongs in Current state. -->

- Goal: {{ONE_SENTENCE_OUTCOME_THE_USER_WANTS}}
- Done when: {{VERIFIABLE_COMPLETION_CRITERIA}}
- Current phase: {{PHASE_AND_ITS_EXIT_CRITERION}}
- In scope: {{WHAT_THIS_TASK_MAY_CHANGE}}
- Out of scope / do not: {{NON_GOALS_AND_FORBIDDEN_ACTIONS}}
- Fixed user decisions: {{DATED_DECISIONS_NOT_TO_REOPEN_OR_NONE}}

## Objective and completion criteria

{{OBJECTIVE_AND_MEASURABLE_COMPLETION}}

## Current state

{{VERIFIED_CURRENT_STATE_AND_UNVERIFIED_FACTS_WITHOUT_SUPERSEDED_COMMANDS}}

## Work in progress

<!-- Refresh before every handoff; sealing requires the first three fields (write none when nothing applies). The successor checks them read-only. -->

- Unfinished work: {{NONE_OR_PARTIAL_STEP_FILES_AND_WHAT_REMAINS}}
- Background jobs: {{NONE_OR_EACH_JOB_COMMAND_PID_OUTPUT_PATH_AND_HOW_IT_ENDED}}
- Workspace changes: {{NONE_OR_COMMIT_SHA_OR_UNCOMMITTED_PATHS_FROM_GIT_STATUS}}
- External state: {{NONE_OR_APPS_SESSIONS_OR_SERVICES_LEFT_RUNNING_AND_WHO_OWNS_THEM}}

## Scope and constraints

{{IN_SCOPE_OUT_OF_SCOPE_AND_FIXED_CONSTRAINTS}}

## Decisions and rationale

{{DATED_DECISIONS_REASONS_AND_REJECTED_ALTERNATIVES_MARKING_REPLACED_DECISIONS_SUPERSEDED}}

## Changed artifacts

{{FILES_COMMITS_MIGRATIONS_CONFIG_AND_EXTERNAL_RESOURCE_IDS}}

## Verification evidence

{{COMMANDS_RUNS_REVISION_BOUND_RESULTS_AND_FAILURES}}

## Blockers, risks, and permissions

{{BLOCKERS_OWNER_CLEARING_ACTION_RISKS_AND_VALID_AUTHORIZATION}}

## Next exact actions

1. [{{OWNER_AGENT_USER_OR_EXTERNAL}}] {{FIRST_EXACT_RESUME_ACTION}}
2. [{{OWNER}}] {{SECOND_ACTION_OR_REMOVE}}
3. [{{OWNER}}] {{THIRD_ACTION_OR_REMOVE}}

- User action now: {{NONE_OR_ONE_EXACT_USER_ACTION}}
- Ready-to-send reply: {{PASTEABLE_AUTHORIZATION_OR_CHOICE_TEXT_OR_NOT_NEEDED}}

## Resume protocol

{{FILES_TO_READ_FIRST_STATE_TO_RECHECK_AND_STOP_CONDITIONS}}

## Revision log

- `{{UPDATED_AT_ISO_8601}}` r{{HANDOFF_REVISION}} — {{WHAT_CHANGED_IN_THIS_HANDOFF_REVISION}}
