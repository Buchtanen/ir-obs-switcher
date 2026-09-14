"""Mix the featured driver's name/nickname into he/him/his commentary lines."""

from __future__ import annotations

import re
from collections.abc import Sequence
from random import Random

_EN_PRONOUN = re.compile(r"\b(He is|he is|Himself|himself|His|his|Him|him|He|he)\b(?!['’]s)")
_CS_ON = re.compile(r"\b(On|on)\b")
_FULL_CLAUSE = re.compile(
    r"^(that'?s|that is|the|a|an)\b",
    re.IGNORECASE,
)
_POSITION_OPEN = re.compile(
    r"^p\s*[-.]?\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty)\b",
    re.IGNORECASE,
)


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


def broadcast_identity(names: Sequence[str]) -> str:
    """Prefer nickname (last configured token) then the first spoken name."""
    pool = [str(n).strip() for n in names if n and str(n).strip()]
    if len(pool) >= 2:
        return pool[1]
    return pool[0] if pool else ""


def normalize_hero_vocative(text: str, names: Sequence[str]) -> str:
    """Rewrite a vocative opener to third person. Does not accept the line."""
    raw = (text or "").lstrip()
    if not raw:
        return text
    for name in names:
        token = str(name).strip()
        if not token:
            continue
        match = re.match(rf"^{re.escape(token)}\s*[,.]\s+(.+)$", raw, flags=re.IGNORECASE | re.S)
        if match is None:
            continue
        rest = match.group(1).strip()
        if not rest:
            return raw
        if _FULL_CLAUSE.match(rest) and (
            rest.lower().startswith(("that's", "that’s", "that is"))
            or re.search(r"\b(is|are|was|were)\b", rest, flags=re.IGNORECASE)
        ):
            return rest[:1].upper() + rest[1:]
        if _POSITION_OPEN.match(rest):
            return f"{token} is {rest}"
        return f"{token} is {rest}"
    return text


def rewrite_schema_hero(text: str, names: Sequence[str]) -> str:
    """Replace schema-role 'Hero X' / \"X's hero closing\" with broadcast identity."""
    raw = text if isinstance(text, str) else ""
    if not raw:
        return raw
    identity = broadcast_identity(names)
    if not identity:
        return raw
    out = re.sub(r"\bHero\s+" + re.escape(identity) + r"\b", identity, raw, flags=re.IGNORECASE)
    for name in names:
        token = str(name).strip()
        if not token:
            continue
        out = re.sub(r"\bHero\s+" + re.escape(token) + r"\b", identity, out, flags=re.IGNORECASE)
        out = re.sub(
            rf"\b{re.escape(token)}['’]s hero closing\b",
            f"{identity} is closing",
            out,
            flags=re.IGNORECASE,
        )
    out = re.sub(r"\bHero\s+Richard\b", identity, out, flags=re.IGNORECASE)
    out = re.sub(
        r"\bRichard['’]s hero closing\b",
        f"{identity} is closing",
        out,
        flags=re.IGNORECASE,
    )
    return out


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
    if low == "he is":
        return f"{name} is"
    if low == "his":
        return f"{name}'s"
    return name
