"""Failure mode #2: isAllDay silently flips when reminders are added.

The fix is fail-fast: UpdateTask requires isAllDay explicitly when
reminders/startDate/dueDate change. CreateTask either infers isAllDay
from date shape or requires it explicitly when reminders are passed.
"""

import pytest

from ticktick_mcp.prepare import _prepare_task


class TestUpdateFailFast:
    def test_reminders_without_isallday_raises(self) -> None:
        with pytest.raises(ValueError, match="isAllDay must be passed explicitly"):
            _prepare_task(
                {"projectId": "p1", "title": "T", "reminders": ["TRIGGER:-PT5M"]},
                is_update=True,
            )

    def test_startdate_without_isallday_raises(self) -> None:
        with pytest.raises(ValueError, match="isAllDay must be passed explicitly"):
            _prepare_task(
                {"projectId": "p1", "startDate": "2026-03-15T10:00:00", "timeZone": "Europe/Berlin"},
                is_update=True,
            )

    def test_duedate_without_isallday_raises(self) -> None:
        with pytest.raises(ValueError, match="isAllDay must be passed explicitly"):
            _prepare_task(
                {"projectId": "p1", "dueDate": "2026-03-15T10:00:00", "timeZone": "Europe/Berlin"},
                is_update=True,
            )

    def test_allday_true_with_positive_trigger_passes(self) -> None:
        task = _prepare_task(
            {
                "projectId": "p1",
                "isAllDay": True,
                "reminders": ["TRIGGER:PT9H"],
            },
            is_update=True,
        )
        assert task["isAllDay"] is True
        assert task["reminders"] == ["TRIGGER:PT9H"]

    def test_allday_true_with_negative_trigger_raises(self) -> None:
        with pytest.raises(ValueError, match="All-day tasks use positive offsets"):
            _prepare_task(
                {
                    "projectId": "p1",
                    "isAllDay": True,
                    "reminders": ["TRIGGER:-PT5M"],
                },
                is_update=True,
            )

    def test_allday_false_with_positive_trigger_raises(self) -> None:
        with pytest.raises(ValueError, match="Timed tasks use negative offsets"):
            _prepare_task(
                {
                    "projectId": "p1",
                    "isAllDay": False,
                    "reminders": ["TRIGGER:PT9H"],
                },
                is_update=True,
            )

    def test_dateonly_duedate_implies_allday_no_failfast(self) -> None:
        """Date-only dueDate implies isAllDay=True even on UpdateTask, so the
        fail-fast rule should NOT trigger (inferred mode is enough)."""
        task = _prepare_task(
            {"projectId": "p1", "dueDate": "2026-03-15"},
            is_update=True,
        )
        assert task["isAllDay"] is True


class TestCreateInference:
    def test_reminders_with_dateonly_infers_allday_true(self) -> None:
        task = _prepare_task(
            {"title": "T", "brief": "B", "dueDate": "2026-03-15", "reminders": ["TRIGGER:PT9H"]}
        )
        assert task["isAllDay"] is True
        assert task["reminders"] == ["TRIGGER:PT9H"]

    def test_reminders_with_timeofday_infers_allday_false(self) -> None:
        task = _prepare_task(
            {
                "title": "T",
                "brief": "B",
                "dueDate": "2026-03-15T19:00",
                "timeZone": "Europe/Berlin",
                "reminders": ["TRIGGER:-PT5M"],
            }
        )
        assert task["isAllDay"] is False
        assert task["reminders"] == ["TRIGGER:-PT5M"]

    def test_reminders_without_date_or_allday_raises(self) -> None:
        with pytest.raises(ValueError, match="reminders requires isAllDay"):
            _prepare_task({"title": "T", "brief": "B", "reminders": ["TRIGGER:PT9H"]})

    def test_reminders_with_explicit_allday_passes(self) -> None:
        task = _prepare_task(
            {"title": "T", "brief": "B", "isAllDay": True, "reminders": ["TRIGGER:PT9H"]}
        )
        assert task["isAllDay"] is True

    def test_reminders_with_dateonly_validates_triggers(self) -> None:
        with pytest.raises(ValueError, match="All-day tasks use positive offsets"):
            _prepare_task(
                {"title": "T", "brief": "B", "dueDate": "2026-03-15", "reminders": ["TRIGGER:-PT5M"]}
            )
