"""Reproducible semantic and latency evaluation over commentary tape rows.

The corpus points at recorded polish operations and asserts propositions and
constraints.  It deliberately does not prescribe one golden sentence.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?::\d+)*(?:\.\d+)?")


@dataclass(frozen=True)
class PolishRecord:
    tape: str
    ordinal: int
    event_type: str
    node_id: str
    outcome: str
    attempts: int
    latency_ms: float
    skeleton: str
    polished: str
    prompt_tokens: int | None
    completion_tokens: int | None
    fact_pack: dict[str, Any]
    request: dict[str, Any]
    validator_codes: tuple[str, ...]

    @property
    def key(self) -> tuple[str, int]:
        return self.tape, self.ordinal


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    tape: str
    polish_ordinal: int
    category: str
    story_state: str
    required_fact_ids: tuple[str, ...]
    expected_relation: str | None
    forbidden_claims: tuple[str, ...]
    forbidden_terms: tuple[str, ...]
    invalid_source_fact_ids: tuple[str, ...]
    expected_eligibility: str
    note: str

    @property
    def key(self) -> tuple[str, int]:
        return self.tape, self.polish_ordinal


@dataclass(frozen=True)
class EvaluationIssue:
    code: str
    severity: str
    detail: str


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def load_polish_records(paths: Iterable[Path]) -> list[PolishRecord]:
    """Load only ``llm_polish`` rows and assign a stable per-tape ordinal."""
    records: list[PolishRecord] = []
    for path in sorted(paths, key=lambda item: item.name):
        ordinal = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
                if not isinstance(row, dict) or row.get("type") != "llm_polish":
                    continue
                ordinal += 1
                response = _object(row.get("response"))
                usage = _object(response.get("usage"))
                codes = response.get("validatorCodes")
                records.append(
                    PolishRecord(
                        tape=path.name,
                        ordinal=ordinal,
                        event_type=str(row.get("eventType") or ""),
                        node_id=str(row.get("nodeId") or ""),
                        outcome=str(row.get("outcome") or ""),
                        attempts=int(row.get("attempts") or 0),
                        latency_ms=float(row.get("latencyMs") or 0.0),
                        skeleton=str(row.get("skeleton") or ""),
                        polished=str(row.get("polished") or ""),
                        prompt_tokens=(
                            int(usage["prompt_tokens"])
                            if usage.get("prompt_tokens") is not None
                            else None
                        ),
                        completion_tokens=(
                            int(usage["completion_tokens"])
                            if usage.get("completion_tokens") is not None
                            else None
                        ),
                        fact_pack=_object(row.get("factPack")),
                        request=_object(row.get("request")),
                        validator_codes=_strings(codes),
                    )
                )
    return records


def load_corpus(path: Path) -> list[EvaluationCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != "commentary-eval/1":
        raise ValueError("unsupported commentary evaluation corpus")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("commentary evaluation corpus has no cases")
    cases: list[EvaluationCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("corpus case must be an object")
        case_id = str(raw.get("id") or "").strip()
        if not case_id or case_id in seen:
            raise ValueError(f"invalid or duplicate corpus case id: {case_id!r}")
        seen.add(case_id)
        cases.append(
            EvaluationCase(
                id=case_id,
                tape=str(raw.get("tape") or ""),
                polish_ordinal=int(raw.get("polishOrdinal") or 0),
                category=str(raw.get("category") or ""),
                story_state=str(raw.get("storyState") or "live"),
                required_fact_ids=_strings(raw.get("requiredFactIds")),
                expected_relation=(
                    str(raw["expectedRelation"]) if raw.get("expectedRelation") else None
                ),
                forbidden_claims=_strings(raw.get("forbiddenClaims")),
                forbidden_terms=_strings(raw.get("forbiddenTerms")),
                invalid_source_fact_ids=_strings(raw.get("invalidSourceFactIds")),
                expected_eligibility=str(raw.get("expectedEligibility") or "speak"),
                note=str(raw.get("note") or ""),
            )
        )
    return cases


def resolve_cases(
    cases: Sequence[EvaluationCase], records: Sequence[PolishRecord]
) -> list[tuple[EvaluationCase, PolishRecord]]:
    by_key = {record.key: record for record in records}
    resolved: list[tuple[EvaluationCase, PolishRecord]] = []
    for case in cases:
        record = by_key.get(case.key)
        if record is None:
            raise ValueError(f"{case.id}: missing source row {case.tape}#{case.polish_ordinal}")
        resolved.append((case, record))
    return resolved


def _facts(record: PolishRecord) -> list[dict[str, Any]]:
    raw = [
        record.fact_pack.get("required_facts"),
        record.fact_pack.get("optional_facts"),
    ]
    return [
        item for group in raw if isinstance(group, list) for item in group if isinstance(item, dict)
    ]


def _normalized_number(value: object) -> str:
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return raw
    if ":" in raw:
        return ":".join(part.lstrip("0") or "0" for part in raw.split(":"))
    try:
        return f"{float(raw):.9f}".rstrip("0").rstrip(".")
    except ValueError:
        return raw.casefold()


def _literal_numbers(text: str) -> set[str]:
    return {_normalized_number(match.group(0)) for match in _NUMBER.finditer(text)}


def _fact_numbers(fact: dict[str, Any]) -> list[object]:
    value = fact.get("required_numbers")
    return value if isinstance(value, list) else []


def evaluate_case(case: EvaluationCase, record: PolishRecord) -> list[EvaluationIssue]:
    """Evaluate explicit corpus constraints plus selected-fact numeric grounding."""
    issues: list[EvaluationIssue] = []
    facts = _facts(record)
    facts_by_id = {str(fact.get("id") or ""): fact for fact in facts}
    for fact_id in case.required_fact_ids:
        if fact_id not in facts_by_id:
            issues.append(
                EvaluationIssue("source_contract_mismatch", "hard", f"missing fact {fact_id}")
            )
    if case.expected_relation:
        relations = {str(fact.get("relation") or "") for fact in facts}
        relations.add(str(_object(record.fact_pack.get("beat")).get("relation") or ""))
        if case.expected_relation not in relations:
            issues.append(
                EvaluationIssue(
                    "source_contract_mismatch",
                    "hard",
                    f"missing relation {case.expected_relation}",
                )
            )
    source_forbidden = set(_strings(record.fact_pack.get("forbidden_claims")))
    missing_forbidden = set(case.forbidden_claims) - source_forbidden
    if missing_forbidden:
        issues.append(
            EvaluationIssue(
                "source_contract_mismatch",
                "hard",
                "missing forbidden claims: " + ", ".join(sorted(missing_forbidden)),
            )
        )
    for fact_id in case.invalid_source_fact_ids:
        if fact_id in facts_by_id:
            issues.append(
                EvaluationIssue("invalid_source_fact", "hard", f"invalid fact emitted: {fact_id}")
            )
    if case.expected_eligibility == "reject":
        issues.append(
            EvaluationIssue("ineligible_source_story", "hard", "story should not be generated")
        )

    output = record.polished.strip()
    if not output:
        issues.append(EvaluationIssue("missing_model_output", "hard", "empty final model output"))
        return issues
    folded = output.casefold()
    for term in case.forbidden_terms:
        if term.casefold() in folded:
            issues.append(EvaluationIssue("forbidden_term", "hard", term))

    selected = [
        facts_by_id[fact_id] for fact_id in case.required_fact_ids if fact_id in facts_by_id
    ]
    optional = record.fact_pack.get("optional_facts")
    if isinstance(optional, list):
        selected += [fact for fact in optional if isinstance(fact, dict) and fact not in selected]
    allowed_numbers = {
        _normalized_number(number) for fact in selected for number in _fact_numbers(fact)
    }
    skeleton_numbers = _literal_numbers(record.skeleton)
    invented = _literal_numbers(output) - allowed_numbers - skeleton_numbers
    if invented:
        issues.append(
            EvaluationIssue(
                "invented_selected_fact_number",
                "hard",
                ", ".join(sorted(invented)),
            )
        )
    return issues


def summarize(records: Sequence[PolishRecord]) -> dict[str, Any]:
    latencies = [record.latency_ms for record in records]
    accepted = [record.latency_ms for record in records if record.outcome == "ok"]
    fallbacks = [record.latency_ms for record in records if record.outcome != "ok"]
    prompt_tokens = [record.prompt_tokens for record in records if record.prompt_tokens is not None]
    completion_tokens = [
        record.completion_tokens for record in records if record.completion_tokens is not None
    ]

    def median(values: Sequence[float | int]) -> float:
        return round(float(statistics.median(values)), 3) if values else 0.0

    fallback_count = len(fallbacks)
    operations = len(records)
    return {
        "operations": operations,
        "modelCalls": sum(record.attempts for record in records),
        "fallbacks": fallback_count,
        "fallbackRate": round(fallback_count / operations, 4) if operations else 0.0,
        "outcomes": dict(sorted(Counter(record.outcome for record in records).items())),
        "attempts": {
            str(key): value
            for key, value in sorted(Counter(record.attempts for record in records).items())
        },
        "latencyMs": {
            "medianAll": median(latencies),
            "medianAccepted": median(accepted),
            "medianFallback": median(fallbacks),
            "maximum": round(max(latencies), 3) if latencies else 0.0,
        },
        "tokens": {
            "medianPrompt": median(prompt_tokens),
            "medianCompletion": median(completion_tokens),
        },
    }


def evaluate_corpus(
    cases: Sequence[EvaluationCase], records: Sequence[PolishRecord]
) -> dict[str, Any]:
    resolved = resolve_cases(cases, records)
    rows: list[dict[str, Any]] = []
    severity: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    for case, record in resolved:
        issues = evaluate_case(case, record)
        severity.update(issue.severity for issue in issues)
        codes.update(issue.code for issue in issues)
        rows.append(
            {
                "id": case.id,
                "source": f"{record.tape}#{record.ordinal}",
                "eventType": record.event_type,
                "outcome": record.outcome,
                "issues": [issue.__dict__ for issue in issues],
            }
        )
    return {
        "cases": len(rows),
        "issuesBySeverity": dict(sorted(severity.items())),
        "issuesByCode": dict(sorted(codes.items())),
        "results": rows,
    }


def replay_live(record: PolishRecord, base_url: str, timeout_s: float = 12.0) -> str:
    """Repeat one stored request against an OpenAI-compatible local endpoint."""
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("live replay URL must use http or https and include a host")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(record.request).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # B310 is suppressed only after the explicit HTTP(S) scheme and host validation above.
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310  # nosec B310
        payload = json.loads(response.read().decode("utf-8"))
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("local model response has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("local model response has no message")
    return str(message.get("content") or "").strip()


def _paths(recordings: Path) -> list[Path]:
    return sorted(recordings.glob("overlay-20260901T*.jsonl"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, default=Path("recordings"))
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("tests/fixtures/commentary/commentary_eval_cases.json"),
    )
    parser.add_argument("--live-url", help="repeat corpus requests against this local base URL")
    parser.add_argument("--live-limit", type=int, default=0)
    args = parser.parse_args(argv)

    records = load_polish_records(_paths(args.recordings))
    cases = load_corpus(args.corpus)
    result: dict[str, Any] = {
        "baseline": summarize(records),
        "corpus": evaluate_corpus(cases, records),
    }
    if args.live_url:
        limit = args.live_limit if args.live_limit > 0 else len(cases)
        by_key = {record.key: record for record in records}
        live: list[dict[str, str]] = []
        for case in cases[:limit]:
            record = by_key[case.key]
            live.append({"id": case.id, "output": replay_live(record, args.live_url)})
        result["live"] = live
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
