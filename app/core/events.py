"""In-process event bus. Simple pub/sub for decoupling modules.

No external broker needed — just async callbacks.
For future: swap to Redis Streams or RabbitMQ if needed.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Coroutine[Any, Any, None]]


@dataclass
class Event:
    """Base event."""
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actor_id: int | None = None


class EventBus:
    """Simple async event bus. Handlers are called concurrently."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Event handler failed: event=%s handler=%s error=%s",
                    event.type,
                    handlers[i].__name__,
                    result,
                )


# Global event bus instance
event_bus = EventBus()
