# Editorial MiniStory lifecycle

## Problem

LLM generation runs on the TTS worker while live telemetry continues. The old path decided to speak before Qwen started, so a relation could end or the hero order could change during generation without a final freshness decision.

## Implemented contract

- `MiniStoryRegistry` keeps a thread-safe story identity, run epoch, hero-order revision and current source facts.
- Normal EXIT before audio resolves the story. The worker uses at most one remaining Qwen call within the global two-call budget, otherwise the deterministic resolved canonical sentence.
- Normal EXIT after commit does not cancel the narrative lease.
- Session/run reset and relation identity mismatch invalidate uncommitted speech.
- A hero class-position change invalidates waiting stories and interrupts active speech. Incidents and ordinary exits do not hard-interrupt.
- The process sink uses an interrupt generation and cancellable child process, so cancellation remains visible until the old backend exits; ducking is restored by the context manager.
- DEBUG tape rows expose story/revision/run/order identity and actual commit-to-completion transitions.

## Evidence

`tests/test_ministory.py` covers resolution during delayed polish, the two-call cap, invalidation during polish, post-commit EXIT, hero-order interruption and worker reuse. Scheduler, director, TTS, consumer and overlay tape regressions cover integration and compatibility.
