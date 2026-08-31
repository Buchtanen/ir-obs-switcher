# N10 — Watcher decision log

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md)  
**Status:** **defer public API**. Optional debug ring inside N3/N5 commit if useful.

## Why deferred as a slice

A user-facing `GET` + admin page is a separate contract (`API.md`, schemaVersion). v1 needs log lines in tests/DEBUG, not a new endpoint.

If added inside N3/N5:

- bounded ring (64)
- fields: watch, kind, emitted, reason, confidence, mono_ms
- log **suppressed** generic incident when branch speaks
- log formatter fallback vs graph hit
- no INFO per-tick spam

Do not open `feat/observer-decision-log` until after live listen.
