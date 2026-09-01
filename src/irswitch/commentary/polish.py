"""Optional grounded LLM commentary generation over authored anchors. Fail-soft.

The model receives explicit required/optional propositions and never owns race
truth. Invalid output falls back to the authored anchor in the TTS worker.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from irswitch.commentary.graph import GraphNode, TtsLimits
from irswitch.commentary.speech_numbers import numbers_to_words
from irswitch.commentary.validator import validate_utterance
from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

# High-precision junk only. Do not NLP-match names/leads — that rejects good paraphrases.
_BANNED_PHRASE = re.compile(
    r"\b(welcome back|stay tuned|ladies and gentlemen)\b",
    re.IGNORECASE,
)
_EXPAND_PAD = 40
_EXPAND_RATIO = 1.35
_MIN_ATTEMPT_S = 0.05

_LEAD_CLAIM = re.compile(
    r"\b(unchallenged lead|narrow lead|the lead|leads?|leading|leader)\b",
    re.IGNORECASE,
)
_LEAD_OK = re.compile(
    r"\b(unchallenged lead|narrow lead|the lead|leads?|leading|leader|"
    r"pole|p\s*one|p\s*1|position\s*one)\b",
    re.IGNORECASE,
)
_POLE = re.compile(r"\bpole\b", re.IGNORECASE)
_RIVAL_AHEAD = re.compile(r"\bis ahead\b", re.IGNORECASE)
_TRAIL = re.compile(r"\b(trails?|trailing|behind|closing on|hunting)\b", re.IGNORECASE)
_PASS = re.compile(r"\b(inches past|overtakes?|overtook|passes?|passed|edges)\b", re.IGNORECASE)
_WESTWARD = re.compile(r"\b(westward|eastward|northward|southward)\b", re.IGNORECASE)
_CM = re.compile(r"\b(centimet(?:er|re)s?|centimeters?)\b", re.IGNORECASE)
_SECONDS = re.compile(r"\bseconds?\b", re.IGNORECASE)
_LIVE_CALL = re.compile(r"^\s*Live Call\s*:", re.IGNORECASE)
_HERO_PREFIX = re.compile(r"^([A-Z][a-z]{2,})\.\s+([A-Z][a-z]{2,})\b")
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_WORD_NUM = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
}
_P_TOKEN = re.compile(
    r"(?<![\w'’])p\s*-?\s*(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty)\b",
    re.IGNORECASE,
)
_S_TOKEN = re.compile(r"(?<![\w'’])s\s*(\d+|one|two|three)\b", re.IGNORECASE)
_NUMBER_LITERAL = re.compile(r"-?\d+(?:(?:[.:])\d+)*")
_POSITION_GAIN = re.compile(r"\b(gains?|gained|moves? up|takes? p\s*\d+)\b", re.IGNORECASE)
_PROPER_TOKEN = re.compile(r"\b[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wÁČĎÉĚÍŇÓŘŠŤÚŮÝŽáčďéěíňóřšťúůýž'-]{1,}\b")
_RELATION_PATTERNS = {
    "hero_closing_on_target": re.compile(
        r"\b(closes?|closing|chases?|chasing|hunts?|hunting|catches?|catching|"
        r"stahuje|dotahuje|pronásleduje)\b",
        re.IGNORECASE,
    ),
    "target_closing_on_hero": re.compile(
        r"\b(pressure|pressuring|closes?|closing|hunted|behind|tlak|tlačí|dotahuje|zezadu)\b",
        re.IGNORECASE,
    ),
    "hero_passed_target": re.compile(
        r"\b(passes?|passed|overtakes?|overtook|předjíždí|předjel)\b",
        re.IGNORECASE,
    ),
    "hero_gained_position": re.compile(
        r"\b(gains?|gained|moves? up|takes? p\s*\w+|získává|posouvá se|bere)\b",
        re.IGNORECASE,
    ),
    "hero_lost_position": re.compile(
        r"\b(loses?|lost|drops?|dropped|falls? back|ztrácí|klesá|propadá)\b",
        re.IGNORECASE,
    ),
    "class_leader_changed": re.compile(
        r"\b(lead|leader|leading|p\s*one|vedení|lídr|čela|první)\b",
        re.IGNORECASE,
    ),
    "session_result": re.compile(
        r"\b(finishes?|finished|result|wrap|ends?|ending|končí|výsledek|závěr|konec)\b",
        re.IGNORECASE,
    ),
}
_NUMBER_WORD_TOKENS = frozenset(
    {
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
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "nula",
        "jedna",
        "jeden",
        "dva",
        "dvě",
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
        "dvacet",
        "třicet",
        "čtyřicet",
        "padesát",
        "šedesát",
        "sedmdesát",
        "osmdesát",
        "devadesát",
        "sto",
        "sta",
    }
)

_FACT_LOCK = (
    "Keep EVERY fact from SKELETON. Do not add new numbers, names, or events.\n"
    "Keep numbers written as words (as in the skeleton); do not reintroduce digits.\n"
    "Keep units as words (meters per second, degrees Celsius, seconds); "
    "do not reintroduce abbreviations (m/s, °C, km/h).\n"
    "Never invent yellows, overtakes, final lap, Stay tuned, leads, or BPM.\n"
    "Do not turn a chase into a lead, or a position loss into a gain.\n"
    "P two / P two / second is a race position, not pole.\n"
    "ahead / trails / closing on / P two are not a lead. Do not say the featured "
    "driver leads unless SKELETON already says lead, P one, or pole.\n"
    "Surnames (West, Leep, and similar) are people, never compass directions.\n"
    "Do not prefix the line with Live Call:.\n"
    "Do not glue the featured driver name onto another driver's surname "
    "(not Richard Ohanian).\n"
    "Never you/your/jsi/tvůj to the featured driver. Viewers hear about the protagonist; "
    "rivals are the other named drivers.\n"
    "Never open with the featured driver's name and a comma (not 'Richard, ...'). "
    "Never open with Name. then the rest of the call. Talk about the driver; do not address them.\n"
    "Ignore prior commentary. Use only SKELETON numbers, names, and P/S marks.\n"
)

_FACT_LOCK_CS = (
    "Zachovej KAŽDÝ fakt ze SKELETONU. Nepřidávej nová čísla, jména ani události.\n"
    "Čísla ponech slovně a nevracej číslice ani zkratky jednotek.\n"
    "Nikdy nevymýšlej žlutou vlajku, předjetí, poslední kolo, vedení ani BPM.\n"
    "Nezaměň stíhání za vedení a ztrátu pozice za zisk.\n"
    "Mluv o hlavním jezdci ve třetí osobě; nikdy ho neoslovuj jako ty nebo vy.\n"
    "Nevkládej úvod typu Živě ani meta komentář.\n"
)


def _hero_lock(driver_names: Sequence[str]) -> str:
    shown = " / ".join(n.strip() for n in driver_names if n and str(n).strip())
    if not shown:
        return ""
    return (
        f"The featured driver is {shown}, the protagonist of the call. "
        "Speak about that driver in third person (name mixed with he/him/his). "
        "Other named people are rivals, not the featured driver. "
        "Never address the featured driver as you/your; this is for stream viewers, not pit radio. "
        "Do not open with their name plus a comma or a lone Name. sentence.\n"
    )


def _tts_for(node: GraphNode | None) -> TtsLimits:
    return node.tts if node is not None else TtsLimits()


def polish_char_limit(skeleton: str, tts: TtsLimits) -> int:
    """Polish may restyle, not grow into a second invented sentence."""
    n = len((skeleton or "").strip())
    grown = max(n + _EXPAND_PAD, int(n * _EXPAND_RATIO) if n else 64)
    return min(int(tts.max_chars), grown)


def _is_grounded(fact_pack: dict[str, Any] | None) -> bool:
    return isinstance(fact_pack, dict) and fact_pack.get("version") == "commentary-facts/2"


def _request_char_limit(
    skeleton: str,
    tts: TtsLimits,
    fact_pack: dict[str, Any] | None,
) -> int:
    return int(tts.max_chars) if _is_grounded(fact_pack) else polish_char_limit(skeleton, tts)


def _length_rule(tts: TtsLimits, skeleton: str) -> str:
    cap = polish_char_limit(skeleton, tts)
    return (
        "Stream-viewer commentary only, third person about the featured driver. "
        "Same sentence count as the skeleton; "
        "do not add a sentence. Richer wording of the same facts only. "
        f"Hard cap {cap} characters for this skeleton and {tts.max_seconds:g} seconds spoken. "
        "Do not welcome, recap unused history, or invent action."
    )


def _completion_tokens(
    settings: CommentarySettings,
    tts: TtsLimits,
    skeleton: str,
    fact_pack: dict[str, Any] | None,
) -> int:
    # Grounded generation may use the full node budget; legacy v1 polish stays
    # skeleton-relative for backwards compatibility.
    budget = _request_char_limit(skeleton, tts, fact_pack) + 16
    return max(32, min(int(settings.llm_max_tokens), budget))


def _expansion_code(
    skeleton: str,
    content: str,
    tts: TtsLimits,
    fact_pack: dict[str, Any] | None,
) -> str | None:
    if _BANNED_PHRASE.search(content or ""):
        return "banned_phrase"
    if len((content or "").strip()) > _request_char_limit(skeleton, tts, fact_pack):
        return "expanded"
    return None


def fact_violation_codes(
    skeleton: str,
    polished: str,
    driver_names: Sequence[str] = (),
    *,
    fact_pack: dict[str, Any] | None = None,
) -> list[str]:
    """Reject VOD-style inversions the 3B model repeats. Empty = fact-ok."""
    sk = skeleton or ""
    po = polished or ""
    codes: list[str] = []
    if _LIVE_CALL.search(po):
        codes.append("live_call_prefix")
    if _LEAD_CLAIM.search(po) and not _LEAD_OK.search(sk):
        codes.append("invented_lead")
    if _POLE.search(po) and not _POLE.search(sk) and not _LEAD_OK.search(sk):
        codes.append("invented_pole")
    if (_TRAIL.search(sk) or _RIVAL_AHEAD.search(sk)) and _LEAD_CLAIM.search(po):
        codes.append("polarity_flip")
    if _TRAIL.search(sk) and _PASS.search(po) and not _PASS.search(sk):
        codes.append("invented_pass")
    if re.search(r"\bWest\b", sk) and _WESTWARD.search(po):
        codes.append("surname_as_direction")
    if _SECONDS.search(sk) and _CM.search(po):
        codes.append("unit_distortion")
    fused = _HERO_PREFIX.match(sk.strip())
    if fused is not None:
        glued = f"{fused.group(1)} {fused.group(2)}"
        if re.search(rf"\b{re.escape(glued)}\b", po) and glued not in sk:
            codes.append("hero_name_fusion")
    if _hero_vocative(po, driver_names):
        codes.append("hero_vocative")
    if _two_front_polarity_conflict(po, fact_pack):
        codes.append("two_front_polarity_conflict")
    if _token_set(po, _P_TOKEN) - _token_set(sk, _P_TOKEN):
        codes.append("invented_position")
    if _token_set(po, _S_TOKEN) - _token_set(sk, _S_TOKEN):
        codes.append("invented_sector")
    if _is_grounded(fact_pack):
        forbidden = {
            str(item)
            for item in fact_pack.get("forbidden_claims", [])
            if isinstance(item, str)
        }
        if "on_track_pass" in forbidden and _PASS.search(po):
            codes.append("forbidden_pass")
        if "hero_leads" in forbidden and _LEAD_CLAIM.search(po):
            codes.append("forbidden_lead")
        if "position_gain" in forbidden and _POSITION_GAIN.search(po):
            codes.append("forbidden_position_gain")
        if _missing_required_terms(po, fact_pack):
            codes.append("missing_required_fact")
        if _invented_numbers(sk, po, fact_pack):
            codes.append("invented_number")
        if _invented_name(sk, po, driver_names, fact_pack):
            codes.append("invented_name")
    return codes


def _missing_required_terms(polished: str, fact_pack: dict[str, Any]) -> bool:
    folded = polished.casefold()
    raw = fact_pack.get("required_facts")
    if not isinstance(raw, list):
        return False
    for fact in raw:
        if not isinstance(fact, dict):
            continue
        terms = fact.get("required_terms")
        if isinstance(terms, list) and any(
            not _contains_term(folded, str(term)) for term in terms if str(term).strip()
        ):
            return True
        numbers = fact.get("required_numbers")
        if isinstance(numbers, list) and any(
            not _contains_number(polished, number) for number in numbers
        ):
            return True
        relation = str(fact.get("relation") or "")
        pattern = _RELATION_PATTERNS.get(relation)
        if pattern is not None and pattern.search(polished) is None:
            return True
    return False


def _contains_term(folded: str, term: str) -> bool:
    token = term.strip().casefold()
    if not token:
        return True
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", folded, re.IGNORECASE) is not None


def _contains_number(polished: str, expected: object) -> bool:
    normalized = _normalize_number(expected)
    literals = {_normalize_number(match.group(0)) for match in _NUMBER_LITERAL.finditer(polished)}
    if normalized in literals:
        return True
    folded = polished.casefold()
    for locale in ("en", "cs"):
        spoken = numbers_to_words(str(expected), locale).casefold()
        if spoken and spoken in folded:
            return True
    return False


def _invented_numbers(
    skeleton: str,
    polished: str,
    fact_pack: dict[str, Any],
) -> bool:
    allowed = {_normalize_number(item) for item in fact_pack.get("allowed_numbers", [])}
    allowed.update(_normalize_number(match.group(0)) for match in _NUMBER_LITERAL.finditer(skeleton))
    found = {_normalize_number(match.group(0)) for match in _NUMBER_LITERAL.finditer(polished)}
    if found - allowed:
        return True
    allowed_words = _number_words(skeleton)
    for item in fact_pack.get("allowed_numbers", []):
        allowed_words.update(_number_words(numbers_to_words(str(item), "en")))
        allowed_words.update(_number_words(numbers_to_words(str(item), "cs")))
    return bool(_number_words(polished) - allowed_words)


def _number_words(text: str) -> set[str]:
    tokens = re.findall(r"[\wáčďéěíňóřšťúůýž]+", (text or "").casefold())
    return {token for token in tokens if token in _NUMBER_WORD_TOKENS}


def _invented_name(
    skeleton: str,
    polished: str,
    driver_names: Sequence[str],
    fact_pack: dict[str, Any],
) -> bool:
    allowed_text = " ".join(
        [
            skeleton,
            *(str(item) for item in fact_pack.get("allowed_names", [])),
            *(str(item) for item in driver_names),
        ]
    ).casefold()
    allowed_tokens = set(re.findall(r"[\wáčďéěíňóřšťúůýž'-]+", allowed_text))
    for match in _PROPER_TOKEN.finditer(polished):
        token = match.group(0)
        if token.casefold() in allowed_tokens:
            continue
        # Sentence-opening capitalization is not enough evidence of a name.
        prefix = polished[: match.start()].rstrip()
        if not prefix or prefix[-1:] in ".!?":
            continue
        if token in {"TV", "P", "S", "Celsius", "Fahrenheit"}:
            continue
        return True
    return False


def _normalize_number(value: object) -> str:
    raw = str(value).strip().replace(",", ".")
    parts = re.split(r"([.:])", raw)
    normalized: list[str] = []
    for part in parts:
        if part in {".", ":"}:
            normalized.append(part)
        elif part.lstrip("-").isdigit():
            sign = "-" if part.startswith("-") else ""
            normalized.append(sign + (part.lstrip("-").lstrip("0") or "0"))
        else:
            normalized.append(part)
    return "".join(normalized).rstrip("0").rstrip(".") if "." in raw else "".join(normalized)


def _token_set(text: str, pattern: re.Pattern[str]) -> set[int]:
    found: set[int] = set()
    for match in pattern.finditer(text or ""):
        token = match.group(1).lower()
        if token.isdigit():
            found.add(int(token))
            continue
        mapped = _WORD_NUM.get(token)
        if mapped is not None:
            found.add(mapped)
    return found


def _two_front_polarity_conflict(
    polished: str,
    fact_pack: dict[str, Any] | None,
) -> bool:
    if not isinstance(fact_pack, dict):
        return False
    front = fact_pack.get("front_target")
    rear = fact_pack.get("rear_target")
    if not isinstance(front, dict) or not isinstance(rear, dict):
        return False
    front_name = str(front.get("name") or "").strip()
    rear_name = str(rear.get("name") or "").strip()
    if not front_name or not rear_name or front_name.casefold() == rear_name.casefold():
        return bool(front_name and rear_name)
    text = polished or ""
    front_behind = re.search(
        rf"\b{re.escape(front_name)}\b[^.!?]{{0,48}}\b(behind|from behind|rear|zezadu|vzadu)\b",
        text,
        re.IGNORECASE,
    )
    rear_ahead = re.search(
        rf"\b{re.escape(rear_name)}\b[^.!?]{{0,48}}\b(ahead|in front|vpředu|před ním)\b",
        text,
        re.IGNORECASE,
    )
    return front_behind is not None or rear_ahead is not None


def _hero_vocative(text: str, names: Sequence[str]) -> bool:
    """True when the line opens by addressing the featured driver."""
    raw = (text or "").lstrip()
    if not raw:
        return False
    for name in names:
        token = str(name).strip()
        if not token:
            continue
        # Richard, that's a lap.
        if re.match(rf"^{re.escape(token)}\s*,", raw, flags=re.IGNORECASE):
            return True
        # Richard. That's a lap.
        if re.match(rf"^{re.escape(token)}\.\s+\S", raw, flags=re.IGNORECASE):
            return True
    return False


def _reject_codes(
    skeleton: str,
    content: str,
    node: GraphNode,
    driver_names: Sequence[str] = (),
    fact_pack: dict[str, Any] | None = None,
) -> list[str]:
    codes: list[str] = []
    expand = _expansion_code(skeleton, content, node.tts, fact_pack)
    if expand:
        codes.append(expand)
    issues = validate_utterance(content, node)
    codes.extend(item.code for item in issues)
    for code in fact_violation_codes(skeleton, content, driver_names, fact_pack=fact_pack):
        if code not in codes:
            codes.append(code)
    return codes


def _system_prompt(
    *,
    past: bool,
    tts: TtsLimits,
    skeleton: str,
    driver_names: Sequence[str] = (),
    locale: str = "en",
    fact_pack: dict[str, Any] | None = None,
) -> str:
    if _is_grounded(fact_pack):
        cap = _request_char_limit(skeleton, tts, fact_pack)
        if locale.lower().startswith("cs"):
            timing = "opožděný" if past else "živý"
            return (
                f"Napiš přirozený {timing} televizní komentář pro diváky streamu.\n"
                "Použij ANCHOR jako stylistický výchozí bod. Zachovej všechna REQUIRED_FACTS, "
                "vyber jen relevantní OPTIONAL_FACTS a respektuj FORBIDDEN_CLAIMS.\n"
                "Nevymýšlej jména, čísla, pozice, sektory ani události. Piš o hlavním jezdci "
                "ve třetí osobě. Jedna nebo dvě věty, pouze výsledný komentář. "
                f"Limit je {cap} znaků a {tts.max_seconds:g} sekundy mluveného projevu."
            )
        hero = _hero_lock(driver_names)
        timing = "delayed" if past else "live"
        return (
            f"Write a natural {timing} TV race call for stream viewers.\n"
            "Use ANCHOR as a stylistic starting point. Preserve every REQUIRED_FACT, choose only "
            "relevant OPTIONAL_FACTS, and obey FORBIDDEN_CLAIMS.\n"
            "Do not invent names, numbers, positions, sectors, causes, or events. "
            f"{hero}Write one or two sentences and output commentary only. "
            f"Hard cap {cap} characters and {tts.max_seconds:g} seconds spoken."
        )
    if locale.lower().startswith("cs"):
        cap = polish_char_limit(skeleton, tts)
        timing = "opožděný televizní komentář" if past else "živý televizní komentář"
        return (
            f"Uprav {timing} pro diváky streamu, ne rádio do kokpitu.\n"
            f"{_FACT_LOCK_CS}"
            "Zachovej stejný počet vět; nepřidávej další větu. "
            f"Limit je {cap} znaků a {tts.max_seconds:g} sekundy mluveného projevu. "
            "Pouze výsledný komentář, bez vysvětlování."
        )
    hero = _hero_lock(driver_names)
    if past:
        lead = (
            "Polish a TV race call that already happened moments ago.\n"
            f"{_FACT_LOCK}{hero}"
            "Keep the same facts; do not invent that a pass, lead, or finish already happened.\n"
        )
    else:
        lead = "Polish a TV race call for stream viewers.\n" f"{_FACT_LOCK}{hero}"
    return (
        f"{lead}{_length_rule(tts, skeleton)}\n"
        "Commentary only — no meta commentary about being an AI."
    )


def _user_content(
    skeleton: str,
    *,
    past: bool,
    rejected: Sequence[str] = (),
    previous: str | None = None,
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> str:
    if _is_grounded(fact_pack):
        required = fact_pack.get("required_facts", [])
        optional = fact_pack.get("optional_facts", [])
        forbidden = fact_pack.get("forbidden_claims", [])
        allowed_names = fact_pack.get("allowed_names", [])
        allowed_numbers = fact_pack.get("allowed_numbers", [])
        parts = [
            f"ANCHOR:\n{skeleton}",
            "REQUIRED_FACTS:\n"
            + json.dumps(required, ensure_ascii=False, separators=(",", ":")),
            "OPTIONAL_FACTS:\n"
            + json.dumps(optional, ensure_ascii=False, separators=(",", ":")),
            "FORBIDDEN_CLAIMS:\n"
            + json.dumps(forbidden, ensure_ascii=False, separators=(",", ":")),
            "ALLOWED_NAMES:\n"
            + json.dumps(allowed_names, ensure_ascii=False, separators=(",", ":")),
            "ALLOWED_NUMBERS:\n"
            + json.dumps(allowed_numbers, ensure_ascii=False, separators=(",", ":")),
        ]
        if rejected:
            parts.append(
                "PREVIOUS OUTPUT REJECTED: "
                + ", ".join(rejected)
                + ". Correct those violations; do not copy the rejected output."
            )
        return "\n".join(parts)
    instruction = (
        "Rewrite this delayed call. Same facts, same length, richer wording only."
        if past
        else "Rewrite the live call. Same facts, same length, richer wording only."
    )
    parts = [f"SKELETON:\n{skeleton}\n{instruction}"]
    if fact_pack:
        safe = {key: value for key, value in fact_pack.items() if key != "recent"}
        parts.append(
            "FACTS:\n" + json.dumps(safe, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
    if composition_path:
        parts.append("COMPOSITION_PATH: " + " -> ".join(str(item) for item in composition_path))
    if rejected:
        parts.append(
            "PREVIOUS REWRITE REJECTED: "
            + ", ".join(rejected)
            + ". Do not repeat those mistakes. Output only the rewrite."
        )
        if previous:
            parts.append(f"REJECTED TEXT:\n{previous}")
    return "\n".join(parts)


@dataclass(frozen=True)
class PolishOutcome:
    """Result of one polish attempt (for TTS + optional debug tape)."""

    text: str
    outcome: str  # ok | fallback_disabled | fallback_timeout | fallback_error | retry_exhausted
    latency_ms: float
    skeleton: str
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    attempts: int = 0
    fact_pack: dict[str, Any] | None = None
    composition_path: tuple[str, ...] = ()

    def debug_record(self, *, node_id: str, event_type: str) -> dict[str, Any]:
        last = None
        if isinstance(self.response, dict):
            last = self.response.get("content")
        grounded = _is_grounded(self.fact_pack)
        return {
            "nodeId": node_id,
            "eventType": event_type,
            "outcome": self.outcome,
            "latencyMs": round(self.latency_ms, 1),
            "attempts": self.attempts,
            "skeleton": self.skeleton,
            "polished": self.text if self.outcome == "ok" else last,
            "spoken": self.text,
            "request": self.request,
            "response": self.response,
            "factPack": self.fact_pack,
            "compositionPath": list(self.composition_path),
            "grounded": grounded,
            "anchor": self.skeleton if grounded else None,
            "requiredFacts": (
                self.fact_pack.get("required_facts", []) if grounded and self.fact_pack else []
            ),
            "optionalFacts": (
                self.fact_pack.get("optional_facts", []) if grounded and self.fact_pack else []
            ),
            "fallbackUsed": self.outcome != "ok",
        }


def _max_attempts(settings: CommentarySettings) -> int:
    try:
        raw = int(getattr(settings, "llm_max_attempts", 5) or 5)
    except (TypeError, ValueError):
        raw = 5
    return max(1, min(8, raw))


def build_polish_request(
    skeleton: str,
    settings: CommentarySettings,
    *,
    past: bool = False,
    node: GraphNode | None = None,
    driver_names: Sequence[str] = (),
    rejected: Sequence[str] = (),
    previous: str | None = None,
    locale: str = "en",
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> dict[str, Any]:
    tts = _tts_for(node)
    text = skeleton.strip()
    return {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": _completion_tokens(settings, tts, text, fact_pack),
        # Native Ollama + OpenAI-compat: keep Qwen3 from spending the token
        # budget on a thinking trace (empty content / timeout).
        "think": False,
        "reasoning_effort": "none",
        "messages": [
            {
                "role": "system",
                "content": _system_prompt(
                    past=past,
                    tts=tts,
                    skeleton=text,
                    driver_names=driver_names,
                    locale=locale,
                    fact_pack=fact_pack,
                ),
            },
            {
                "role": "user",
                "content": _user_content(
                    text,
                    past=past,
                    rejected=rejected,
                    previous=previous,
                    fact_pack=fact_pack,
                    composition_path=composition_path,
                ),
            },
        ],
    }


def _failed(
    *,
    outcome: str,
    latency_ms: float,
    skeleton: str,
    request: dict[str, Any],
    response: dict[str, Any] | None = None,
    attempts: int,
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> PolishOutcome:
    return PolishOutcome(
        text="",
        outcome=outcome,
        latency_ms=latency_ms,
        skeleton=skeleton,
        request=request,
        response=response,
        attempts=attempts,
        fact_pack=fact_pack,
        composition_path=tuple(composition_path),
    )


def polish_skeleton(
    skeleton: str,
    node: GraphNode,
    settings: CommentarySettings,
    *,
    opener: Any | None = None,
    past: bool = False,
    driver_names: Sequence[str] = (),
    locale: str = "en",
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> PolishOutcome:
    """Blocking HTTP polish. Never raises. Empty text when polish is on and fails."""
    text = (skeleton or "").strip()
    if not text:
        return PolishOutcome(
            text="",
            outcome="fallback_validate",
            latency_ms=0.0,
            skeleton=skeleton,
            request={},
            attempts=0,
            fact_pack=fact_pack,
            composition_path=tuple(composition_path),
        )
    if not settings.llm_polish:
        return PolishOutcome(
            text=text,
            outcome="fallback_disabled",
            latency_ms=0.0,
            skeleton=text,
            request={},
            attempts=0,
            fact_pack=fact_pack,
            composition_path=tuple(composition_path),
        )

    url = _chat_completions_url(settings.llm_base_url)
    if urlparse(url).scheme not in {"http", "https"}:
        return _failed(
            outcome="fallback_error",
            latency_ms=0.0,
            skeleton=text,
            request=build_polish_request(
                text,
                settings,
                past=past,
                node=node,
                driver_names=driver_names,
                locale=locale,
                fact_pack=fact_pack,
                composition_path=composition_path,
            ),
            response={"error": "llm_base_url must be http(s)"},
            attempts=0,
            fact_pack=fact_pack,
            composition_path=composition_path,
        )

    max_attempts = _max_attempts(settings)
    deadline = time.monotonic() + max(0.5, float(settings.llm_timeout_s))
    started = time.monotonic()
    payload: dict[str, Any] = {}
    last_response: dict[str, Any] | None = None
    timed_out = 0
    http_ok = 0

    for attempt in range(1, max_attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= _MIN_ATTEMPT_S:
            break
        rejected: Sequence[str] = ()
        previous: str | None = None
        if isinstance(last_response, dict):
            codes = last_response.get("validatorCodes")
            if isinstance(codes, list) and codes:
                rejected = [str(code) for code in codes]
            previous = str(last_response.get("content") or "") or None
        payload = build_polish_request(
            text,
            settings,
            past=past,
            node=node,
            driver_names=driver_names,
            rejected=rejected,
            previous=previous,
            locale=locale,
            fact_pack=fact_pack,
            composition_path=composition_path,
        )
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            if opener is not None:
                raw = opener(req, timeout=remaining)
            else:
                with urllib.request.urlopen(req, timeout=remaining) as resp:  # nosec B310
                    raw = resp.read()
        except TimeoutError:
            timed_out += 1
            last_response = {"error": "timeout"}
            continue
        except urllib.error.URLError as exc:
            last_response = {"error": str(exc.reason)}
            logger.warning("commentary llm polish unreachable: %s", exc.reason)
            continue
        except Exception as exc:
            last_response = {"error": str(exc)}
            logger.warning("commentary llm polish failed", exc_info=True)
            continue

        http_ok += 1
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_response = {"error": f"bad json: {exc}"}
            continue

        if not isinstance(parsed, dict):
            last_response = {"error": "not an object"}
            continue
        content = _extract_content(parsed)
        compact = _compact_response(parsed)
        if not content:
            last_response = compact
            continue

        codes = _reject_codes(text, content, node, driver_names, fact_pack)
        last_response = {**compact, "validatorCodes": codes}
        if codes:
            continue

        latency = (time.monotonic() - started) * 1000.0
        return PolishOutcome(
            text=content,
            outcome="ok",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response=compact,
            attempts=attempt,
            fact_pack=fact_pack,
            composition_path=tuple(composition_path),
        )

    latency = (time.monotonic() - started) * 1000.0
    attempts_done = max(timed_out + http_ok, 1)
    if http_ok == 0 and timed_out > 0:
        kind = "fallback_timeout"
    elif http_ok == 0:
        kind = "fallback_error"
    else:
        kind = "retry_exhausted"
    return _failed(
        outcome=kind,
        latency_ms=latency,
        skeleton=text,
        request=payload,
        response=last_response,
        attempts=attempts_done,
        fact_pack=fact_pack,
        composition_path=composition_path,
    )


def _chat_completions_url(base_url: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    if not root:
        root = "http://127.0.0.1:11434/v1"
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def _extract_content(parsed: dict[str, Any]) -> str:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    raw = str(content).strip() if content else ""
    if raw:
        return _THINK_BLOCK.sub("", raw).strip()
    return ""


def _compact_response(parsed: dict[str, Any]) -> dict[str, Any]:
    usage = parsed.get("usage")
    compact: dict[str, Any] = {
        "id": parsed.get("id"),
        "model": parsed.get("model"),
        "content": _extract_content(parsed),
    }
    if isinstance(usage, dict):
        compact["usage"] = usage
    return compact
