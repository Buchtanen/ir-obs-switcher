"""Tests for TaskRegistry."""

from __future__ import annotations

import asyncio

import pytest

from irswitch.server.task_registry import TaskRegistry


@pytest.fixture
def registry() -> TaskRegistry:
    return TaskRegistry()


@pytest.mark.asyncio
async def test_spawn_registers_task(registry: TaskRegistry) -> None:
    started = asyncio.Event()
    finished = asyncio.Event()

    async def work() -> None:
        started.set()
        await finished.wait()

    task = registry.spawn("work", work())
    await started.wait()
    assert "work" in registry
    assert len(registry) == 1
    assert not task.done()

    finished.set()
    await task
    assert "work" not in registry
    assert len(registry) == 0


@pytest.mark.asyncio
async def test_done_callback_removes_task(registry: TaskRegistry) -> None:
    async def quick() -> str:
        return "ok"

    task = registry.spawn("quick", quick())
    assert await task == "ok"
    # Allow done callback to run
    await asyncio.sleep(0)
    assert "quick" not in registry


@pytest.mark.asyncio
async def test_replace_cancels_previous(registry: TaskRegistry) -> None:
    first_started = asyncio.Event()
    first_cancelled = asyncio.Event()

    async def long_running() -> None:
        first_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            first_cancelled.set()
            raise

    async def replacement() -> str:
        return "new"

    first = registry.spawn("named", long_running())
    await first_started.wait()

    second = registry.spawn("named", replacement(), replace=True)
    await first_cancelled.wait()
    assert first.cancelled()
    assert await second == "new"
    await asyncio.sleep(0)
    assert "named" not in registry


@pytest.mark.asyncio
async def test_replace_false_keeps_existing(registry: TaskRegistry) -> None:
    gate = asyncio.Event()

    async def first_work() -> str:
        await gate.wait()
        return "first"

    async def second_work() -> str:
        return "second"

    first = registry.spawn("named", first_work())
    second = registry.spawn("named", second_work(), replace=False)
    assert second is first
    assert len(registry) == 1

    gate.set()
    assert await first == "first"
    await asyncio.sleep(0)
    assert "named" not in registry


@pytest.mark.asyncio
async def test_cancel_by_name(registry: TaskRegistry) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def work() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = registry.spawn("work", work())
    await started.wait()
    registry.cancel("work")
    await cancelled.wait()
    assert task.cancelled()
    await asyncio.sleep(0)
    assert "work" not in registry


@pytest.mark.asyncio
async def test_cancel_missing_is_noop(registry: TaskRegistry) -> None:
    registry.cancel("missing")


@pytest.mark.asyncio
async def test_cancel_all(registry: TaskRegistry) -> None:
    started = asyncio.Event()
    count = 0

    async def work() -> None:
        nonlocal count
        count += 1
        if count == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise

    t1 = registry.spawn("a", work())
    t2 = registry.spawn("b", work())
    await started.wait()
    assert len(registry) == 2

    await registry.cancel_all()
    assert t1.cancelled()
    assert t2.cancelled()
    assert len(registry) == 0
