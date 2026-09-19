"""Mix the featured driver's name/nickname into he/him/his commentary lines."""

from __future__ import annotations

import re
from collections.abc import Sequence
from random import Random

_EN_PRONOUN = re.compile(r"\b(He's|he's|He is|he is|Himself|himself|His|his|Him|him|He|he)\b")
_CS_ON = re.compile(r"\b(On|on)\b")


def resolve_hero_names(
    *,
    driver_name: str | None,
    driver_nickname: str | None,
    iracing_names: Sequence[str] = (),
) -> tuple[str, ...]:
    """Config override wins; otherwise iRacing first/last tokens."""
    out: list[str] = []
    for raw in (driver_name, driver_nickname):
        token = str(raw).strip() if raw else ""
        if token and token not in out:
            out.append(token)
    if out:
        return tuple(out)
    for raw in iracing_names:
        token = str(raw).strip() if raw else ""
        if token and token not in out:
            out.append(token)
    return tuple(out)


def mentions_hero(text: str, names: Sequence[str]) -> bool:
    raw = text if isinstance(text, str) else ""
    if not raw or not names:
        return False
    for name in names:
        token = str(name).strip()
        if not token:
            continue
        if re.search(rf"\b{re.escape(token)}\b", raw, flags=re.IGNORECASE):
            return True
    return False


def mix_hero_name(
    text: str,
    names: Sequence[str],
    locale: str | None = "en",
    *,
    rng: Random | None = None,
    name: str | None = None,
) -> str:
    """Replace the first 3rd-person pronoun with a hero name.

    Do not prefix ``Name. rest`` or ``Name, rest`` — that reads as address
    (talks *to* the driver). Leave pronoun-free lines unchanged.

    Idempotent when any *names* token is already in *text*. Empty-safe.
    """
    raw = text if isinstance(text, str) else ""
    if not raw:
        return raw
    pool = [str(n).strip() for n in names if n and str(n).strip()]
    if name:
        chosen = str(name).strip()
        if chosen and chosen not in pool:
            pool.append(chosen)
    if not pool:
        return raw
    if mentions_hero(raw, pool):
        return raw
    chosen = (name or "").strip() or _pick_name(pool, raw, rng)
    cs = (locale or "en").strip().lower().startswith(("cs", "cz"))
    if cs:
        replaced, n = _CS_ON.subn(chosen, raw, count=1)
        return replaced if n else raw
    replaced, n = _EN_PRONOUN.subn(lambda m: _en_form(m.group(1), chosen), raw, count=1)
    return replaced if n else raw


def _pick_name(pool: Sequence[str], text: str, rng: Random | None) -> str:
    if rng is not None:
        return rng.choice(list(pool))
    return pool[abs(hash(text)) % len(pool)]


def _en_form(token: str, name: str) -> str:
    low = token.lower()
    if low in {"he's", "he is"}:
        return f"{name} is"
    if low == "his":
        return f"{name}'s"
    return name
