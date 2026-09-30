"""
Border Intelligence EventBus Module.
Lightweight, thread-safe, asynchronous in-memory EventBus for real-time pub/sub.
"""
import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Set
from backend.events.schema import BaseEvent, EventType

SubscriberCallback = Callable[[BaseEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Asynchronous in-memory EventBus supporting wildcard and typed subscriptions."""

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, Set[SubscriberCallback]] = {}
        self._wildcard_subscribers: Set[SubscriberCallback] = set()
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        callback: SubscriberCallback,
        event_type: EventType | None = None,
    ) -> None:
        """Subscribe a callback to a specific EventType, or all events if event_type is None."""
        async with self._lock:
            if event_type is None:
                self._wildcard_subscribers.add(callback)
            else:
                if event_type not in self._subscribers:
                    self._subscribers[event_type] = set()
                self._subscribers[event_type].add(callback)

    async def unsubscribe(
        self,
        callback: SubscriberCallback,
        event_type: EventType | None = None,
    ) -> None:
        """Unsubscribe a callback."""
        async with self._lock:
            if event_type is None:
                self._wildcard_subscribers.discard(callback)
            else:
                if event_type in self._subscribers:
                    self._subscribers[event_type].discard(callback)

    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to all matching subscribers concurrently in the background.
        Isolated: slow subscribers or exceptions never block or crash the publisher.
        """
        callbacks: List[SubscriberCallback] = []
        async with self._lock:
            callbacks.extend(self._wildcard_subscribers)
            if event.event_type in self._subscribers:
                callbacks.extend(self._subscribers[event.event_type])

        if not callbacks:
            return

        tasks = [self._safe_invoke(cb, event) for cb in callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _safe_invoke(callback: SubscriberCallback, event: BaseEvent) -> None:
        try:
            await callback(event)
        except Exception as err:
            import logging
            logging.getLogger(__name__).warning(f"EventBus subscriber {callback} error on {event.event_type}: {err}")


# Global singleton instance
global_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return global_event_bus
