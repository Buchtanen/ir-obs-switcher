"""Bounded anti-repeat + filler-tail quota for commentary line selection.

Densified cells still share Czech/EN filler endings. This module keeps a short
ring of recently spoken (normalized) lines and deprioritizes exact repeats and
near-duplicate tails when alternatives exist. Never hard-fails: if every
candidate is recent / over quota, selection falls back to any fully-bound line.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Defaults (not config keys — document in COMMENTARY_ENGINE.md).
DEFAULT_HISTORY_SIZE = 24
DEFAULT_TAIL_TOKENS = 5
DEFAULT_MAX_SIMILAR_TAILS = 1
DEFAULT_TAIL_RATIO = 0.78

_SLOT_TOKEN = re.compile(r"\{[a-z0-9_]+\}", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_utterance(text: str) -> str:
    """Lowercase, strip slots, drop punctuation, collapse whitespace."""
    raw = text if isinstance(text, str) else ""
    cleaned = _SLOT_TOKEN.sub(" ", raw)
    cleaned = cleaned.casefold()
    cleaned = _NON_WORD.sub(" ", cleaned)
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned


def utterance_tokens(text: str) -> tuple[str, ...]:
    norm = normalize_utterance(text)
    if not norm:
        return ()
    return tuple(norm.split(" "))


def utterance_tail(text: str, *, n: int = DEFAULT_TAIL_TOKENS) -> str:
    """Last *n* normalized tokens (shared filler endings)."""
    tokens = utterance_tokens(text)
    if not tokens:
        return ""
    width = max(1, int(n))
    return " ".join(tokens[-width:])


def tails_similar(
    left: str,
    right: str,
    *,
    ratio: float = DEFAULT_TAIL_RATIO,
) -> bool:
    """True when tails match exactly or SequenceMatcher ratio is high enough."""
    a = left.strip()
    b = right.strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= float(ratio)


@dataclass
class RecentUtteranceHistory:
    """Ring buffer of recently spoken normalized lines + raw tails."""

    size: int = DEFAULT_HISTORY_SIZE
    tail_tokens: int = DEFAULT_TAIL_TOKENS
    max_similar_tails: int = DEFAULT_MAX_SIMILAR_TAILS
    tail_ratio: float = DEFAULT_TAIL_RATIO
    _norms: deque[str] = field(default_factory=deque, init=False, repr=False)
    _tails: deque[str] = field(default_factory=deque, init=False, repr=False)
    _raws: deque[str] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        maxlen = max(1, int(self.size))
        self.size = maxlen
        self.tail_tokens = max(1, int(self.tail_tokens))
        self.max_similar_tails = max(1, int(self.max_similar_tails))
        self.tail_ratio = float(self.tail_ratio)
        self._norms = deque(maxlen=maxlen)
        self._tails = deque(maxlen=maxlen)
        self._raws = deque(maxlen=maxlen)

    def clear(self) -> None:
        self._norms.clear()
        self._tails.clear()
        self._raws.clear()

    def remember(self, text: str) -> None:
        norm = normalize_utterance(text)
        if not norm:
            return
        self._norms.append(norm)
        self._tails.append(utterance_tail(text, n=self.tail_tokens))
        self._raws.append(str(text).strip())

    def forget_last(self, text: str) -> None:
        """Undo an optimistic remember when a queued line never becomes audible."""
        raw = str(text).strip()
        if not self._raws or self._raws[-1] != raw:
            return
        self._raws.pop()
        self._norms.pop()
        self._tails.pop()

    def recent(self, limit: int | None = None) -> tuple[str, ...]:
        """Return a bounded oldest-to-newest copy for fact-pack anti-repeat hints."""
        if limit is None:
            return tuple(self._raws)
        width = max(0, int(limit))
        if width == 0:
            return ()
        return tuple(self._raws)[-width:]

    def __len__(self) -> int:
        return len(self._norms)

    def is_recent_exact(self, text: str) -> bool:
        norm = normalize_utterance(text)
        if not norm:
            return False
        return norm in self._norms

    def similar_tail_count(self, text: str) -> int:
        candidate = utterance_tail(text, n=self.tail_tokens)
        if not candidate:
            return 0
        return sum(
            1 for prev in self._tails if tails_similar(candidate, prev, ratio=self.tail_ratio)
        )

    def tail_over_quota(self, text: str) -> bool:
        return self.similar_tail_count(text) >= self.max_similar_tails


def prefer_fresh_candidates(
    candidates: list[str],
    history: RecentUtteranceHistory | None,
) -> list[str]:
    """Filter order: fresh+under-quota → not-exact → all (never empty if input nonempty)."""
    if not candidates:
        return []
    if history is None or len(history) == 0:
        return list(candidates)

    preferred = [
        line
        for line in candidates
        if not history.is_recent_exact(line) and not history.tail_over_quota(line)
    ]
    if preferred:
        return preferred

    fresh = [line for line in candidates if not history.is_recent_exact(line)]
    if fresh:
        return fresh

    return list(candidates)
