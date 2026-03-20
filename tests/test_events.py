"""Tests for event bus."""

import pytest

from app.core.events import Event, EventBus


@pytest.mark.asyncio
async def test_publish_subscribe():
    bus = EventBus()
    received = []

    async def handler(event: Event):
        received.append(event)

    bus.subscribe("test.event", handler)
    await bus.publish(Event(type="test.event", payload={"key": "value"}))

    assert len(received) == 1
    assert received[0].payload["key"] == "value"


@pytest.mark.asyncio
async def test_no_handler():
    bus = EventBus()
    # Should not raise
    await bus.publish(Event(type="unhandled.event"))


@pytest.mark.asyncio
async def test_multiple_handlers():
    bus = EventBus()
    results = []

    async def handler1(event: Event):
        results.append("h1")

    async def handler2(event: Event):
        results.append("h2")

    bus.subscribe("multi", handler1)
    bus.subscribe("multi", handler2)
    await bus.publish(Event(type="multi"))

    assert "h1" in results
    assert "h2" in results


@pytest.mark.asyncio
async def test_handler_error_doesnt_break_others():
    bus = EventBus()
    results = []

    async def bad_handler(event: Event):
        raise ValueError("oops")

    async def good_handler(event: Event):
        results.append("ok")

    bus.subscribe("err", bad_handler)
    bus.subscribe("err", good_handler)
    await bus.publish(Event(type="err"))

    assert "ok" in results


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    results = []

    async def handler(event: Event):
        results.append(1)

    bus.subscribe("unsub", handler)
    bus.unsubscribe("unsub", handler)
    await bus.publish(Event(type="unsub"))

    assert len(results) == 0
