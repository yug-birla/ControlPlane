"""Event transport -- ``component -> event -> transport -> consumer``.

In-process and synchronous: the smallest real mechanism that satisfies
the contract for this milestone's scale. Deliberately behind an
interface so a later layer can swap in a Redis Streams-backed transport
(docs/DATA/QDRANT_REDIS_DATA_CONTRACT.md SS17-19) without changing any
publisher or consumer.

The transport carries events only -- it must never contain routing or
recovery policy (EVENT_MODEL.md: "Do NOT allow the event bus itself to
contain business policy"). Consumers registered here (e.g. EventStore)
must not make control decisions; only controlplane.runtime does that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from controlplane.events.schema import Event

EventHandler = Callable[[Event], None]


class EventTransport(ABC):
    @abstractmethod
    def subscribe(self, handler: EventHandler) -> None: ...

    @abstractmethod
    def publish(self, event: Event) -> None: ...


class InProcessEventTransport(EventTransport):
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers:
            handler(event)
