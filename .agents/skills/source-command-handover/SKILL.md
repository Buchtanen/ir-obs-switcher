---
name: source-command-handover
description: Last /flow step — durable checkpoint so the next agent can resume. Use for handover, checkpoint, recovery, resume, převzetí práce, or pokračování jiným agentem. Do not use this as a substitute for issue, docs-keeper, or verifier.
---

# Durable handover

Follow `.cursor/commands/handover.md` and `.cursor/rules/11-agent-handover.mdc`.

This is the **end** of `/flow`, not the work loop. The checkpoint must be reconstructable from the repository and the authoritative issue without conversation history. Then, unless the issue-set or a human prompt says otherwise, open a PR to `master`.
