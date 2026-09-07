---
name: source-command-handover
description: Create or resume a durable development checkpoint when work moves between agents, pauses, or risks context/quota interruption. Use for handover, checkpoint, recovery, resume, převzetí práce, or pokračování jiným agentem.
---

# Durable handover

Follow the canonical workflow in `.cursor/commands/handover.md` and the mandatory contract in `.cursor/rules/09-agent-handover.mdc`.

The checkpoint must be reconstructable from the repository and authoritative issue without conversation history. Verify repository identity before editing, preserve unexplained dirty files, record the current TDD phase and exact next action, and retain user authorization boundaries for commits, pushes, issue changes and other external mutations.
