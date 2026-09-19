"""One bounded nonblocking mailbox for every NarrativeRuntime command."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from threading import Lock
from typing import Any

from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.context import ContextBatchPart
from irswitch.contracts.primitives import ContractViolation, canonical_sha256


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    accepted: bool
    reason: str
    command: NarrativeCommand
    evicted_command_ids: tuple[str, ...] = ()
    evicted_commands: tuple[NarrativeCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class BundleAdmissionResult:
    accepted: bool
    reason: str
    commands: tuple[NarrativeCommand, ...]
    recovery: NarrativeCommand | None = None


class NarrativeMailbox:
    """Single ordered container with 56/7/1 admission reservations."""

    ORDINARY_CELLS = 56
    PROTECTED_CELLS = 7
    EMERGENCY_CELLS = 1
    TOTAL_CAPACITY = 64

    def __init__(self) -> None:
        self._items: list[NarrativeCommand] = []
        self._next_sequence = 1
        self._lock = Lock()
        self._latest_context: ContextBatchPart | None = None
        self._ingress_closed = False
        self._shutdown_recovery: dict[str, Any] | None = None

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def recovery(self) -> NarrativeCommand | None:
        with self._lock:
            return self._find_kind("MAILBOX_RECOVERY")

    @property
    def shutdown_recovery(self) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._shutdown_recovery)

    def snapshot(self) -> tuple[NarrativeCommand, ...]:
        with self._lock:
            return tuple(sorted(self._items, key=lambda item: item.mailbox_sequence))

    def dequeue(self) -> NarrativeCommand | None:
        with self._lock:
            if not self._items:
                return None
            index = min(
                range(len(self._items)), key=lambda item: self._items[item].mailbox_sequence
            )
            return self._items.pop(index)

    def admit(self, command: NarrativeCommand) -> AdmissionResult:
        if not isinstance(command, NarrativeCommand):
            raise ContractViolation("NarrativeMailbox accepts only NarrativeCommand")
        if command.mailbox_sequence != 0:
            raise ContractViolation("producer must not assign mailboxSequence")
        with self._lock:
            if command.kind == "SHUTDOWN":
                return self._admit_shutdown(command)
            if self._ingress_closed:
                return AdmissionResult(False, "ingress_closed", command)
            duplicate = self._find_command_id(str(command.command_id))
            if duplicate is not None:
                if duplicate.fingerprint != command.fingerprint:
                    raise ContractViolation("duplicate commandId carries conflicting content")
                return AdmissionResult(True, "duplicate", duplicate)
            coalesced = self._coalesce(command)
            if coalesced is not None:
                return AdmissionResult(True, "coalesced", coalesced)
            if command.protected:
                return self._admit_protected(command)
            return self._admit_ordinary(command)

    def admit_bundle(
        self, control: NarrativeCommand, context: NarrativeCommand
    ) -> BundleAdmissionResult:
        """Atomically admit a protected control/context pair or one recovery barrier."""
        if control.kind not in {"CONFIG_UPDATE", "TAPE_HEALTH_CHANGED"}:
            raise ContractViolation("atomic bundle requires config or tape-health control")
        if context.kind != "APPLY_CONTEXT_BATCH" or context.context_part is None:
            raise ContractViolation("atomic bundle requires an APPLY_CONTEXT_BATCH second")
        if not control.protected or not context.protected:
            raise ContractViolation("atomic bundle members must both be protected")
        if control.mailbox_sequence != 0 or context.mailbox_sequence != 0:
            raise ContractViolation("producer must not assign mailboxSequence")
        with self._lock:
            if self._ingress_closed:
                return BundleAdmissionResult(False, "ingress_closed", ())
            if (
                self._find_command_id(str(control.command_id)) is not None
                or self._find_command_id(str(context.command_id)) is not None
            ):
                raise ContractViolation("atomic bundle commandId is already queued")
            if self._protected_used() <= self.PROTECTED_CELLS - 2:
                first = self._append(control)
                second = self._append(context)
                self._latest_context = context.context_part
                return BundleAdmissionResult(True, "accepted", (first, second))
            first_loss = self._take_sequence()
            last_loss = self._take_sequence()
            recovery = self._place_recovery(
                latest_context=context.context_part,
                loss_sequence=first_loss,
                loss_last_sequence=last_loss,
                safety_effects=(control.safety_effect(), context.safety_effect()),
                observed_mono_ms=max(int(control.enqueued_mono_ms), int(context.enqueued_mono_ms)),
            )
            self._latest_context = context.context_part
            return BundleAdmissionResult(True, "mailbox_recovery", (recovery,), recovery=recovery)

    def _admit_ordinary(self, command: NarrativeCommand) -> AdmissionResult:
        if self._ordinary_used() < self.ORDINARY_CELLS:
            stamped = self._append(command)
            if command.context_part is not None:
                self._latest_context = command.context_part
            return AdmissionResult(True, "accepted", stamped)
        if command.kind == "MANUAL_SPEAK_REQUEST":
            return AdmissionResult(False, "mailbox_overloaded", command)
        if command.kind == "VALIDITY_DEADLINE_ELAPSED":
            return AdmissionResult(False, "deadline_admission_skipped", command)
        if command.kind != "APPLY_CONTEXT_BATCH" or command.context_part is None:
            return AdmissionResult(False, "mailbox_overloaded", command)
        silence_index = self._oldest_index(
            lambda item: not item.protected and item.kind == "LONG_SILENCE_ELAPSED"
        )
        if silence_index is not None:
            evicted = self._items.pop(silence_index)
            stamped = self._append(command)
            self._latest_context = command.context_part
            return AdmissionResult(
                True,
                "mailbox_evicted_update",
                stamped,
                (str(evicted.command_id),),
                (evicted,),
            )
        context_index = self._oldest_index(
            lambda item: not item.protected and item.kind == "APPLY_CONTEXT_BATCH"
        )
        if context_index is None:
            return AdmissionResult(False, "mailbox_overloaded", command)
        evicted = self._items.pop(context_index)
        recovery = self._place_recovery(
            latest_context=command.context_part,
            loss_sequence=evicted.mailbox_sequence,
            safety_effects=(
                {
                    "kind": "MAILBOX_RECOVERY",
                    "identity": str(evicted.command_id),
                    "payloadHash": evicted.fingerprint,
                },
            ),
            observed_mono_ms=int(command.enqueued_mono_ms),
        )
        self._latest_context = command.context_part
        return AdmissionResult(
            True,
            "mailbox_recovery",
            recovery,
            (str(evicted.command_id),),
            (evicted,),
        )

    def _admit_protected(self, command: NarrativeCommand) -> AdmissionResult:
        if self._protected_used() < self.PROTECTED_CELLS:
            stamped = self._append(command)
            if command.context_part is not None:
                self._latest_context = command.context_part
            return AdmissionResult(True, "accepted", stamped)
        if self._latest_context is None:
            return AdmissionResult(False, "recovery_context_unavailable", command)
        lost_sequence = self._take_sequence()
        recovery = self._place_recovery(
            latest_context=self._latest_context,
            loss_sequence=lost_sequence,
            safety_effects=(command.safety_effect(),),
            observed_mono_ms=int(command.enqueued_mono_ms),
        )
        return AdmissionResult(True, "mailbox_recovery", recovery)

    def _place_recovery(
        self,
        *,
        latest_context: ContextBatchPart,
        loss_sequence: int,
        safety_effects: tuple[dict[str, str], ...],
        observed_mono_ms: int,
        loss_last_sequence: int | None = None,
    ) -> NarrativeCommand:
        existing = self._find_kind("MAILBOX_RECOVERY")
        if existing is None:
            recovery = NarrativeCommand.recovery(
                f"mailbox:recovery:{loss_sequence}",
                observed_mono_ms,
                latest_context=latest_context,
                loss_first_sequence=loss_sequence,
                loss_last_sequence=(
                    loss_sequence if loss_last_sequence is None else loss_last_sequence
                ),
                safety_effects=safety_effects,
            )
            return self._append(recovery)
        payload = existing.payload
        effects = tuple(payload["safetyEffects"])
        for safety_effect in safety_effects:
            if safety_effect not in effects:
                effects = (*effects, safety_effect)
        if len(effects) > 64:
            compacted = {
                "kind": "MAILBOX_RECOVERY",
                "identity": "safety-effects:compacted",
                "payloadHash": str(canonical_sha256(list(effects[:-63]))),
            }
            effects = (compacted, *effects[-63:])
        loss_last = loss_sequence if loss_last_sequence is None else loss_last_sequence
        refreshed = NarrativeCommand.recovery(
            str(existing.command_id),
            observed_mono_ms,
            latest_context=latest_context,
            loss_first_sequence=min(payload["lossFirstMailboxSequence"], loss_sequence),
            loss_last_sequence=max(payload["lossLastMailboxSequence"], loss_last),
            safety_effects=effects,
            mailbox_sequence=existing.mailbox_sequence,
        )
        self._replace(existing, refreshed)
        return refreshed

    def _admit_shutdown(self, command: NarrativeCommand) -> AdmissionResult:
        existing_shutdown = self._find_kind("SHUTDOWN")
        if existing_shutdown is not None:
            if existing_shutdown.fingerprint != command.fingerprint:
                raise ContractViolation("shutdown singleton carries conflicting content")
            self._ingress_closed = True
            return AdmissionResult(True, "duplicate", existing_shutdown)
        recovery = self._find_kind("MAILBOX_RECOVERY")
        if recovery is not None:
            self._shutdown_recovery = recovery.payload
            self._items.remove(recovery)
            stamped = command.with_mailbox_sequence(recovery.mailbox_sequence)
            self._items.append(stamped)
        else:
            stamped = self._append(command)
        self._ingress_closed = True
        return AdmissionResult(True, "accepted", stamped)

    def _coalesce(self, command: NarrativeCommand) -> NarrativeCommand | None:
        key = command.coalesce_key
        if key is None:
            return None
        for existing in self._items:
            if existing.coalesce_key == key:
                refreshed = command.with_mailbox_sequence(existing.mailbox_sequence)
                self._replace(existing, refreshed)
                return refreshed
        return None

    def _append(self, command: NarrativeCommand) -> NarrativeCommand:
        if len(self._items) >= self.TOTAL_CAPACITY:
            raise ContractViolation("NarrativeMailbox capacity invariant violated")
        stamped = command.with_mailbox_sequence(self._take_sequence())
        self._items.append(stamped)
        return stamped

    def _take_sequence(self) -> int:
        sequence = self._next_sequence
        self._next_sequence += 1
        return sequence

    def _ordinary_used(self) -> int:
        return sum(
            not item.protected and item.kind not in {"MAILBOX_RECOVERY", "SHUTDOWN"}
            for item in self._items
        )

    def _protected_used(self) -> int:
        return sum(
            item.protected and item.kind not in {"MAILBOX_RECOVERY", "SHUTDOWN"}
            for item in self._items
        )

    def _find_kind(self, kind: str) -> NarrativeCommand | None:
        return next((item for item in self._items if item.kind == kind), None)

    def _find_command_id(self, command_id: str) -> NarrativeCommand | None:
        return next((item for item in self._items if item.command_id == command_id), None)

    def _oldest_index(self, predicate: Any) -> int | None:
        candidates = [
            (index, item.mailbox_sequence)
            for index, item in enumerate(self._items)
            if predicate(item)
        ]
        return min(candidates, key=lambda value: value[1])[0] if candidates else None

    def _replace(self, previous: NarrativeCommand, current: NarrativeCommand) -> None:
        self._items[self._items.index(previous)] = current
