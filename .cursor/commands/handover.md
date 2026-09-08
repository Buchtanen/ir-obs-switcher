# Handover checkpoint

Last durable step of `/flow`. Create or refresh the recovery point so the next agent does not need the chat.

1. Confirm `/flow` issue, diary, docs-keeper, and verifier already ran for this slice (or record why a human bypassed them).
2. Read `.cursor/rules/11-agent-handover.mdc` and identify the authoritative issue.
3. Verify the exact worktree, branch, HEAD, upstream and dirty files.
4. Record the current TDD phase, last evidence, next action, intended file ownership and blockers.
5. Prefer the issue dev diary as the durable record. Use a task-specific tracked handover file only when the issue-set already has one.
6. If a meaningful checkpoint was pushed, publish/deduplicate the dev diary with its immutable SHA.
7. Re-read the record as if no conversation context existed. Report any missing fact instead of guessing it.
8. Unless the issue-set or a human prompt says otherwise, open or update the PR to `master`.

Do not hide dirty files, claim unrun tests, or treat an in-memory subagent message as durable state.
