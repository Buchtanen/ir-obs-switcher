"""Owned, bounded async model IO for current-fact commentary.

Remote M1 is an OpenAI-compatible wire protocol, not an OpenAI identity claim.
No redirect, ambient proxy, retry, or output-derived semantic authority.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import aiohttp

from irswitch.events.commentary_grounding import free_grounding_reasons
from irswitch.events.commentary_microplan import M2_SYSTEM, Microplan, digest
from irswitch.events.semantic_verifier import free_wording_reasons


@dataclass(frozen=True)
class ModelSettings:
    enabled: bool = False
    speech_enabled: bool = True
    provider: str = "local"
    mode: str = "live"
    wording_policy: str = "strict"
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen3:4b-instruct-2507-q4_K_M"
    api_key_env: str = "IRSWITCH_LLM_API_KEY"
    timeout_s: float = 1.5
    max_tokens: int = 96
    warmup: bool = True

    @classmethod
    def from_values(cls, values: dict[str, Any]) -> ModelSettings:
        settings = {
            key: values.get(f"commentary.llm.{key}", field.default)
            for key, field in cls.__dataclass_fields__.items()
        }
        settings["enabled"] = bool(settings["enabled"] and values.get("commentary.enabled", False))
        settings["speech_enabled"] = bool(values.get("commentary.enabled", False))
        return cls(**settings)

    @property
    def signature(self) -> str:
        return digest(self.__dict__)

    @property
    def effective_wording_policy(self) -> str:
        if (
            self.enabled
            and self.provider == "remote"
            and self.wording_policy == "experimental_free"
        ):
            return "experimental_free"
        return "strict"


class ModelFailure(Exception):
    """A safe diagnostic code; never carries a URL, credential or response body."""


class ModelSkip:
    """A valid model decision to stay silent, distinct from transport fallback."""


class ModelClient:
    def __init__(
        self, settings: Callable[[], ModelSettings], *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._busy = False
        self._closed = False
        self._shadow: asyncio.Task[None] | None = None
        self._attempts: deque[str] = deque(maxlen=256)
        self._skipped: deque[str] = deque(maxlen=256)
        self._history: deque[dict[str, Any]] = deque(maxlen=100)
        self._generation = 0
        self._signature = ""
        self._last: dict[str, Any] = {}
        self._preflight = "not_requested"
        self._preflight_signature = ""
        self._spoken: deque[str] = deque(maxlen=128)
        self._played_context: deque[dict[str, Any]] = deque(maxlen=8)
        self._total_attempts = 0
        self._selections: deque[dict[str, Any]] = deque(maxlen=100)

    def _speech_key(self, plan: Microplan) -> str:
        return digest((plan.session_id, plan.correlation_id, [text for _, text in plan.facts]))

    def was_spoken(self, plan: Microplan) -> bool:
        return self._speech_key(plan) in self._spoken

    def note_spoken(self, plan: Microplan) -> None:
        """Only PLAYBACK_ACCEPTED may advance actual spoken fact memory."""
        self._spoken.append(self._speech_key(plan))
        for row in reversed(self._selections):
            if row["bundleHash"] == plan.digest:
                row.update(played=True, playedMonoMs=round(self._clock() * 1000))
                self._played_context.append(
                    {
                        "session_id": plan.session_id,
                        "played_mono_ms": round(self._clock() * 1000),
                        "text": row["text"],
                        "actors": [name for _, name in plan.actors],
                        "actor_bindings": list(plan.actors),
                        "correlation_id": plan.correlation_id,
                        "beat_id": plan.beat_id,
                        "input_fields": list(plan.input_fields),
                    }
                )
                break

    def note_selection(self, plan: Microplan, text: str, *, generated: bool) -> None:
        cfg = self._settings()
        self._selections.append(
            {
                "eventId": plan.event_id,
                "bundleHash": plan.digest,
                "source": cfg.provider if generated else "authored",
                "model": cfg.model if generated else None,
                "text": text,
                "played": False,
                "wordingPolicy": cfg.effective_wording_policy,
                "semanticCheck": (
                    "not_enforced"
                    if generated and cfg.effective_wording_policy == "experimental_free"
                    else "strict"
                ),
                "strictWouldAccept": plan.accepts(text),
                "selectedMonoMs": round(self._clock() * 1000),
            }
        )

    def status(self) -> dict[str, Any]:
        cfg = self._settings()
        return {
            "provider": cfg.provider,
            "mode": cfg.mode,
            "model": cfg.model,
            "profile": "M2/1" if cfg.provider == "remote" else "tight/1",
            "wordingPolicy": cfg.effective_wording_policy,
            "timeoutSeconds": cfg.timeout_s,
            "enabled": cfg.enabled,
            "speechEnabled": cfg.speech_enabled,
            "busy": self._busy,
            "generation": self._generation,
            "preflight": (
                self._preflight
                if not self._preflight_signature or cfg.signature == self._preflight_signature
                else "stale"
            ),
            "attemptCount": len(self._attempts),
            "lastReason": self._last.get("reason"),
            "totalAttempts": self._total_attempts,
            "lastAttempt": dict(self._last),
            "recentAttempts": list(self._history),
            "recentSelections": list(self._selections),
        }

    def settings(self) -> ModelSettings:
        return self._settings()

    def _headers(self, cfg: ModelSettings) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if cfg.provider == "remote":
            token = os.environ.get(cfg.api_key_env, "").strip()
            if not token or any(c.isspace() for c in token):
                raise ModelFailure("credential_missing")
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request_plan(self, plan: Microplan) -> Microplan:
        """Add only a deterministic comparison to an actually played same-target update."""
        if plan.beat_id != "HUNTING" or len(plan.actors) < 2:
            return plan
        current_gap = dict(plan.input_fields).get("gap_seconds")
        if not isinstance(current_gap, (int, float)):
            return plan
        now_ms = round(self._clock() * 1000)
        for previous in reversed(self._played_context):
            age_ms = now_ms - previous["played_mono_ms"]
            if (
                previous["session_id"] != plan.session_id
                or previous["beat_id"] != "HUNTING"
                or previous["actor_bindings"] != list(plan.actors)
                or previous["correlation_id"] != plan.correlation_id
                or not 1000 <= age_ms <= 60000
            ):
                continue
            old_gap = dict(previous["input_fields"]).get("gap_seconds")
            if not isinstance(old_gap, (int, float)):
                continue
            reduction_ms = round((old_gap - current_gap) * 1000)
            if reduction_ms < 100:
                return plan
            reduction = reduction_ms / 1000
            target = plan.actors[1][1]
            fact = (
                f"{plan.event_id}:context:gap-change",
                f"Since the last spoken update, the gap from "
                f"{plan.subject} to {target} decreased by {reduction:.3f} seconds.",
            )
            return replace(
                plan,
                facts=(*plan.facts, fact),
                input_fields=(*plan.input_fields, ("gap_reduction_seconds", reduction)),
            )
        return plan

    def _body(self, cfg: ModelSettings, plan: Microplan) -> dict[str, Any]:
        if cfg.provider == "remote":
            system = M2_SYSTEM
            now_ms = round(self._clock() * 1000)
            recent = tuple(
                {
                    "age_seconds": round((now_ms - row["played_mono_ms"]) / 1000, 1),
                    "text": row["text"],
                    "actors": row["actors"],
                }
                for row in self._played_context
                if row["session_id"] == plan.session_id
                and 0 <= now_ms - row["played_mono_ms"] <= 60000
            )[-3:]
            user = plan.prompt_json(now_ms=now_ms, recent_commentary=recent)
        else:
            system = (
                "Write exactly one of the following independently approved sentences. "
                "Output only that sentence, without quotes or explanation.\n"
                + "\n".join(plan.allowed)
            )
            user = plan.prompt_json()
        return {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "temperature": 0.3 if cfg.provider == "remote" else 0.2,
            "top_p": 1 if cfg.provider == "remote" else 0.8,
            "max_tokens": 192 if cfg.provider == "remote" else cfg.max_tokens,
            "reasoning_effort": "none",
            "n": 1,
        }

    async def _post(
        self, body: dict[str, Any], headers: dict[str, str], timeout_s: float
    ) -> dict[str, Any]:
        # Each request owns its session; cancellation closes the socket and connector.
        cfg = self._settings()
        from irswitch.contracts.config import _validate_url

        try:
            base = _validate_url(
                cfg.base_url, "commentary.llm.base_url", remote=cfg.provider == "remote"
            )
        except ValueError:
            raise ModelFailure("endpoint_invalid") from None
        if not base.endswith("/v1"):
            base += "/v1"
        url = base + "/chat/completions"
        async with aiohttp.ClientSession(
            trust_env=False, timeout=aiohttp.ClientTimeout(total=timeout_s)
        ) as session:
            async with session.post(
                url, json=body, headers=headers, allow_redirects=False
            ) as response:
                if response.status != 200:
                    raise ModelFailure(f"http_{response.status}")
                if response.content_type != "application/json":
                    raise ModelFailure("content_type")
                raw = bytearray()
                async for chunk in response.content.iter_chunked(4096):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise ModelFailure("response_oversize")
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise ModelFailure("response_json") from None
                if not isinstance(result, dict):
                    raise ModelFailure("response_shape")
                return result

    def _text(
        self, cfg: ModelSettings, response: dict[str, Any], plan: Microplan
    ) -> str | ModelSkip:
        try:
            choices = response["choices"]
            if len(choices) != 1 or choices[0]["finish_reason"] != "stop":
                raise ModelFailure("incomplete_response")
            message = choices[0]["message"]
            if message.get("tool_calls") or message.get("refusal"):
                raise ModelFailure("non_speech_response")
            content = message["content"]
            if not isinstance(content, str) or len(content) > 4096:
                raise ModelFailure("response_shape")
            if cfg.provider == "remote":
                data = json.loads(content)
                if set(data) != {"action", "used_fact_ids", "candidates"}:
                    raise ModelFailure("response_shape")
                if data["action"] == "skip":
                    if data["used_fact_ids"] != [] or data["candidates"] != []:
                        raise ModelFailure("response_shape")
                    return ModelSkip()
                if data["action"] != "speak":
                    raise ModelFailure("response_shape")
                used = data["used_fact_ids"]
                allowed = {key for key, _ in plan.facts}
                if (
                    not isinstance(used, list)
                    or not used
                    or any(not isinstance(key, str) or key not in allowed for key in used)
                    or len(used) != len(set(used))
                ):
                    raise ModelFailure("fact_ids_mismatch")
                candidates = data["candidates"]
                if len(candidates) != 1 or set(candidates[0]) != {"style_id", "text"}:
                    raise ModelFailure("response_shape")
                if candidates[0]["style_id"] != "natural":
                    raise ModelFailure("response_shape")
                content = candidates[0]["text"]
            if not isinstance(content, str) or not content.strip() or len(content) > 200:
                raise ModelFailure("response_shape")
            return " ".join(content.split())
        except (KeyError, TypeError, ValueError, IndexError):
            raise ModelFailure("response_shape") from None

    async def realize(self, plan: Microplan) -> str | ModelSkip | None:
        cfg = self._settings()
        started = self._clock()
        if self._closed or not cfg.enabled or self._busy:
            return None
        if plan.digest in self._skipped:
            return ModelSkip()
        if plan.digest in self._attempts:
            return None
        if (
            self._shadow is not None
            and not self._shadow.done()
            and asyncio.current_task() is not self._shadow
        ):
            return None
        if started * 1000 >= plan.expires_ms:
            return None
        self._attempts.append(plan.digest)
        self._total_attempts += 1
        self._busy = True
        if cfg.signature != self._signature:
            self._signature = cfg.signature
            self._generation += 1
        row: dict[str, Any] = {
            "eventId": plan.event_id,
            "beatId": plan.beat_id,
            "revision": plan.revision,
            "bundleHash": plan.digest,
            "configHash": cfg.signature,
            "facts": [{"id": key, "text": text} for key, text in plan.facts],
            "fallbackText": plan.allowed[0],
            "generation": self._generation,
            "mode": cfg.mode,
            "model": cfg.model,
            "startedMonoMs": round(started * 1000),
            "accepted": False,
            "wordingPolicy": cfg.effective_wording_policy,
            "semanticCheck": (
                "not_enforced" if cfg.effective_wording_policy == "experimental_free" else "strict"
            ),
        }
        try:
            headers = self._headers(cfg)
            request_plan = self._request_plan(plan) if cfg.provider == "remote" else plan
            body = self._body(cfg, request_plan)
            row["promptHash"] = digest(body)
            row["facts"] = [{"id": key, "text": text} for key, text in request_plan.facts]
            budget = min(cfg.timeout_s, (plan.expires_ms - started * 1000) / 1000)
            async with asyncio.timeout(budget):
                response = await self._post(body, headers, budget)
            if self._clock() * 1000 >= plan.expires_ms:
                raise ModelFailure("expired")
            if cfg.signature != self._settings().signature:
                raise ModelFailure("config_changed")
            text = self._text(cfg, response, request_plan)
            secret = headers.get("Authorization", "").removeprefix("Bearer ")
            if secret and secret in json.dumps(response):
                raise ModelFailure("credential_echo")
            if isinstance(text, ModelSkip):
                self._skipped.append(plan.digest)
                row.update(accepted=True, reason="model_skip", action="skip")
                return text
            # Keep candidate for shadow audit only after bounded JSON shape validation.
            row["text"] = text
            row["modelReported"] = str(response.get("model", ""))[:128]
            row["strictWouldAccept"] = plan.accepts(text)
            if cfg.effective_wording_policy == "experimental_free":
                shape_reasons = free_wording_reasons(text)
                if shape_reasons:
                    row["shapeReasons"] = shape_reasons
                    raise ModelFailure("speech_shape_rejected")
                grounding_reasons = free_grounding_reasons(text, request_plan)
                row["groundingGuard"] = "passed" if not grounding_reasons else "rejected"
                if grounding_reasons:
                    row["groundingReasons"] = grounding_reasons
                    raise ModelFailure("grounding_rejected")
            elif not row["strictWouldAccept"]:
                raise ModelFailure("semantic_rejected")
            row.update(
                accepted=True,
                reason=(
                    "accepted_experimental_free"
                    if cfg.effective_wording_policy == "experimental_free"
                    else "accepted"
                ),
            )
            return text
        except asyncio.CancelledError:
            row["reason"] = "cancelled"
            raise
        except TimeoutError:
            row["reason"] = "timeout"
        except ModelFailure as error:
            row["reason"] = str(error)
        except Exception:
            # Never log response/exception contents: providers can echo secrets.
            row["reason"] = "transport_error"
        finally:
            completed = self._clock()
            row.update(
                completedMonoMs=round(completed * 1000),
                elapsedMs=round((completed - started) * 1000, 2),
            )
            self._last = row
            self._history.append(row)
            self._busy = False
        return None

    def submit_shadow(self, plan: Microplan) -> bool:
        if self._closed or self._busy or (self._shadow is not None and not self._shadow.done()):
            return False

        async def run() -> None:
            await self.realize(plan)

        self._shadow = asyncio.create_task(run(), name="commentary-model-shadow")
        return True

    def start(self) -> None:
        """Optional, asynchronous preflight with the same endpoint/auth/deadline."""
        self._closed = False
        cfg = self._settings()
        if not cfg.enabled or not cfg.warmup or self._closed or self._shadow is not None:
            return
        self._busy = True
        self._preflight_signature = cfg.signature

        async def preflight() -> None:
            self._busy = True
            self._preflight = "pending"
            try:
                headers = self._headers(cfg)
                body = {
                    "model": cfg.model,
                    "messages": [{"role": "user", "content": "Reply OK only."}],
                    "stream": False,
                    "max_tokens": 16,
                    "reasoning_effort": "none",
                }
                async with asyncio.timeout(cfg.timeout_s):
                    response = await self._post(body, headers, cfg.timeout_s)
                choice = response["choices"][0]
                ok = (
                    choice["finish_reason"] == "stop"
                    and choice["message"]["content"].strip() == "OK"
                )
                self._preflight = (
                    "ready" if ok and cfg.signature == self._settings().signature else "failed"
                )
            except asyncio.CancelledError:
                self._preflight = "cancelled"
                raise
            except Exception:
                self._preflight = "failed"
            finally:
                self._busy = False

        self._shadow = asyncio.create_task(preflight(), name="commentary-model-preflight")

    async def close(self) -> None:
        self._closed = True
        if self._shadow is not None:
            self._shadow.cancel()
            await asyncio.gather(self._shadow, return_exceptions=True)
            self._shadow = None
