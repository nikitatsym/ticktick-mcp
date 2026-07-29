"""Tests for TickTick date parsing in the today filter."""

from datetime import datetime, timezone

import pytest

from ticktick_mcp.client import TickTickClient

# ── _parse_date ──────────────────────────────────────────────────────────────


class TestParseDate:
    def test_absent_date_is_none(self) -> None:
        assert TickTickClient._parse_date(None) is None
        assert TickTickClient._parse_date("") is None

    def test_ticktick_utc_format(self) -> None:
        assert TickTickClient._parse_date("2026-01-15T09:00:00.000+0000") == datetime(
            2026, 1, 15, 9, 0, tzinfo=timezone.utc,
        )

    def test_unparseable_date_raises_instead_of_dropping_the_task(self) -> None:
        """None here would silently shrink a filter that promises every match."""
        with pytest.raises(ValueError, match="unparseable TickTick date"):
            TickTickClient._parse_date("15 January 2026")

    def test_the_error_names_the_offending_value_and_task(self) -> None:
        with pytest.raises(ValueError, match=r"'nonsense'.*on task abc123"):
            TickTickClient._parse_date("nonsense", "abc123")
