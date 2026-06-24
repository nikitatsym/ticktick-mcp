"""Tests for _validate_reminders — covers both the regex (permissive iCal
duration) and the all-day vs timed shape rule."""

import pytest

from ticktick_mcp.prepare import _validate_reminders


class TestAcceptedShapes:
    def test_allday_pt9h(self) -> None:
        _validate_reminders(["TRIGGER:PT9H"], is_all_day=True)

    def test_timed_minus_pt5m(self) -> None:
        _validate_reminders(["TRIGGER:-PT5M"], is_all_day=False)

    def test_timed_compound_hm(self) -> None:
        _validate_reminders(["TRIGGER:-PT1H30M"], is_all_day=False)

    def test_allday_explicit_zeros(self) -> None:
        _validate_reminders(["TRIGGER:P0DT9H0M0S"], is_all_day=True)

    def test_timed_compound_dth(self) -> None:
        _validate_reminders(["TRIGGER:-P1DT2H"], is_all_day=False)

    def test_allday_pt0s(self) -> None:
        _validate_reminders(["TRIGGER:PT0S"], is_all_day=True)


class TestShapeMismatch:
    def test_timed_with_positive_trigger_raises(self) -> None:
        with pytest.raises(ValueError, match="Timed tasks use negative offsets"):
            _validate_reminders(["TRIGGER:PT9H"], is_all_day=False)

    def test_allday_with_negative_trigger_raises(self) -> None:
        with pytest.raises(ValueError, match="All-day tasks use positive offsets"):
            _validate_reminders(["TRIGGER:-PT5M"], is_all_day=True)


class TestFormatErrors:
    def test_garbage(self) -> None:
        with pytest.raises(ValueError, match="Invalid reminder trigger format"):
            _validate_reminders(["GARBAGE"], is_all_day=True)

    def test_empty_trigger_value(self) -> None:
        with pytest.raises(ValueError, match="Invalid reminder trigger format"):
            _validate_reminders(["TRIGGER:"], is_all_day=True)

    def test_no_digits(self) -> None:
        with pytest.raises(ValueError, match="Invalid reminder trigger format"):
            _validate_reminders(["TRIGGER:P"], is_all_day=True)

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError):
            _validate_reminders([42], is_all_day=True)  # type: ignore[list-item]
