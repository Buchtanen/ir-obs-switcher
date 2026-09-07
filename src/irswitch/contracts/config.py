"""Strict immutable v2 commentary configuration candidates.

This module validates a complete desired candidate.  It deliberately does not
apply values to the live runtime; ConfigLedger owns generation and boundary
application in the next implementation slice.
"""

from __future__ import annotations

import configparser
import ipaddress
import json
import math
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from .primitives import Sha256Hash, canonical_sha256
from .resources import packaged_schema_bytes

_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_LLM_GROUP = frozenset(
    {
        "commentary.llm_base_url",
        "commentary.llm_model",
        "commentary.llm_timeout_s",
        "commentary.llm_max_tokens",
    }
)
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_IPV6_UNIQUE_LOCAL = ipaddress.ip_network("fc00::/7")


@dataclass(frozen=True, slots=True)
class ConfigDiagnostic:
    reason: str
    source_key: str
    replacement_keys: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class CommentaryConfigSnapshot:
    """One fully defaulted, normalized and hash-addressed desired snapshot."""

    values: MappingProxyType[str, object]
    config_hash: Sha256Hash

    @classmethod
    def create(cls, values: dict[str, object]) -> CommentaryConfigSnapshot:
        frozen = {key: _freeze(value) for key, value in sorted(values.items())}
        digest = canonical_sha256(_json_values(frozen))
        return cls(MappingProxyType(frozen), digest)

    def to_dict(self) -> dict[str, object]:
        return _json_values(self.values)

    def replay_values(self) -> dict[str, object]:
        sensitive = _contract()["ledgerContract"]["sensitiveKeys"]
        return {
            key: ({"redacted": True} if key in sensitive else _json_value(value))
            for key, value in self.values.items()
        }


@dataclass(frozen=True, slots=True)
class CommentaryConfigCandidate:
    valid: bool
    snapshot: CommentaryConfigSnapshot | None
    diagnostics: tuple[ConfigDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class PendingConfigChange:
    key: str
    boundary: str
    desired_generation: int


@dataclass(frozen=True, slots=True)
class ConfigPreflight:
    component: str
    generation: int


@dataclass(frozen=True, slots=True)
class ConfigInstallOutcome:
    installed: bool
    desired_generation: int
    automatic_enabled: bool
    diagnostics: tuple[ConfigDiagnostic, ...]
    preflights: tuple[ConfigPreflight, ...]


@dataclass(frozen=True, slots=True)
class EffectiveConfigPatch:
    key: str
    value: object | None
    redacted: bool


@dataclass(frozen=True, slots=True)
class ConfigApplyRecord:
    apply_sequence: int
    boundary: str
    desired_generation: int
    changed_keys: tuple[str, ...]
    old_effective_hash: Sha256Hash
    new_effective_hash: Sha256Hash
    effective_patch: tuple[EffectiveConfigPatch, ...]


_MISSING = object()


class ConfigLedger:
    """Single-owner desired/effective ledger with exact boundary application."""

    def __init__(
        self,
        initial: CommentaryConfigSnapshot,
        *,
        desired_generation: int = 0,
        apply_sequence: int = 0,
        ready_components: tuple[str, ...] = (),
    ) -> None:
        if desired_generation < 0 or apply_sequence < 0:
            raise ValueError("config generation and apply sequence must be nonnegative")
        if any(component not in {"llm", "tts"} for component in ready_components):
            raise ValueError("unknown config preflight component")
        self._lock = threading.Lock()
        self._desired = initial
        self._effective = initial
        self._desired_generation = desired_generation
        self._apply_sequence = apply_sequence
        self._pending: tuple[PendingConfigChange, ...] = ()
        self._component_status = dict.fromkeys(ready_components, (desired_generation, True))

    @property
    def desired_generation(self) -> int:
        with self._lock:
            return self._desired_generation

    @property
    def apply_sequence(self) -> int:
        with self._lock:
            return self._apply_sequence

    @property
    def desired_snapshot(self) -> CommentaryConfigSnapshot:
        with self._lock:
            return self._desired

    @property
    def effective_snapshot(self) -> CommentaryConfigSnapshot:
        with self._lock:
            return self._effective

    @property
    def pending_changes(self) -> tuple[PendingConfigChange, ...]:
        with self._lock:
            return self._pending

    def install(self, candidate: CommentaryConfigCandidate) -> ConfigInstallOutcome:
        """Install one whole valid desired generation or preserve all prior state."""

        with self._lock:
            if not candidate.valid or candidate.snapshot is None:
                return ConfigInstallOutcome(
                    False,
                    self._desired_generation,
                    False,
                    candidate.diagnostics,
                    (),
                )
            old_desired = self._desired
            self._desired_generation += 1
            self._desired = candidate.snapshot
            self._pending = self._recompute_pending()

            changed_components: set[str] = set()
            all_keys = set(old_desired.values) | set(candidate.snapshot.values)
            for key in all_keys:
                if old_desired.values.get(key, _MISSING) == candidate.snapshot.values.get(
                    key, _MISSING
                ):
                    continue
                definition = _definition_for(key)
                component = None if definition is None else definition.get("preflightComponent")
                if component in {"llm", "tts"}:
                    changed_components.add(component)

            for component in ("llm", "tts"):
                if component in changed_components:
                    self._component_status[component] = (self._desired_generation, False)
                elif component in self._component_status:
                    _, ready = self._component_status[component]
                    self._component_status[component] = (self._desired_generation, ready)

            preflights = tuple(
                ConfigPreflight(component, self._desired_generation)
                for component in sorted(changed_components)
            )
            return ConfigInstallOutcome(
                True,
                self._desired_generation,
                bool(candidate.snapshot.values["commentary.enabled"]),
                (),
                preflights,
            )

    def apply_boundary(self, boundary: str) -> ConfigApplyRecord | None:
        """Apply every pending key owned by one exact frozen boundary."""

        boundaries = frozenset(_contract()["ledgerContract"]["boundaryVocabulary"])
        if boundary not in boundaries:
            raise ValueError(f"unknown config apply boundary: {boundary}")
        with self._lock:
            keys = tuple(item.key for item in self._pending if item.boundary == boundary)
            if not keys:
                return None
            old_snapshot = self._effective
            effective_values = dict(old_snapshot.values)
            for key in keys:
                if key in self._desired.values:
                    effective_values[key] = self._desired.values[key]
                else:
                    effective_values.pop(key, None)
            self._effective = CommentaryConfigSnapshot.create(effective_values)
            self._apply_sequence += 1
            self._pending = self._recompute_pending()
            sensitive = frozenset(_contract()["ledgerContract"]["sensitiveKeys"])
            patch = tuple(
                EffectiveConfigPatch(
                    key,
                    None if key in sensitive else self._desired.values.get(key),
                    key in sensitive,
                )
                for key in keys
            )
            return ConfigApplyRecord(
                self._apply_sequence,
                boundary,
                self._desired_generation,
                keys,
                old_snapshot.config_hash,
                self._effective.config_hash,
                patch,
            )

    def record_preflight(self, component: str, generation: int, *, success: bool) -> bool:
        """Accept only the current generation's component completion."""

        with self._lock:
            status = self._component_status.get(component)
            if status is None or status[0] != generation or generation != self._desired_generation:
                return False
            self._component_status[component] = (generation, success)
            return True

    def component_available(self, component: str, generation: int) -> bool:
        """Never use a ready backend proved for an older desired generation."""

        with self._lock:
            return self._component_status.get(component) == (generation, True)

    def _recompute_pending(self) -> tuple[PendingConfigChange, ...]:
        keys = set(self._desired.values) | set(self._effective.values)
        pending: list[PendingConfigChange] = []
        for key in sorted(keys):
            if self._desired.values.get(key, _MISSING) == self._effective.values.get(key, _MISSING):
                continue
            definition = _definition_for(key)
            if definition is None:
                raise ValueError(f"missing frozen definition for effective key: {key}")
            boundary = (
                "next_stream"
                if key.startswith("commentary.detector.")
                else definition["applyBoundary"]
            )
            pending.append(PendingConfigChange(key, boundary, self._desired_generation))
        return tuple(pending)


@lru_cache(maxsize=1)
def _contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(packaged_schema_bytes("config-contract.json")))


@lru_cache(maxsize=1)
def _detector_catalog() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(packaged_schema_bytes("detector-catalog.json")))


def _freeze(value: object) -> object:
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    return value


def _json_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, MappingProxyType):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _json_values(values: object) -> dict[str, object]:
    if not isinstance(values, (dict, MappingProxyType)):
        raise TypeError("config values must be a mapping")
    return {str(key): _json_value(value) for key, value in values.items()}


def _legacy_entry(key: str) -> dict[str, Any] | None:
    for entry in _contract()["migrationContract"]["entries"]:
        source = entry["source"]
        match_kind = entry["matchKind"]
        if match_kind == "exact" and key == source:
            return cast(dict[str, Any], entry)
        if match_kind == "prefix" and key.startswith(source.removesuffix("*")):
            return cast(dict[str, Any], entry)
        if match_kind == "group" and key in _LLM_GROUP:
            return cast(dict[str, Any], entry)
        if match_kind == "section" and key == source:
            return cast(dict[str, Any], entry)
    return None


def _definition_for(key: str) -> dict[str, Any] | None:
    for definition in _contract()["keyDefinitions"]:
        if definition["keyClass"] == "static" and definition["key"] == key:
            return cast(dict[str, Any], definition)
    prefix = "commentary.detector."
    if not key.startswith(prefix):
        return None
    suffix = key[len(prefix) :]
    detector_id, separator, option = suffix.partition(".")
    if not separator:
        return None
    detector = next(
        (item for item in _detector_catalog()["definitions"] if item["id"] == detector_id),
        None,
    )
    if detector is None:
        return None
    if option == "enabled":
        return {
            "key": key,
            "valueType": "boolean",
            "constraints": {},
            "sensitive": False,
        }
    parameter = next((item for item in detector["parameters"] if item["id"] == option), None)
    if parameter is None:
        return None
    return {
        "key": key,
        "valueType": parameter["type"],
        "constraints": {
            "minimum": parameter["minimum"],
            "maximum": parameter["maximum"],
        },
        "sensitive": False,
    }


def _normalized_string(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{key} contains a control character")
    return " ".join(unicodedata.normalize("NFC", value).strip().split())


def _scalar(value: object, definition: dict[str, Any], *, from_ini: bool) -> object:
    key = definition["key"]
    value_type = definition["valueType"]
    constraints = definition.get("constraints", {})

    if value_type == "boolean":
        if from_ini:
            if value not in {"true", "false"}:
                raise ValueError(f"{key} must be exactly true or false")
            parsed: object = value == "true"
        else:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
            parsed = value
    elif value_type == "integer":
        if from_ini:
            if not isinstance(value, str) or _INTEGER.fullmatch(value) is None:
                raise ValueError(f"{key} must be a finite base-10 integer")
            parsed = int(value, 10)
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{key} must be an integer")
            parsed = value
    elif value_type == "number":
        if from_ini:
            if not isinstance(value, str) or _NUMBER.fullmatch(value) is None:
                raise ValueError(f"{key} must be a finite base-10 number")
            parsed = float(value)
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"{key} must be a finite base-10 number")
    elif value_type in {"string", "url", "path", "enum"}:
        parsed = _normalized_string(value, key)
        if value_type == "enum" and parsed not in constraints["values"]:
            raise ValueError(f"{key} must be one of {constraints['values']}")
    elif value_type in {"enum_set", "string_set"}:
        raw_items: list[str] | list[object]
        if from_ini:
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a comma-separated set")
            raw_items = value.split(",") if value else []
        elif isinstance(value, (list, tuple)):
            raw_items = list(value)
        else:
            raise ValueError(f"{key} must be a set array")
        items = [_normalized_string(item, key) for item in raw_items]
        if len(set(items)) != len(items):
            raise ValueError(f"{key} has a duplicate set member")
        allowed = constraints.get("values")
        if constraints.get("reference") == "exported_detector_ids":
            allowed = [item["id"] for item in _detector_catalog()["definitions"]]
        if allowed is not None and any(item not in allowed for item in items):
            raise ValueError(f"{key} contains an unknown set member")
        parsed = tuple(sorted(items))
    else:
        raise ValueError(f"{key} has unsupported frozen type {value_type}")

    if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
        if "minimum" in constraints and parsed < constraints["minimum"]:
            raise ValueError(f"{key} is out of range")
        if "maximum" in constraints and parsed > constraints["maximum"]:
            raise ValueError(f"{key} is out of range")
    if isinstance(parsed, str):
        if len(parsed) < constraints.get("minLength", 0):
            raise ValueError(f"{key} is shorter than allowed")
        if len(parsed) > constraints.get("maxLength", 2**31):
            raise ValueError(f"{key} is longer than allowed")
    return parsed


def _validate_url(value: str, key: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError
        if parsed.query or parsed.fragment:
            raise ValueError
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        host = parsed.hostname
        if host is None:
            raise ValueError
        local = host == "localhost"
        if not local:
            address = ipaddress.ip_address(host)
            local = (
                address.is_loopback
                or address.is_link_local
                or (
                    address.version == 4
                    and any(address in network for network in _RFC1918_NETWORKS)
                )
                or (address.version == 6 and address in _IPV6_UNIQUE_LOCAL)
            )
        path = "/" + "/".join(part for part in parsed.path.split("/") if part)
        if path == "/":
            path = ""
        if path not in {"", "/v1"} and not path.endswith("/v1"):
            raise ValueError
        if not local:
            raise ValueError
        netloc = f"[{host}]" if ":" in host else host
        if port is not None:
            netloc = f"{netloc}:{port}"
        return urlunsplit((parsed.scheme, netloc, path, "", ""))
    except (ValueError, ipaddress.AddressValueError) as error:
        raise ValueError(f"{key} URL outside local/LAN policy") from error


def _validate_path(
    value: str,
    key: str,
    *,
    repository_root: Path,
    working_directory: Path,
    home_directory: Path,
) -> str:
    path = Path(value).expanduser()
    lexical = working_directory / path if not path.is_absolute() else path
    resolved = lexical.resolve(strict=False)
    forbidden = {
        Path(resolved.anchor).resolve(strict=False),
        home_directory.resolve(strict=False),
        repository_root.resolve(strict=False),
    }
    if resolved in forbidden:
        raise ValueError(f"{key} is an unsafe root path")
    if not path.is_absolute():
        base = working_directory.resolve(strict=False)
        cursor = base
        for part in path.parts:
            cursor /= part
            if cursor.is_symlink() and not cursor.resolve(strict=False).is_relative_to(base):
                raise ValueError(f"{key} follows an existing symlink outside output parent")
    existing = lexical
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir() or not os.access(existing, os.W_OK):
        raise ValueError(f"{key} destination parent is not writable")
    return value


def _directional_detector_errors(values: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for detector in _detector_catalog()["definitions"]:
        if detector["kind"] != "directional":
            continue
        detector_id = detector["id"]
        parameters = {item["id"]: item["default"] for item in detector["parameters"]}
        prefix = f"commentary.detector.{detector_id}."
        for key, value in values.items():
            if key.startswith(prefix) and key != f"{prefix}enabled":
                parameters[key.removeprefix(prefix)] = value

        checks = (
            (
                parameters["sample_interval_s"]
                < parameters["bucket_s"]
                <= parameters["trend_window_s"],
                "sample_interval_s < bucket_s <= trend_window_s",
            ),
            (
                parameters["min_samples"] * parameters["sample_interval_s"]
                <= parameters["trend_window_s"],
                "min_samples * sample_interval_s <= trend_window_s",
            ),
            (
                parameters["confirm_s"] <= parameters["trend_window_s"],
                "confirm_s <= trend_window_s",
            ),
            (
                parameters["enter_gap_max_s"] < parameters["exit_gap_min_s"],
                "enter_gap_max_s < exit_gap_min_s",
            ),
            (
                parameters["overlap_enter_s"]
                < parameters["overlap_exit_s"]
                <= parameters["attack_enter_s"]
                < parameters["attack_exit_s"],
                "overlap_enter_s < overlap_exit_s <= attack_enter_s < attack_exit_s",
            ),
            (
                parameters["attack_exit_s"]
                <= parameters["approach_enter_s"]
                < parameters["approach_exit_s"]
                <= parameters["enter_gap_max_s"],
                "attack_exit_s <= approach_enter_s < approach_exit_s <= enter_gap_max_s",
            ),
            (
                parameters["update_min_interval_s"] >= parameters["clear_s"],
                "update_min_interval_s >= clear_s",
            ),
            (
                parameters["stale_after_s"] <= parameters["trend_window_s"],
                "stale_after_s <= trend_window_s",
            ),
        )
        errors.extend(
            f"detector {detector_id} violates {message}" for passed, message in checks if not passed
        )
    return errors


def _tuning_errors(values: dict[str, object], *, capture_preflight_ready: bool) -> list[str]:
    errors: list[str] = []
    profile = values["commentary.detectors.profile"]
    tape_enabled = values["commentary.tape.enabled"]
    channels = cast(tuple[str, ...] | list[str], values["commentary.tape.channels"])
    allowlist = cast(
        tuple[str, ...] | list[str],
        values["commentary.tape.detector_tuning.trigger_allowlist"],
    )
    captures = values["commentary.tape.detector_tuning.capture_input_windows"]
    for detector in _detector_catalog()["definitions"]:
        detector_id = detector["id"]
        enabled = values.get(f"commentary.detector.{detector_id}.enabled", False)
        if not enabled or detector["tuningPolicy"] != "required":
            continue
        if not detector["experimental"]:
            errors.append(f"required tuning detector {detector_id} cannot be enabled")
        elif profile != "calibration":
            errors.append(f"required tuning detector {detector_id} requires calibration profile")
        elif not tape_enabled or "detector_tuning" not in channels:
            errors.append(f"required tuning detector {detector_id} requires detector_tuning tape")
        elif detector_id not in allowlist:
            errors.append(f"required tuning detector {detector_id} must be allowlisted")
        elif not captures:
            errors.append(f"required tuning detector {detector_id} requires input-window capture")
        elif not capture_preflight_ready:
            errors.append(
                f"required tuning detector {detector_id} requires writable recorder preflight"
            )
    return errors


def _cross_field_errors(
    values: dict[str, object], *, detector_capture_preflight_ready: bool
) -> list[str]:
    errors: list[str] = []
    active_capacity = cast(int, values["commentary.director.active_episode_capacity"])
    resolved_capacity = cast(int, values["commentary.director.resolved_episode_capacity"])
    tape_channels = cast(tuple[str, ...] | list[str], values["commentary.tape.channels"])
    if active_capacity > resolved_capacity:
        errors.append("active episode capacity must not exceed resolved episode capacity")
    if values["commentary.tape.enabled"] and not values["commentary.tape.channels"]:
        errors.append("tape channels empty while tape is enabled")
    if (
        values["commentary.tape.llm_eval.capture_prompt"] == "full"
        and "llm_eval" not in tape_channels
    ):
        errors.append("full prompt requires the llm_eval tape channel")
    errors.extend(_directional_detector_errors(values))
    errors.extend(_tuning_errors(values, capture_preflight_ready=detector_capture_preflight_ready))
    return errors


def parse_commentary_mapping(
    supplied: object,
    *,
    repository_root: Path,
    working_directory: Path | None = None,
    home_directory: Path | None = None,
    detector_capture_preflight_ready: bool = False,
    _from_ini: bool = False,
) -> CommentaryConfigCandidate:
    """Validate a complete candidate from dotted v2 keys without partial install."""

    if not isinstance(supplied, dict) or any(not isinstance(key, str) for key in supplied):
        diagnostic = ConfigDiagnostic("invalid_config", "commentary", (), "config must be a map")
        return CommentaryConfigCandidate(False, None, (diagnostic,))

    diagnostics: list[ConfigDiagnostic] = []
    for key in supplied:
        legacy = _legacy_entry(key)
        if legacy is not None:
            diagnostics.append(
                ConfigDiagnostic(
                    "legacy_key",
                    key,
                    tuple(legacy["replacementKeys"]),
                    f"legacy key {key}: {legacy['result']}",
                )
            )
        elif _definition_for(key) is None:
            diagnostics.append(
                ConfigDiagnostic("invalid_config", key, (), f"unknown config key: {key}")
            )
    if diagnostics:
        return CommentaryConfigCandidate(False, None, tuple(diagnostics))

    values = dict(_contract()["defaultConfig"])
    workdir = (working_directory or repository_root).resolve(strict=False)
    home = (home_directory or Path.home()).resolve(strict=False)
    for key, raw in supplied.items():
        definition = _definition_for(key)
        assert definition is not None
        try:
            parsed = _scalar(raw, definition, from_ini=_from_ini)
            if definition["valueType"] == "url":
                parsed = _validate_url(cast(str, parsed), key)
            elif definition["valueType"] == "path":
                parsed = _validate_path(
                    cast(str, parsed),
                    key,
                    repository_root=repository_root,
                    working_directory=workdir,
                    home_directory=home,
                )
            values[key] = parsed
        except ValueError as error:
            diagnostics.append(ConfigDiagnostic("invalid_config", key, (), str(error)))

    if not diagnostics:
        for definition in _contract()["keyDefinitions"]:
            if definition["keyClass"] != "static":
                continue
            key = definition["key"]
            try:
                if definition["valueType"] == "url":
                    values[key] = _validate_url(cast(str, values[key]), key)
                elif definition["valueType"] == "path":
                    values[key] = _validate_path(
                        cast(str, values[key]),
                        key,
                        repository_root=repository_root,
                        working_directory=workdir,
                        home_directory=home,
                    )
            except ValueError as error:
                diagnostics.append(ConfigDiagnostic("invalid_config", key, (), str(error)))

    if not diagnostics:
        diagnostics.extend(
            ConfigDiagnostic("invalid_config", "commentary", (), message)
            for message in _cross_field_errors(
                values,
                detector_capture_preflight_ready=detector_capture_preflight_ready,
            )
        )
    if diagnostics:
        return CommentaryConfigCandidate(False, None, tuple(diagnostics))
    return CommentaryConfigCandidate(True, CommentaryConfigSnapshot.create(values), ())


def parse_commentary_ini(
    parser: configparser.ConfigParser,
    *,
    repository_root: Path,
    working_directory: Path | None = None,
    home_directory: Path | None = None,
    detector_capture_preflight_ready: bool = False,
) -> CommentaryConfigCandidate:
    """Flatten commentary INI sections and enforce the v2 scalar grammar."""

    supplied: dict[str, str] = {}
    for section in parser.sections():
        if section == "commentary" or section.startswith("commentary."):
            section_marker = f"[{section}]"
            if _legacy_entry(section_marker) is not None:
                supplied[section_marker] = ""
                continue
            for option, value in parser.items(section, raw=True):
                supplied[f"{section}.{option}"] = value.strip()
    return parse_commentary_mapping(
        supplied,
        repository_root=repository_root,
        working_directory=working_directory,
        home_directory=home_directory,
        detector_capture_preflight_ready=detector_capture_preflight_ready,
        _from_ini=True,
    )
