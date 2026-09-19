# Handover checkpoint

Last durable step of `/flow`. Create or refresh the recovery point so the next agent does not need the chat.

1. Confirm `/flow` issue, diary, docs-keeper, and verifier already ran for this slice (or record why a human bypassed them).
2. Read `.cursor/rules/11-agent-handover.mdc` and `.cursor/rules/09-agent-handover.mdc`; identify the authoritative issue.
3. Verify the exact worktree, branch, HEAD, upstream and dirty files.
4. Record the current TDD phase, last evidence, next action, intended file ownership and blockers.
5. For the v2 narrative issue-set, update `docs/v2.0.0/implementation-handover.md`. Otherwise prefer the issue dev diary unless a task-specific tracked handover already exists.
6. If a meaningful checkpoint was pushed, publish/deduplicate the dev diary with its immutable SHA.
7. Re-read the record as if no conversation context existed. Report any missing fact instead of guessing it.
8. Unless the issue-set or a human prompt says otherwise, open or update the PR to `master`. The v2 set on `codex/commentary-story-flow-spec` does **not** open a `master` PR until the cutover issue says so.

Do not hide dirty files, claim unrun tests, or treat an in-memory subagent message as durable state.
