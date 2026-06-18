"""Tests for the guest table-session logic.

Covers the requirement that once staff closes a guest's table, the guest's
session is invalidated and they must scan the QR code again before ordering.
"""
from unittest.mock import AsyncMock

import pytest

from database.models import WaiterAssignment
from handlers.guest_handlers import _require_active_table, _invalidate_session


class _FakeState:
    """A minimal stand-in for aiogram's FSMContext for unit tests."""

    def __init__(self, data=None):
        self._data = dict(data or {})

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)


@pytest.fixture
def open_assignment():
    return WaiterAssignment(
        id=1,
        waiter_id=2,
        table_number=5,
        status="open",
        assigned_at="2024-01-01T12:00:00",
        payment_status="unpaid",
    )


@pytest.fixture
def reopened_assignment():
    """A new (reopened) assignment for the same table, different timestamp."""
    return WaiterAssignment(
        id=2,
        waiter_id=3,
        table_number=5,
        status="open",
        assigned_at="2024-06-18T16:00:00",
        payment_status="unpaid",
    )


def _table_service(open_assignment=None, new_assignment=None):
    """Build a mock TableService with configurable get_open/auto_assign results."""
    ts = AsyncMock()
    ts.get_open_assignment = AsyncMock(return_value=open_assignment)
    ts.auto_assign_waiter = AsyncMock(return_value=new_assignment)
    return ts


class TestNoTableNumber:
    async def test_no_table_number_asks_to_scan(self):
        """A guest with no table_number at all is asked to scan the QR code."""
        state = _FakeState({})  # no table_number, no token
        ts = _table_service()
        respond = AsyncMock()

        result = await _require_active_table(state, ts, respond)

        assert result is None
        respond.assert_awaited_once()
        assert "QR-код" in respond.call_args.args[0]
        ts.get_open_assignment.assert_not_called()


class TestFreshSession:
    """Guest scanned but hasn't checked out / paid yet (token is None)."""

    async def test_fresh_open_table_latches_token(self, open_assignment):
        """A fresh guest at an already-open table latches onto its token."""
        state = _FakeState({"table_number": 5, "session_assigned_at": None})
        ts = _table_service(open_assignment=open_assignment)
        respond = AsyncMock()

        result = await _require_active_table(state, ts, respond)

        assert result == 5
        # Token captured for future close/reopen detection.
        assert state._data["session_assigned_at"] == open_assignment.assigned_at

    async def test_fresh_closed_table_browsing_allowed(self):
        """A fresh guest at a closed table may still browse the menu.

        No token is captured; the table will be opened on checkout/payment.
        """
        state = _FakeState({"table_number": 5, "session_assigned_at": None})
        ts = _table_service(open_assignment=None)
        respond = AsyncMock()

        result = await _require_active_table(state, ts, respond, for_payment=False)

        assert result == 5
        assert state._data["session_assigned_at"] is None
        ts.auto_assign_waiter.assert_not_called()

    async def test_fresh_closed_table_payment_auto_assigns(
        self, open_assignment
    ):
        """A fresh guest paying at a closed table gets a waiter auto-assigned."""
        state = _FakeState({"table_number": 5, "session_assigned_at": None})
        ts = _table_service(open_assignment=None, new_assignment=open_assignment)
        respond = AsyncMock()

        result = await _require_active_table(
            state, ts, respond, for_payment=True
        )

        assert result == 5
        ts.auto_assign_waiter.assert_awaited_once_with(5)
        assert state._data["session_assigned_at"] == open_assignment.assigned_at

    async def test_fresh_payment_no_waiters_fails(self):
        """If no waiters are available, payment cannot proceed."""
        state = _FakeState({"table_number": 5, "session_assigned_at": None})
        ts = _table_service(open_assignment=None, new_assignment=None)
        respond = AsyncMock()

        result = await _require_active_table(
            state, ts, respond, for_payment=True
        )

        assert result is None
        respond.assert_awaited_once()
        assert "официантов" in respond.call_args.args[0].lower()


class TestActiveSessionClosedByStaff:
    """The core regression: staff closes a table under an existing session."""

    async def test_session_invalidated_when_table_closed(
        self, open_assignment
    ):
        """Guest had an active session, then staff closed the table."""
        state = _FakeState(
            {
                "table_number": 5,
                "session_assigned_at": open_assignment.assigned_at,
            }
        )
        # Table is now closed: get_open_assignment returns None.
        ts = _table_service(open_assignment=None)
        respond = AsyncMock()

        result = await _require_active_table(state, ts, respond)

        assert result is None
        # Session is cleared so the guest must rescan.
        assert state._data["table_number"] is None
        assert state._data["session_assigned_at"] is None
        respond.assert_awaited_once()
        assert "QR-код" in respond.call_args.args[0]
        # Critically, the table must NOT be silently reopened for this guest.
        ts.auto_assign_waiter.assert_not_called()

    async def test_session_invalidated_when_table_reopened_for_others(
        self, open_assignment, reopened_assignment
    ):
        """Staff reopened the table for new guests: old session is stale.

        Even though the table is open again, the assigned_at timestamp
        differs from the guest's session token, so they must rescan.
        """
        state = _FakeState(
            {
                "table_number": 5,
                "session_assigned_at": open_assignment.assigned_at,
            }
        )
        ts = _table_service(open_assignment=reopened_assignment)
        respond = AsyncMock()

        result = await _require_active_table(state, ts, respond)

        assert result is None
        assert state._data["table_number"] is None
        respond.assert_awaited_once()
        assert "QR-код" in respond.call_args.args[0]

    async def test_payment_after_close_requires_rescan(
        self, open_assignment
    ):
        """Even for_payment=True must NOT reopen a closed active session."""
        state = _FakeState(
            {
                "table_number": 5,
                "session_assigned_at": open_assignment.assigned_at,
            }
        )
        ts = _table_service(
            open_assignment=None, new_assignment=open_assignment
        )
        respond = AsyncMock()

        result = await _require_active_table(
            state, ts, respond, for_payment=True
        )

        assert result is None
        assert state._data["table_number"] is None
        # for_payment auto-assign is skipped for stale sessions.
        ts.auto_assign_waiter.assert_not_called()


class TestActiveSessionStillValid:
    async def test_active_session_allows_action(self, open_assignment):
        """A still-open table under the same assignment stays valid."""
        state = _FakeState(
            {
                "table_number": 5,
                "session_assigned_at": open_assignment.assigned_at,
            }
        )
        ts = _table_service(open_assignment=open_assignment)
        respond = AsyncMock()

        result = await _require_active_table(state, ts, respond)

        assert result == 5
        respond.assert_not_awaited()
        ts.auto_assign_waiter.assert_not_called()
        assert state._data["session_assigned_at"] == open_assignment.assigned_at


class TestInvalidateSession:
    async def test_clears_state_and_notifies(self):
        state = _FakeState(
            {"table_number": 5, "session_assigned_at": "2024-01-01T12:00:00"}
        )
        respond = AsyncMock()

        await _invalidate_session(state, respond)

        assert state._data["table_number"] is None
        assert state._data["session_assigned_at"] is None
        respond.assert_awaited_once()
        assert "QR-код" in respond.call_args.args[0]