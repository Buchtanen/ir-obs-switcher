# Overlay and commentary Test 7 implementation plan

Issue: [#215](https://github.com/Buchtanen/ir-obs-switcher/issues/215)

1. Add failing regressions for snapshot freshness/ownership, resolved EXIT
   metadata, FINISH resolution, LLM rejection, queue choice, priority tiers,
   position coalescing and position-specific copy.
2. Make snapshot reconciliation authoritative at equal sequence, clear obsolete
   leases and forward fresh terminal metadata. Bump overlay assets in lockstep.
3. Introduce one centralized editorial tier function and apply it before graph
   selection and in both deferred queues.
4. Stop TTS before commit/speech when enabled LLM polish has no valid response;
   invalidate the story and let the best queued/current candidate proceed.
5. Preserve non-battle fact packs during mini-story resolution and fix the
   unreachable position-only composer branch.
6. Pass the incoming order-change type into preemption so repeated same-direction
   changes coalesce rather than repeatedly interrupting TTS.
7. Update the commentary contract and run focused tests followed by repository
   format, lint and type checks. Record verification and remaining risk in #215.
