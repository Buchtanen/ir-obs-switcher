"""Expand digits and unit tokens to spoken words for LLM polish + TTS.

No third-party deps. Applied on the TTS worker path so the race loop stays
non-blocking. Authored graph lines may still store digits and compact units
(``m/s``, ``23 C``, ``0.38 s``); conversion happens immediately before polish
and again before speak (LLM may reintroduce digits or abbreviations).
"""

from __future__ import annotations

import re
from functools import lru_cache

_EN_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_EN_TENS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)

_CS_ONES = (
    "nula",
    "jedna",
    "dva",
    "tři",
    "čtyři",
    "pět",
    "šest",
    "sedm",
    "osm",
    "devět",
    "deset",
    "jedenáct",
    "dvanáct",
    "třináct",
    "čtrnáct",
    "patnáct",
    "šestnáct",
    "sedmnáct",
    "osmnáct",
    "devatenáct",
)
_CS_TENS = (
    "",
    "",
    "dvacet",
    "třicet",
    "čtyřicet",
    "padesát",
    "šedesát",
    "sedmdesát",
    "osmdesát",
    "devadesát",
)

# Lap / sector clock: 1:52.084 or 1:52
_LAP_TIME = re.compile(r"\b(\d{1,2}):([0-5]\d)(?:\.(\d{1,3}))?\b")
# Signed or plain decimals: +0.318, -1.91, 0.38
_DECIMAL = re.compile(r"(?<![A-Za-z0-9_])([+-]?)(\d+)\.(\d+)(?![A-Za-z0-9_])")
# Sector marker S1 / S12
_SECTOR = re.compile(r"\bS(\d{1,2})\b", re.IGNORECASE)
# Position / car shorthand P5 / #12 (keep letter, expand digits)
_PREFIXED = re.compile(r"(?<![A-Za-z0-9])([P#p])(\d{1,3})\b")
# Bare integers (skip tokens like line-0 / id_12)
_INTEGER = re.compile(r"(?<![A-Za-z0-9_-])(\d{1,3})(?!\.\d)(?![A-Za-z0-9_])")

# Compact speech units from weather / gap formatters and LLM leftovers.
_UNIT_DEG_OF_C = re.compile(r"\bdegrees\s+of\s+Celsius\b", re.IGNORECASE)
_UNIT_MPS = re.compile(r"\bm\s*/\s*s\b", re.IGNORECASE)
_UNIT_KMH = re.compile(r"\b(?:km\s*/\s*h|kmh|kph)\b", re.IGNORECASE)
_UNIT_MPH = re.compile(r"\bmph\b", re.IGNORECASE)
_UNIT_DEG_C_SYM = re.compile(r"(?:°\s*C|℃)\b", re.IGNORECASE)
_UNIT_DEG_F_SYM = re.compile(r"(?:°\s*F|℉)\b", re.IGNORECASE)
_UNIT_DEG_C_WORD = re.compile(r"\bdeg(?:ree)?s?\s*C\b", re.IGNORECASE)
_UNIT_DEG_F_WORD = re.compile(r"\bdeg(?:ree)?s?\s*F\b", re.IGNORECASE)
_UNIT_BPM = re.compile(r"\bbpm\b", re.IGNORECASE)
_UNIT_PERCENT = re.compile(r"%")
# Gap formatter ``1.91 s`` / glued ``0.38s`` — lowercase s only (keep sector ``S1``).
_UNIT_SECONDS_DIGITS = re.compile(r"(?<=\d)\s*s\b")
_UNIT_CELSIUS_DIGITS = re.compile(r"(?<=\d)\s*C\b", re.IGNORECASE)


def numbers_to_words(text: str, locale: str | None = "en") -> str:
    """Replace digit and unit tokens in ``text`` with locale words. Empty-safe."""
    raw = text if isinstance(text, str) else ""
    if not raw:
        return raw
    cs = _is_cs(locale)
    out = _units_to_words(raw, cs)
    if any(ch.isdigit() for ch in out):
        out = _LAP_TIME.sub(lambda m: _lap_time_words(m, cs), out)
        out = _DECIMAL.sub(lambda m: _decimal_words(m, cs), out)
        out = _SECTOR.sub(lambda m: _sector_words(m, cs), out)
        out = _PREFIXED.sub(lambda m: _prefixed_words(m, cs), out)
        out = _INTEGER.sub(lambda m: _int_words(int(m.group(1)), cs), out)
        out = _units_to_words(out, cs)
    return _collapse_spaces(out)


def _is_cs(locale: str | None) -> bool:
    code = (locale or "en").strip().lower()
    return code.startswith("cs") or code.startswith("cz")


def _collapse_spaces(text: str) -> str:
    return re.sub(r" {2,}", " ", text).strip() if text else text


def _unit_labels(cs: bool) -> dict[str, str]:
    if cs:
        return {
            "mps": "metrů za sekundu",
            "kmh": "kilometrů za hodinu",
            "mph": "mil za hodinu",
            "c": "stupňů Celsia",
            "f": "stupňů Fahrenheita",
            "s": "sekund",
            "pct": "procent",
            "bpm": "úderů za minutu",
        }
    return {
        "mps": "meters per second",
        "kmh": "kilometers per hour",
        "mph": "miles per hour",
        "c": "degrees Celsius",
        "f": "degrees Fahrenheit",
        "s": "seconds",
        "pct": "percent",
        "bpm": "beats per minute",
    }


@lru_cache(maxsize=2)
def _number_word_unit_re(cs: bool) -> re.Pattern[str]:
    """Match a spoken number token plus a leftover ``C`` / ``s`` unit."""
    parts = [w for w in ((_CS_ONES if cs else _EN_ONES) + (_CS_TENS if cs else _EN_TENS)) if w]
    if cs:
        parts.extend(("sto", "sta", "tečka", "plus", "mínus", "minus"))
    else:
        parts.extend(("hundred", "point", "plus", "minus"))
    inner = "|".join(re.escape(w) for w in sorted(set(parts), key=len, reverse=True))
    token = rf"(?:{inner})(?:-(?:{inner}))?"
    return re.compile(rf"\b({token})\s+(C|s)\b", re.IGNORECASE)


def _units_to_words(text: str, cs: bool) -> str:
    """Expand compact unit tokens; leave numbers for the digit pass."""
    labels = _unit_labels(cs)
    out = _UNIT_DEG_OF_C.sub(labels["c"], text)
    out = _UNIT_KMH.sub(labels["kmh"], out)
    out = _UNIT_MPS.sub(labels["mps"], out)
    out = _UNIT_MPH.sub(labels["mph"], out)
    out = _UNIT_DEG_C_SYM.sub(labels["c"], out)
    out = _UNIT_DEG_F_SYM.sub(labels["f"], out)
    out = _UNIT_DEG_C_WORD.sub(labels["c"], out)
    out = _UNIT_DEG_F_WORD.sub(labels["f"], out)
    out = _UNIT_BPM.sub(labels["bpm"], out)
    out = _UNIT_PERCENT.sub(" " + labels["pct"], out)
    out = _UNIT_SECONDS_DIGITS.sub(" " + labels["s"], out)
    out = _UNIT_CELSIUS_DIGITS.sub(" " + labels["c"], out)

    def _word_unit(match: re.Match[str]) -> str:
        head = match.group(1)
        kind = match.group(2).lower()
        if kind == "c":
            return f"{head} {labels['c']}"
        return f"{head} {labels['s']}"

    return _number_word_unit_re(cs).sub(_word_unit, out)


def _int_words(n: int, cs: bool) -> str:
    if n < 0:
        return f"{'mínus' if cs else 'minus'} {_int_words(-n, cs)}"
    if n < 20:
        return (_CS_ONES if cs else _EN_ONES)[n]
    if n < 100:
        tens = n // 10
        ones = n % 10
        if cs:
            return _CS_TENS[tens] if ones == 0 else f"{_CS_TENS[tens]} {_CS_ONES[ones]}"
        return _EN_TENS[tens] if ones == 0 else f"{_EN_TENS[tens]}-{_EN_ONES[ones]}"
    if n < 1000:
        hundreds = n // 100
        rest = n % 100
        if cs:
            head = "sto" if hundreds == 1 else f"{_CS_ONES[hundreds]} sta"
            return head if rest == 0 else f"{head} {_int_words(rest, True)}"
        head = "one hundred" if hundreds == 1 else f"{_EN_ONES[hundreds]} hundred"
        return head if rest == 0 else f"{head} {_int_words(rest, False)}"
    # Rare in commentary; fall back to digit-by-digit.
    return " ".join(_digit_words(ch, cs) for ch in str(n))


def _digit_words(ch: str, cs: bool) -> str:
    if not ch.isdigit():
        return ch
    return (_CS_ONES if cs else _EN_ONES)[int(ch)]


def _frac_words(frac: str, cs: bool) -> str:
    return " ".join(_digit_words(ch, cs) for ch in frac)


def _lap_time_words(match: re.Match[str], cs: bool) -> str:
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    frac = match.group(3)
    if cs:
        parts = [
            _int_words(minutes, True),
            "minuta" if minutes == 1 else "minuty" if minutes < 5 else "minut",
            _int_words(seconds, True),
        ]
        if frac:
            parts.extend(["tečka", _frac_words(frac, True)])
        return " ".join(parts)
    parts = [
        _int_words(minutes, False),
        "minute" if minutes == 1 else "minutes",
        _int_words(seconds, False),
    ]
    if frac:
        parts.extend(["point", _frac_words(frac, False)])
    return " ".join(parts)


def _decimal_words(match: re.Match[str], cs: bool) -> str:
    sign, whole, frac = match.group(1), match.group(2), match.group(3)
    prefix = ""
    if sign == "+":
        prefix = "plus "
    elif sign == "-":
        prefix = "mínus " if cs else "minus "
    point = "tečka" if cs else "point"
    return f"{prefix}{_int_words(int(whole), cs)} {point} {_frac_words(frac, cs)}"


def _sector_words(match: re.Match[str], cs: bool) -> str:
    return f"S {_int_words(int(match.group(1)), cs)}"


def _prefixed_words(match: re.Match[str], cs: bool) -> str:
    return f"{match.group(1).upper()} {_int_words(int(match.group(2)), cs)}"


@lru_cache(maxsize=8)
def _locale_key(locale: str | None) -> str:
    return "cs" if _is_cs(locale) else "en"
