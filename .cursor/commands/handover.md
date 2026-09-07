# Handover checkpoint

Create or refresh the durable recovery point for the current task.

1. Read `.cursor/rules/09-agent-handover.mdc` and identify the authoritative issue.
2. Verify the exact worktree, branch, HEAD, upstream and dirty files.
3. Record the current TDD phase, last evidence, next action, intended file ownership and blockers.
4. For v2, update `docs/v2.0.0/implementation-handover.md`; otherwise use the issue dev diary unless a task-specific tracked handover already exists.
5. If a meaningful checkpoint was pushed, publish/deduplicate the dev diary with its immutable SHA.
6. Re-read the record as if no conversation context existed. Report any missing fact instead of guessing it.

Do not hide dirty files, claim unrun tests, or treat an in-memory subagent message as durable state.
