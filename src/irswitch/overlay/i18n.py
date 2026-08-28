"""Overlay copy catalogs.

Event payloads carry copy *tokens* (``"battle.hunting"``); the renderer resolves
them against the language chosen by ``overlay.language``. English is the base
catalog: every other locale may be partial and falls back to it.

Distinct from :mod:`irswitch.i18n`, which localises the operator dashboards.
Catalogs are plain dicts so they ship inside the wheel without package-data.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

DEFAULT_LANGUAGE = "en"

EN: Mapping[str, str] = MappingProxyType(
    {
        "battle.hunting": "HUNTING",
        "battle.hunted": "UNDER ATTACK",
        "battle.closing_in": "CLOSING IN",
        "battle.approach": "APPROACH",
        "battle.attack_range": "ATTACK RANGE",
        "battle.side_by_side": "SIDE BY SIDE",
        "lap.complete": "LAP COMPLETE",
        "lap.personal_best": "PERSONAL BEST",
        "position.gained": "POSITION GAINED",
        "position.lost": "POSITION LOST",
        "position.overtake": "OVERTAKE",
        "session.final_lap": "FINAL LAP",
        "session.finish": "FINISH",
        "incident": "INCIDENT",
        "pit.entry": "PIT ENTRY",
        "pit.lane": "PIT LANE",
        "pit.stopped": "PIT STOP",
        "pit.released": "PIT RELEASE",
        "pit.exit": "PIT EXIT",
        "pit.outcome": "PIT OUTCOME",
        "bio.hr_high": "HEART RATE HIGH",
        "bio.hr_pressure": "HR PRESSURE",
        "ble.lost": "HR SENSOR LOST",
    }
)

CS: Mapping[str, str] = MappingProxyType(
    {
        "battle.hunting": "STÍHÁM",
        "battle.hunted": "POD TLAKEM",
        "battle.closing_in": "DOTAHUJI",
        "battle.approach": "BLÍŽÍM SE",
        "battle.attack_range": "ÚTOČNÁ ZÓNA",
        "battle.side_by_side": "KOLA V KOLĚ",
        "lap.complete": "KOLO DOKONČENO",
        "lap.personal_best": "OSOBNÍ REKORD",
        "position.gained": "ZISK POZICE",
        "position.lost": "ZTRÁTA POZICE",
        "position.overtake": "PŘEDJETÍ",
        "session.final_lap": "POSLEDNÍ KOLO",
        "session.finish": "CÍL",
        "incident": "INCIDENT",
        "pit.entry": "VJEZD DO BOXŮ",
        "pit.lane": "PO BOXOVÉ DRÁZE",
        "pit.stopped": "ZASTÁVKA V BOXU",
        "pit.released": "UVOLNĚN Z BOXU",
        "pit.exit": "VÝJEZD Z BOXŮ",
        "pit.outcome": "VÝSLEDEK BOXU",
        "bio.hr_high": "VYSOKÝ TEP",
        "bio.hr_pressure": "ZÁTĚŽ TEPU",
        "ble.lost": "ZTRÁTA SENZORU TEPU",
    }
)

CATALOGS: Mapping[str, Mapping[str, str]] = MappingProxyType({"en": EN, "cs": CS})

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(CATALOGS)


def normalize_language(language: str | None) -> str:
    """Return a supported language code, falling back to English."""
    code = (language or "").strip().lower()
    return code if code in CATALOGS else DEFAULT_LANGUAGE


def catalog_for(language: str | None) -> Mapping[str, str]:
    """Return the catalog for ``language`` (English for unknown codes)."""
    return CATALOGS[normalize_language(language)]


def resolve_copy(token: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Resolve a copy token: requested locale, then English, then the token."""
    return catalog_for(language).get(token) or EN.get(token) or token


def copy_catalog_for_renderer(language: str | None = None) -> dict[str, str]:
    """Return EN base merged with locale overrides for client-side lookup."""
    code = normalize_language(language)
    merged = dict(EN)
    if code != DEFAULT_LANGUAGE:
        merged.update(catalog_for(code))
    return merged
