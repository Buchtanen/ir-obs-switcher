"""Optional shadow consumer beside CommentaryConsumer (#284).

Default-off peer that can drain an ``EventSubscription`` and admit already
adapted publications through ``NarrativeIngress`` into ``NarrativeMailbox``.
It does not speak, does not replace ``CommentaryConsumer``, and is not spawned
by ``race.runtime`` unless an explicit enabled flag is set.

Not exported from ``events/__init__.py``. No INI / product config key in this
slice — the race flag stays hard-coded ``False`` until a cutover kick.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from irswitch.events.async_fanout import EventSubscription
from irswitch.events.narrative import NarrativeEvent
from irswitch.events.narrative_ingress import IngressAdmission, NarrativeIngress
from irswitch.events.stream import (
    ConfigUpdate,
    FrozenAcceptedEventBatch,
    SessionReset,
    StreamItem,
)

logger = logging.getLogger(__name__)

PublicationAdapter = Callable[[FrozenAcceptedEventBatch], "AdaptedPublication | None"]


@dataclass(frozen=True, slots=True)
class AdaptedPublication:
    """Already-adapted narrative publication ready for NarrativeIngress."""

    timeline: dict[str, Any]
    fact_view: dict[str, Any]
    events: tuple[NarrativeEvent, ...]
    fanout_stream_sequence: int
    command_id_prefix: str
    enqueued_mono_ms: int


@dataclass(frozen=True, slots=True)
class ShadowAdmission:
    accepted: bool
    reason: str
    command_ids: tuple[str, ...]
    mailbox_sequences: tuple[int, ...]
    effects: tuple[str, ...]


class NarrativeShadowConsumer:
    """Shadow peer for CommentaryConsumer; library/test path first."""

    def __init__(
        self,
        subscription: EventSubscription | None = None,
        *,
        enabled: bool = False,
        ingress: NarrativeIngress | None = None,
        publication_adapter: PublicationAdapter | None = None,
    ) -> None:
        self.subscription = subscription
        self.enabled = bool(enabled)
        self.ingress = NarrativeIngress() if ingress is None else ingress
        self.publication_adapter = publication_adapter
        self.running = False
        self.processed = 0
        self.skipped = 0
        self.failures = 0
        self.last_error: str | None = None
        self.last_stream_sequence = 0
        self.last_admission: ShadowAdmission | None = None

    def handle_adapted_publication(self, publication: AdaptedPublication) -> ShadowAdmission:
        if not self.enabled:
            result = ShadowAdmission(
                accepted=False,
                reason="shadow_disabled",
                command_ids=(),
                mailbox_sequences=(),
                effects=("shadow_disabled",),
            )
            self.last_admission = result
            return result
        admitted = self.ingress.admit_context_publication(
            timeline=publication.timeline,
            fact_view=publication.fact_view,
            events=publication.events,
            fanout_stream_sequence=publication.fanout_stream_sequence,
            command_id_prefix=publication.command_id_prefix,
            enqueued_mono_ms=publication.enqueued_mono_ms,
        )
        result = _from_ingress(admitted)
        self.last_admission = result
        if result.accepted:
            self.processed += 1
        else:
            self.skipped += 1
        return result

    async def handle(self, item: StreamItem) -> ShadowAdmission | None:
        if not self.enabled:
            return None
        self.last_stream_sequence = int(getattr(item, "stream_sequence", 0) or 0)
        if isinstance(item, (SessionReset, ConfigUpdate)):
            self.skipped += 1
            result = ShadowAdmission(
                accepted=False,
                reason="shadow_non_batch",
                command_ids=(),
                mailbox_sequences=(),
                effects=("shadow_non_batch",),
            )
            self.last_admission = result
            return result
        if not isinstance(item, FrozenAcceptedEventBatch):
            self.skipped += 1
            result = ShadowAdmission(
                accepted=False,
                reason="shadow_unknown_item",
                command_ids=(),
                mailbox_sequences=(),
                effects=("shadow_unknown_item",),
            )
            self.last_admission = result
            return result
        adapter = self.publication_adapter
        if adapter is None:
            self.skipped += 1
            result = ShadowAdmission(
                accepted=False,
                reason="shadow_adapter_missing",
                command_ids=(),
                mailbox_sequences=(),
                effects=("shadow_adapter_missing",),
            )
            self.last_admission = result
            return result
        publication = adapter(item)
        if publication is None:
            self.skipped += 1
            result = ShadowAdmission(
                accepted=False,
                reason="shadow_adapter_skipped",
                command_ids=(),
                mailbox_sequences=(),
                effects=("shadow_adapter_skipped",),
            )
            self.last_admission = result
            return result
        return self.handle_adapted_publication(publication)

    async def run(self) -> None:
        if not self.enabled:
            self.running = False
            return
        if self.subscription is None:
            raise RuntimeError("NarrativeShadowConsumer.run requires a subscription when enabled")
        self.running = True
        try:
            while True:
                try:
                    item = await asyncio.wait_for(self.subscription.get(), timeout=0.2)
                except TimeoutError:
                    continue
                try:
                    await self.handle(item)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.failures += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning(
                        "narrative shadow consumer failed for one item",
                        exc_info=True,
                    )
        finally:
            self.running = False


def _from_ingress(admitted: IngressAdmission) -> ShadowAdmission:
    effects = ("shadow_ingress",) + tuple(admitted.effects)
    return ShadowAdmission(
        accepted=bool(admitted.accepted),
        reason=str(admitted.reason),
        command_ids=tuple(admitted.command_ids),
        mailbox_sequences=tuple(admitted.mailbox_sequences),
        effects=effects,
    )
