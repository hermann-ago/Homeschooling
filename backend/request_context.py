"""Per-request operation identity shared with synchronous route handlers."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

_current: ContextVar["RequestContext | None"] = ContextVar("homeschooling_request", default=None)


@dataclass
class RequestContext:
    key: str
    device_label: str | None = None
    operation_ids: list[str] = field(default_factory=list)

    def next_operation_id(self) -> str:
        operation_id = self.key if not self.operation_ids else f"{self.key}:{len(self.operation_ids) + 1}"
        self.operation_ids.append(operation_id)
        return operation_id


def begin(context: RequestContext):
    return _current.set(context)


def end(token):
    _current.reset(token)


def current() -> RequestContext | None:
    return _current.get()


def operation_id() -> str | None:
    context = current()
    return context.next_operation_id() if context else None


def device_label() -> str | None:
    context = current()
    return context.device_label if context else None
