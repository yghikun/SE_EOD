"""Resource ownership states shared by intra- and interprocedural analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResourceState(str, Enum):
    UNSEEN = "UNSEEN"
    ACQUIRED = "ACQUIRED"
    BORROWED = "BORROWED"
    TRANSFERRED = "TRANSFERRED"
    RELEASED = "RELEASED"
    ESCAPED = "ESCAPED"
    UNKNOWN = "UNKNOWN"


class ResourceAction(str, Enum):
    ACQUIRE = "acquire"
    BORROW = "borrow"
    TRANSFER = "transfer"
    RELEASE = "release"
    ESCAPE = "escape"
    UNKNOWN = "unknown"


_TRANSITIONS: dict[tuple[ResourceState, ResourceAction], ResourceState] = {
    (ResourceState.UNSEEN, ResourceAction.ACQUIRE): ResourceState.ACQUIRED,
    (ResourceState.UNSEEN, ResourceAction.BORROW): ResourceState.BORROWED,
    (ResourceState.ACQUIRED, ResourceAction.RELEASE): ResourceState.RELEASED,
    (ResourceState.ACQUIRED, ResourceAction.TRANSFER): ResourceState.TRANSFERRED,
    (ResourceState.ACQUIRED, ResourceAction.ESCAPE): ResourceState.ESCAPED,
    (ResourceState.BORROWED, ResourceAction.RELEASE): ResourceState.UNKNOWN,
    (ResourceState.BORROWED, ResourceAction.TRANSFER): ResourceState.TRANSFERRED,
    (ResourceState.BORROWED, ResourceAction.ESCAPE): ResourceState.ESCAPED,
}


def transition(state: ResourceState, action: ResourceAction) -> ResourceState:
    """Apply one conservative ownership transition."""

    if action is ResourceAction.UNKNOWN or state is ResourceState.UNKNOWN:
        return ResourceState.UNKNOWN
    return _TRANSITIONS.get((state, action), ResourceState.UNKNOWN)


def join_states(left: ResourceState, right: ResourceState) -> ResourceState:
    """Join states from two paths without claiming an unsafe definite result."""

    if left is right:
        return left
    if left is ResourceState.UNSEEN or right is ResourceState.UNSEEN:
        return ResourceState.UNKNOWN
    return ResourceState.UNKNOWN


@dataclass(frozen=True)
class ResourceViolation:
    kind: str
    state: ResourceState
    message: str


def error_path_violation(state: ResourceState) -> ResourceViolation | None:
    if state is ResourceState.ACQUIRED:
        return ResourceViolation(
            kind="missing_cleanup",
            state=state,
            message="owned resource reaches an error return without release or transfer",
        )
    return None
