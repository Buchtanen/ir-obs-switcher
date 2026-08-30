"""Anti-repeat + filler-tail quota for commentary line selection."""

from __future__ import annotations

import random

from irswitch.commentary.anti_repeat import (
    RecentUtteranceHistory,
    normalize_utterance,
    prefer_fresh_candidates,
    utterance_tail,
)
from irswitch.commentary.director import choose_filled_line


def test_normalize_strips_slots_and_case() -> None:
    assert normalize_utterance("  Dotahuje na {target_name}! ") == "dotahuje na"
    assert normalize_utterance("That's P5.") == "that s p5"


def test_utterance_tail_last_tokens() -> None:
    assert utterance_tail("Gap shrinks, that's pressure.", n=3) == "that s pressure"


def test_choose_filled_line_avoids_recent_exact_when_alternatives_exist() -> None:
    texts = ("Alpha line.", "Bravo line.", "Charlie line.")
    history = RecentUtteranceHistory(size=8)
    history.remember("Alpha line.")
    # Same seed that would otherwise be free to pick Alpha repeatedly.
    spoken = choose_filled_line(texts, {}, random.Random(0), history=history)
    assert spoken is not None
    assert spoken != "Alpha line."
    assert spoken in ("Bravo line.", "Charlie line.")


def test_choose_filled_line_speaks_only_candidate_even_if_recent() -> None:
    texts = ("Only one.",)
    history = RecentUtteranceHistory(size=8)
    history.remember("Only one.")
    spoken = choose_filled_line(texts, {}, random.Random(0), history=history)
    assert spoken == "Only one."


def test_choose_filled_line_without_history_stays_deterministic() -> None:
    texts = ("Alpha.", "Bravo.", "Charlie.")
    first = choose_filled_line(texts, {}, random.Random(7))
    second = choose_filled_line(texts, {}, random.Random(7))
    assert first == second
    assert first in texts


def test_filler_tail_quota_deprioritizes_shared_ending() -> None:
    history = RecentUtteranceHistory(size=8, max_similar_tails=2, tail_tokens=3)
    history.remember("Rossi closes, to je tlak.")
    history.remember("Gap shrinks, to je tlak.")
    # Two similar tails already in the ring → shared-tail candidates drop out.
    candidates = [
        "New battle, to je tlak.",
        "Completely different finish here.",
    ]
    pool = prefer_fresh_candidates(candidates, history)
    assert pool == ["Completely different finish here."]


def test_filler_tail_quota_falls_back_when_all_share_tail() -> None:
    history = RecentUtteranceHistory(size=8, max_similar_tails=1, tail_tokens=3)
    history.remember("First hit, to je tlak.")
    candidates = [
        "Second hit, to je tlak.",
        "Third hit, to je tlak.",
    ]
    pool = prefer_fresh_candidates(candidates, history)
    assert set(pool) == set(candidates)


def test_history_ring_evicts_old_exact() -> None:
    history = RecentUtteranceHistory(size=2)
    history.remember("One.")
    history.remember("Two.")
    history.remember("Three.")
    assert not history.is_recent_exact("One.")
    assert history.is_recent_exact("Two.")
    assert history.is_recent_exact("Three.")
