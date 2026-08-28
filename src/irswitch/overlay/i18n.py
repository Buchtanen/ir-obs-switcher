"""Overlay copy catalogs.

Event payloads carry copy *tokens* (``"battle.hunting"``); the renderer resolves
them against the language chosen by ``overlay.language``. English is the base
catalog: every other locale may be partial and falls back to it.

Distinct from :mod:`irswitch.i18n`, which localises the operator dashboards.
Catalogs are plain dicts so they ship inside the wheel without package-data.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

DEFAULT_LANGUAGE = "en"

EN: Mapping[str, str] = MappingProxyType(
    {
        "battle.hunting": "HUNTING",
        "battle.hunted": "UNDER ATTACK",
        "battle.closing_in": "CLOSING IN",
        "lap.complete": "LAP COMPLETE",
        "lap.personal_best": "PERSONAL BEST",
        "position.gained": "POSITION GAINED",
        "position.lost": "POSITION LOST",
        "session.final_lap": "FINAL LAP",
        "session.finish": "FINISH",
        "incident": "INCIDENT",
        "pit.entry": "PIT ENTRY",
        "pit.exit": "PIT EXIT",
        "bio.hr_high": "HEART RATE HIGH",
        "ble.lost": "HR SENSOR LOST",
    }
)

CS: Mapping[str, str] = MappingProxyType(
    {
        "battle.hunting": "STÍHÁM",
        "battle.hunted": "POD TLAKEM",
        "battle.closing_in": "DOTAHUJI",
        "lap.complete": "KOLO DOKONČENO",
        "lap.personal_best": "OSOBNÍ REKORD",
        "position.gained": "ZISK POZICE",
        "position.lost": "ZTRÁTA POZICE",
        "session.final_lap": "POSLEDNÍ KOLO",
        "session.finish": "CÍL",
        "incident": "INCIDENT",
        "pit.entry": "VJEZD DO BOXŮ",
        "pit.exit": "VÝJEZD Z BOXŮ",
        "bio.hr_high": "VYSOKÝ TEP",
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
