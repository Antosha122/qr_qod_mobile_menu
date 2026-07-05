"""Tests for TableService and utility functions."""
import pytest
from unittest.mock import AsyncMock

from database.models import Cart, User, WaiterAssignment
from services.table_service import (
    TableService,
    PaymentConfirmationError,
)
from utils.formatters import format_cart_message, format_order_message, format_assignment_message


class TestTableService:
    """Tests for the TableService class."""

    async def test_assign_waiter(self, mock_assignment_repo, sample_assignment):
        """Test assigning a waiter to a table."""
        mock_assignment_repo.assign_waiter.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.assign_waiter(2, 5)

        assert result == sample_assignment
        mock_assignment_repo.assign_waiter.assert_called_once_with(2, 5)

    async def test_get_assignment(self, mock_assignment_repo, sample_assignment):
        """Test getting an assignment."""
        mock_assignment_repo.get_by_table.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.get_assignment(5)

        assert result == sample_assignment

    async def test_get_assignment_not_found(self, mock_assignment_repo):
        """Test getting assignment for unassigned table."""
        mock_assignment_repo.get_by_table.return_value = None
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.get_assignment(999)

        assert result is None

    async def test_is_table_open(self, mock_assignment_repo):
        """Test checking if table is open."""
        mock_assignment_repo.is_table_open.return_value = True
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.is_table_open(5)

        assert result is True

    async def test_close_table_success(self, mock_assignment_repo, mock_cart_repo, sample_assignment):
        """Test closing a table successfully (payment must be confirmed first)."""
        paid_assignment = WaiterAssignment(
            id=sample_assignment.id,
            waiter_id=sample_assignment.waiter_id,
            table_number=sample_assignment.table_number,
            status="open",
            assigned_at=sample_assignment.assigned_at,
            payment_status="paid",
        )
        mock_assignment_repo.get_open_assignment.return_value = paid_assignment
        mock_assignment_repo.close_table.return_value = True
        service = TableService(mock_assignment_repo, mock_cart_repo)

        result = await service.close_table(5)

        assert result is True
        # Already paid — no need to update the payment status again.
        mock_assignment_repo.update_payment_status.assert_not_called()
        # conn= is passed because close_table runs inside a transaction.
        mock_cart_repo.clear_cart.assert_called_once()
        assert mock_cart_repo.clear_cart.call_args[0][0] == 5
        mock_cart_repo.delete_cart.assert_called_once()
        assert mock_cart_repo.delete_cart.call_args[0][0] == 5

    async def test_close_table_auto_marks_paid(
        self, mock_assignment_repo, mock_cart_repo, sample_assignment
    ):
        """Closing a table that is not paid auto-marks it as paid first.

        The waiter pressing "Close table" is itself the confirmation that the
        guest has paid: the table does NOT raise and is closed successfully,
        with its payment status bumped to 'paid' before being closed.
        """
        # sample_assignment has payment_status='unpaid'.
        mock_assignment_repo.get_open_assignment.return_value = sample_assignment
        mock_assignment_repo.close_table.return_value = True
        service = TableService(mock_assignment_repo, mock_cart_repo)

        result = await service.close_table(5)

        assert result is True
        # Payment is auto-confirmed before the table is closed.
        mock_assignment_repo.update_payment_status.assert_called_once()
        assert mock_assignment_repo.update_payment_status.call_args[0][:2] == (5, "paid")
        mock_assignment_repo.close_table.assert_called_once()
        assert mock_assignment_repo.close_table.call_args[0][0] == 5
        mock_cart_repo.clear_cart.assert_called_once()
        assert mock_cart_repo.clear_cart.call_args[0][0] == 5
        mock_cart_repo.delete_cart.assert_called_once()
        assert mock_cart_repo.delete_cart.call_args[0][0] == 5

    async def test_close_table_not_found(self, mock_assignment_repo, mock_cart_repo):
        """Test closing a non-existent table."""
        # No open assignment and close_table returns False.
        mock_assignment_repo.get_open_assignment.return_value = None
        mock_assignment_repo.close_table.return_value = False
        service = TableService(mock_assignment_repo, mock_cart_repo)

        result = await service.close_table(999)

        assert result is False
        mock_cart_repo.clear_cart.assert_not_called()

    async def test_close_then_reopen_resets_payment_status(
        self, mock_assignment_repo, mock_cart_repo, sample_assignment
    ):
        """Closing a paid table and reopening it must reset payment_status.

        Regression test for the bug where a closed table was still shown as
        "paid" to the next guests. After close_table(), the assignment must
        be fully reset; reassigning a waiter yields a fresh 'unpaid' table.
        """
        paid_assignment = WaiterAssignment(
            id=sample_assignment.id,
            waiter_id=sample_assignment.waiter_id,
            table_number=sample_assignment.table_number,
            status="open",
            assigned_at=sample_assignment.assigned_at,
            payment_status="paid",
        )
        mock_assignment_repo.get_open_assignment.return_value = paid_assignment
        mock_assignment_repo.close_table.return_value = True
        service = TableService(mock_assignment_repo, mock_cart_repo)

        closed = await service.close_table(5)

        assert closed is True
        # The repo's close_table now also resets payment_status to 'unpaid'.
        mock_assignment_repo.close_table.assert_called_once()
        assert mock_assignment_repo.close_table.call_args[0][0] == 5
        mock_cart_repo.clear_cart.assert_called_once()
        assert mock_cart_repo.clear_cart.call_args[0][0] == 5
        mock_cart_repo.delete_cart.assert_called_once()
        assert mock_cart_repo.delete_cart.call_args[0][0] == 5

        # Reopening the table (new guests) yields a fresh unpaid assignment.
        fresh_assignment = WaiterAssignment(
            id=sample_assignment.id,
            waiter_id=sample_assignment.waiter_id,
            table_number=sample_assignment.table_number,
            status="open",
            assigned_at=sample_assignment.assigned_at,
            payment_status="unpaid",
        )
        mock_assignment_repo.assign_waiter.return_value = fresh_assignment
        reopened = await service.assign_waiter(2, 5)

        assert reopened.status == "open"
        assert reopened.payment_status == "unpaid"

    async def test_get_all_open_tables(self, mock_assignment_repo, sample_assignment):
        """Test getting all open tables."""
        mock_assignment_repo.get_all_open.return_value = [sample_assignment]
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.get_all_open_tables()

        assert len(result) == 1

    async def test_get_waiter_open_tables(self, mock_assignment_repo, sample_assignment):
        """Test getting all open tables assigned to a specific waiter."""
        mock_assignment_repo.get_open_by_waiter.return_value = [sample_assignment]
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.get_waiter_open_tables(2)

        assert len(result) == 1
        assert result[0].waiter_id == 2
        mock_assignment_repo.get_open_by_waiter.assert_called_once_with(2)

    async def test_get_waiter_open_tables_empty(self, mock_assignment_repo):
        """Test getting open tables for a waiter with no assignments."""
        mock_assignment_repo.get_open_by_waiter.return_value = []
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.get_waiter_open_tables(99)

        assert result == []


class TestPaymentFlow:
    """Tests for the request_bill / pay_bill functionality."""

    async def test_request_bill(self, mock_assignment_repo):
        """Test requesting the bill updates payment_status to 'requested'."""
        mock_assignment_repo.update_payment_status.return_value = True
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.request_bill(5)

        assert result is True
        mock_assignment_repo.update_payment_status.assert_called_once_with(5, "requested")

    async def test_request_bill_not_found(self, mock_assignment_repo):
        """Test requesting bill for a non-existent table."""
        mock_assignment_repo.update_payment_status.return_value = False
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.request_bill(999)

        assert result is False

    async def test_pay_bill(self, mock_assignment_repo, mock_cart_repo):
        """Test paying the bill updates payment_status to 'payment_pending'.

        The guest pressing "Pay" only requests confirmation — it does NOT mark
        the bill as 'paid'. The assigned waiter must confirm via
        `confirm_payment`.
        """
        mock_assignment_repo.update_payment_status.return_value = True
        service = TableService(mock_assignment_repo, mock_cart_repo)

        result = await service.pay_bill(5)

        assert result is True
        mock_assignment_repo.update_payment_status.assert_called_once_with(
            5, "payment_pending"
        )

    async def test_pay_bill_does_not_close_table(self, mock_assignment_repo, mock_cart_repo):
        """Paying the bill must NOT close the table or clear the cart.

        The table stays open until staff explicitly closes it.
        """
        mock_assignment_repo.update_payment_status.return_value = True
        service = TableService(mock_assignment_repo, mock_cart_repo)

        await service.pay_bill(5)

        mock_assignment_repo.close_table.assert_not_called()
        mock_cart_repo.clear_cart.assert_not_called()
        mock_cart_repo.delete_cart.assert_not_called()

    async def test_pay_bill_not_found(self, mock_assignment_repo, mock_cart_repo):
        """Test paying bill for a non-existent table."""
        mock_assignment_repo.update_payment_status.return_value = False
        service = TableService(mock_assignment_repo, mock_cart_repo)

        result = await service.pay_bill(999)

        assert result is False


class TestConfirmPayment:
    """Tests for the confirm_payment functionality."""

    def _pending_assignment(self, waiter_id: int = 2, table_number: int = 5):
        return WaiterAssignment(
            id=1,
            waiter_id=waiter_id,
            table_number=table_number,
            status="open",
            assigned_at="2024-01-01T12:00:00",
            payment_status="payment_pending",
        )

    async def test_confirm_by_assigned_waiter(self, mock_assignment_repo):
        """The assigned waiter can confirm the payment."""
        mock_assignment_repo.get_open_assignment.return_value = self._pending_assignment(waiter_id=2)
        mock_assignment_repo.update_payment_status.return_value = True
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.confirm_payment(5, confirmer_id=2)

        assert result is True
        mock_assignment_repo.update_payment_status.assert_called_once_with(5, "paid")

    async def test_confirm_by_admin_override(self, mock_assignment_repo):
        """An admin can confirm the payment even if not the assigned waiter."""
        mock_assignment_repo.get_open_assignment.return_value = self._pending_assignment(waiter_id=2)
        mock_assignment_repo.update_payment_status.return_value = True
        service = TableService(mock_assignment_repo, AsyncMock())

        result = await service.confirm_payment(5, confirmer_id=99, is_admin=True)

        assert result is True
        mock_assignment_repo.update_payment_status.assert_called_once_with(5, "paid")

    async def test_confirm_by_other_waiter_raises(
        self, mock_assignment_repo, sample_assignment
    ):
        """A different (non-admin) waiter must NOT be able to confirm."""
        mock_assignment_repo.get_open_assignment.return_value = self._pending_assignment(waiter_id=2)
        service = TableService(mock_assignment_repo, AsyncMock())

        with pytest.raises(PaymentConfirmationError):
            await service.confirm_payment(5, confirmer_id=99)

        # Payment must NOT be marked as paid.
        mock_assignment_repo.update_payment_status.assert_not_called()

    async def test_confirm_wrong_state_raises(self, mock_assignment_repo, sample_assignment):
        """Confirming payment when not in 'payment_pending' raises ValueError."""
        # sample_assignment has payment_status='unpaid'
        mock_assignment_repo.get_open_assignment.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock())

        with pytest.raises(ValueError):
            await service.confirm_payment(5, confirmer_id=2)

        mock_assignment_repo.update_payment_status.assert_not_called()

    async def test_confirm_no_open_assignment_raises(self, mock_assignment_repo):
        """Confirming payment with no open assignment raises ValueError."""
        mock_assignment_repo.get_open_assignment.return_value = None
        service = TableService(mock_assignment_repo, AsyncMock())

        with pytest.raises(ValueError):
            await service.confirm_payment(5, confirmer_id=2)


class TestAutoAssignWaiter:
    """Tests for the auto_assign_waiter functionality."""

    async def test_returns_existing_assignment(
        self, mock_assignment_repo, mock_user_repo, sample_assignment
    ):
        """If a table already has an open assignment, it should be returned as-is."""
        mock_assignment_repo.get_open_assignment.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock(), mock_user_repo)

        result = await service.auto_assign_waiter(5)

        assert result == sample_assignment
        mock_user_repo.get_all_waiters.assert_not_called()
        mock_assignment_repo.assign_waiter.assert_not_called()

    async def test_no_waiters_returns_none(self, mock_assignment_repo, mock_user_repo):
        """If no waiters exist, auto-assign should return None."""
        mock_assignment_repo.get_open_assignment.return_value = None
        mock_user_repo.get_all_waiters.return_value = []
        service = TableService(mock_assignment_repo, AsyncMock(), mock_user_repo)

        result = await service.auto_assign_waiter(5)

        assert result is None
        mock_assignment_repo.assign_waiter.assert_not_called()

    async def test_no_user_repo_returns_none(self, mock_assignment_repo):
        """If UserRepository is not configured, auto-assign should return None."""
        mock_assignment_repo.get_open_assignment.return_value = None
        service = TableService(mock_assignment_repo, AsyncMock(), None)

        result = await service.auto_assign_waiter(5)

        assert result is None

    async def test_picks_free_waiter(
        self, mock_assignment_repo, mock_user_repo, sample_waiter_user, sample_assignment
    ):
        """Should assign to a free waiter (0 open tables)."""
        mock_assignment_repo.get_open_assignment.return_value = None
        mock_user_repo.get_all_waiters.return_value = [sample_waiter_user]
        mock_assignment_repo.count_open_by_waiter.return_value = 0
        mock_assignment_repo.assign_waiter.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock(), mock_user_repo)

        result = await service.auto_assign_waiter(5)

        assert result == sample_assignment
        mock_assignment_repo.assign_waiter.assert_called_once_with(sample_waiter_user.id, 5)

    async def test_picks_least_busy_waiter(
        self, mock_assignment_repo, mock_user_repo, sample_assignment
    ):
        """With multiple waiters, should pick the one with fewest open tables."""
        waiter_busy = User(id=10, username="busy", password="x", role="waiter", chat_id=None)
        waiter_free = User(id=11, username="free", password="x", role="waiter", chat_id=None)
        mock_assignment_repo.get_open_assignment.return_value = None
        mock_user_repo.get_all_waiters.return_value = [waiter_busy, waiter_free]

        # First waiter (busy) has 3 tables, second (free) has 0.
        mock_assignment_repo.count_open_by_waiter.side_effect = [3, 0]
        mock_assignment_repo.assign_waiter.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock(), mock_user_repo)

        result = await service.auto_assign_waiter(7)

        assert result == sample_assignment
        mock_assignment_repo.assign_waiter.assert_called_once_with(waiter_free.id, 7)

    async def test_keeps_least_busy_when_none_free(
        self, mock_assignment_repo, mock_user_repo, sample_assignment
    ):
        """If all waiters have tables, should pick the least busy one."""
        w1 = User(id=20, username="w1", password="x", role="waiter", chat_id=None)
        w2 = User(id=21, username="w2", password="x", role="waiter", chat_id=None)
        mock_assignment_repo.get_open_assignment.return_value = None
        mock_user_repo.get_all_waiters.return_value = [w1, w2]

        # w1 has 5 tables, w2 has 2 tables -> w2 should be chosen.
        mock_assignment_repo.count_open_by_waiter.side_effect = [5, 2]
        mock_assignment_repo.assign_waiter.return_value = sample_assignment
        service = TableService(mock_assignment_repo, AsyncMock(), mock_user_repo)

        result = await service.auto_assign_waiter(3)

        assert result == sample_assignment
        mock_assignment_repo.assign_waiter.assert_called_once_with(w2.id, 3)


class TestGetTableOverview:
    """Tests for TableService.get_table_overview().

    Most importantly, these guard against the regression where the table's
    cart total was always shown as ``0 ₽`` to waiters. The root cause was that
    ``get_cart_total(table_number)`` was called with a table number while the
    repository method expects a ``cart_id``. The overview must first resolve
    the cart for the table and then sum its items by ``cart.id``.
    """

    async def test_overview_uses_cart_id_not_table_number(
        self, mock_assignment_repo, mock_cart_repo, sample_assignment
    ):
        """The cart total must be computed from the resolved cart, not the
        table number.

        We deliberately give the cart an id (77) that differs from the table
        number (5). If the service incorrectly passed the table number to
        ``get_cart_total`` it would hit the ``return_value=0.0`` branch we set
        up for ``get_cart_total(5)`` and the table would wrongly show ``0 ₽``.
        """
        mock_assignment_repo.get_open_by_waiter.return_value = [sample_assignment]
        cart = Cart(id=77, table_number=5, created_at="2024-01-01T12:00:00")
        mock_cart_repo.get_cart_by_table.return_value = cart

        async def _fake_get_cart_total(cart_id, conn=None):
            # Only the call with the real cart id returns a non-zero sum.
            return 1230.0 if cart_id == 77 else 0.0

        mock_cart_repo.get_cart_total.side_effect = _fake_get_cart_total

        service = TableService(mock_assignment_repo, mock_cart_repo)
        overview = await service.get_table_overview(waiter_id=2)

        assert 5 in overview
        info = overview[5]
        assert info["is_open"] is True
        assert info["is_mine"] is True
        assert info["total"] == 1230.0
        # Sanity check: the repository was queried with the cart id, not 5.
        mock_cart_repo.get_cart_by_table.assert_awaited_once_with(5)
        mock_cart_repo.get_cart_total.assert_awaited_once_with(77)

    async def test_overview_admin_sees_total_for_any_table(
        self, mock_assignment_repo, mock_cart_repo, sample_assignment
    ):
        """Admins see the cart total for all open tables."""
        mock_assignment_repo.get_all_open.return_value = [sample_assignment]
        cart = Cart(id=77, table_number=5, created_at="2024-01-01T12:00:00")
        mock_cart_repo.get_cart_by_table.return_value = cart
        mock_cart_repo.get_cart_total.return_value = 500.0

        service = TableService(mock_assignment_repo, mock_cart_repo)
        overview = await service.get_table_overview(waiter_id=1, is_admin=True)

        assert overview[5]["total"] == 500.0
        assert overview[5]["is_mine"] is True

    async def test_overview_no_cart_shows_zero(
        self, mock_assignment_repo, mock_cart_repo, sample_assignment
    ):
        """A table with no cart (e.g. just assigned, nothing ordered yet)
        should show a total of 0.0 without raising."""
        mock_assignment_repo.get_open_by_waiter.return_value = [sample_assignment]
        mock_cart_repo.get_cart_by_table.return_value = None

        service = TableService(mock_assignment_repo, mock_cart_repo)
        overview = await service.get_table_overview(waiter_id=2)

        assert overview[5]["total"] == 0.0
        mock_cart_repo.get_cart_total.assert_not_awaited()

    async def test_overview_foreign_table_total_not_fetched(
        self, mock_assignment_repo, mock_cart_repo
    ):
        """Tables owned by other waiters are shown as locked and their totals
        are NOT fetched (no per-table DB queries for foreign tables)."""
        other_assignment = WaiterAssignment(
            id=9,
            waiter_id=99,
            table_number=5,
            status="open",
            assigned_at="2024-01-01T12:00:00",
            payment_status="unpaid",
        )
        mock_assignment_repo.get_open_by_waiter.return_value = [other_assignment]

        service = TableService(mock_assignment_repo, mock_cart_repo)
        overview = await service.get_table_overview(waiter_id=2)

        assert overview[5]["is_open"] is True
        assert overview[5]["is_mine"] is False
        assert overview[5]["total"] == 0.0
        mock_cart_repo.get_cart_by_table.assert_not_awaited()


class TestFormatters:
    """Tests for message formatter functions."""

    def test_format_cart_message_empty(self):
        """Test formatting empty cart."""
        result = format_cart_message([], 0.0, 5)

        assert "пуста" in result

    def test_format_cart_message_with_items(self, sample_menu_item):
        """Test formatting cart with items."""
        items = [(sample_menu_item, 2, 800.0)]

        result = format_cart_message(items, 800.0, 5)

        assert "Ролл с тунцом" in result
        assert "800" in result
        assert "стол 5" in result

    def test_format_cart_message_no_table(self, sample_menu_item):
        """Test formatting cart without table number."""
        items = [(sample_menu_item, 1, 400.0)]

        result = format_cart_message(items, 400.0)

        assert "стол" not in result

    def test_format_order_message(self, sample_order):
        """Test formatting an order."""
        result = format_order_message(sample_order)

        assert "Заказ #1" in result
        assert "Стол: 5" in result
        assert "pending" in result

    def test_format_order_message_with_items(self, sample_order):
        """Test formatting order with items text."""
        items_text = "🍽 Ролл — 2 шт."

        result = format_order_message(sample_order, items_text)

        assert items_text in result

    def test_format_assignment_message_open(self, sample_assignment):
        """Test formatting an open assignment."""
        result = format_assignment_message(sample_assignment)

        assert "Стол 5" in result
        assert "open" in result

    def test_format_assignment_message_no_waiter(self):
        """Test formatting assignment without waiter."""
        assignment = WaiterAssignment(
            id=1, waiter_id=None, table_number=3, status="open", assigned_at=None
        )

        result = format_assignment_message(assignment)

        assert "не назначен" in result