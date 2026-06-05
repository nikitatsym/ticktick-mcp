"""TypedDict shapes for TickTick API responses.

Every field is `NotRequired` — TickTick omits fields rather than returning
null, so the safe stance is "anything could be missing." `NotRequired` comes
from `typing_extensions` (not `typing`) because we target Python 3.10, where
the stdlib variant is only available from 3.11+.
"""

from __future__ import annotations

from typing_extensions import NotRequired, TypedDict


class ItemDict(TypedDict, total=False):
    """A checklist sub-item within a task."""
    id: NotRequired[str]
    title: NotRequired[str]
    status: NotRequired[int]


class TaskDict(TypedDict, total=False):
    """TickTick task as returned by the Open API."""
    id: NotRequired[str]
    projectId: NotRequired[str]
    title: NotRequired[str]
    content: NotRequired[str]
    desc: NotRequired[str]
    status: NotRequired[int]
    priority: NotRequired[int]
    startDate: NotRequired[str]
    dueDate: NotRequired[str]
    isAllDay: NotRequired[bool]
    timeZone: NotRequired[str]
    tags: NotRequired[list[str]]
    reminders: NotRequired[list[str]]
    repeatFlag: NotRequired[str]
    items: NotRequired[list[ItemDict]]
    parentId: NotRequired[str]
    childIds: NotRequired[list[str]]
    sortOrder: NotRequired[int]
    etag: NotRequired[str]
    modifiedTime: NotRequired[str]
    completedTime: NotRequired[str]
    kind: NotRequired[str]
    columnId: NotRequired[str]


class SlimTaskDict(TypedDict, total=False):
    """Compact task projection for list views."""
    id: NotRequired[str]
    projectId: NotRequired[str]
    title: NotRequired[str]
    status: NotRequired[int]
    priority: NotRequired[int]
    dueDate: NotRequired[str]
    tags: NotRequired[list[str]]
    parentId: NotRequired[str]
    childIds: NotRequired[list[str]]


class ProjectDict(TypedDict, total=False):
    """TickTick project as returned by the Open API."""
    id: NotRequired[str]
    name: NotRequired[str]
    color: NotRequired[str]
    viewMode: NotRequired[str]
    kind: NotRequired[str]
    closed: NotRequired[bool]
    groupId: NotRequired[str]
    sortOrder: NotRequired[int]
    permission: NotRequired[str]


class ProjectDataDict(TypedDict, total=False):
    """`/project/{id}/data` response shape: project + tasks + columns."""
    project: NotRequired[ProjectDict]
    tasks: NotRequired[list[TaskDict]]
    columns: NotRequired[list[dict[str, object]]]


class TzMeta(TypedDict):
    """Wrapper metadata describing the timezone actually used for a write op."""
    used: str
    source: str
