"""Table service for table and waiter assignment management."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.repositories.protocols import (
    WaiterAssignmentRepositoryProtocol,
    CartRepositoryProtocol,
    UserRepositoryProtocol,
    ClosedBillRepositoryProtocol,
)
from database.models import WaiterAssignment

logger = logging.getLogger(__name__)


# Mapping of human-readable period names to their timedelta offsets from "now".
# Used by get_revenue / get_waiter_stats to compute the `since` timestamp.
PERIOD_DELTAS: dict[str, timedelta] = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}


class PaymentConfirmationError(Exception):
    """Raised when a non-assigned waiter tries to confirm payment."""

    def __init__(self, table_number: int, confirmer_id: Optional[int]):
        self.table_number = table_number
        self.confirmer_id = confirmer_id
        super().__init__(
            f"Only the waiter assigned to table {table_number} may confirm "
            f"payment (confirmer id={confirmer_id})."
        )


class TableService:
    """Handles table and waiter assignment business logic.

    Lifecycle of a table:
      1. Open (status='open', payment_status='unpaid') when a waiter is assigned
         (auto-assigned on the guest's first checkout).
      2. The guest can request the bill (payment_status='requested').
      3. The guest clicks "Pay" (payment_status='payment_pending') — payment is
         NOT final yet.
      4. The waiter assigned to the table confirms the payment
         (payment_status='paid').
      5. Staff closes the table (status='closed'). Closing a table is itself
         the final confirmation that the guest has paid: if the payment had
         not been confirmed yet, it is automatically marked as 'paid' right
         before the table is released and the cart is cleared.
    """

    def __init__(
        self,
        assignment_repo: WaiterAssignmentRepositoryProtocol,
        cart_repo: CartRepositoryProtocol,
        user_repo: Optional[UserRepositoryProtocol] = None,
        closed_bill_repo: Optional[ClosedBillRepositoryProtocol] = None,
    ):
        self._assignment_repo = assignment_repo
        self._cart_repo = cart_repo
        self._user_repo = user_repo
        # Optional: when provided, closed bills are recorded for revenue and
        # per-waiter statistics. Kept optional so existing tests that build a
        # TableService without it keep working.
        self._closed_bill_repo = closed_bill_repo

    async def assign_waiter(self, waiter_id: int, table_number: int) -> WaiterAssignment:
        """Assign a waiter to a table.

        Args:
            waiter_id: The waiter's user ID.
            table_number: The table number.

        Returns:
            The created/updated WaiterAssignment instance.
        """
        assignment = await self._assignment_repo.assign_waiter(waiter_id, table_number)
        logger.info(f"Waiter {waiter_id} assigned to table {table_number}.")
        return assignment

    async def auto_assign_waiter(self, table_number: int) -> Optional[WaiterAssignment]:
        """Automatically assign a table to the least busy (or free) waiter.

        Selection rule (matches the requested business logic):
        1. Prefer waiters with zero open tables (free waiters).
        2. Otherwise assign to the waiter with the fewest open tables.
        3. Ties are broken by waiter id (oldest waiter first) for determinism.

        If the table already has an open assignment, it is returned as-is.
        If no waiters exist, returns None.

        Args:
            table_number: The table number to assign.

        Returns:
            The WaiterAssignment instance, or None if no waiters are available.
        """
        # Already assigned? Keep the existing assignment.
        existing = await self._assignment_repo.get_open_assignment(table_number)
        if existing is not None:
            return existing

        if self._user_repo is None:
            logger.warning("Auto-assign requested but no UserRepository configured.")
            return None

        waiters = await self._user_repo.get_all_waiters()
        if not waiters:
            logger.warning("Auto-assign failed: no waiters found.")
            return None

        # Count current load per waiter and pick the least busy one.
        best_waiter = None
        best_load: Optional[int] = None
        for waiter in waiters:
            load = await self._assignment_repo.count_open_by_waiter(waiter.id)
            if best_load is None or load < best_load:
                best_load = load
                best_waiter = waiter
                # Free waiter (0 tables) is the ideal choice — stop early.
                if load == 0:
                    break

        if best_waiter is None:
            return None

        assignment = await self._assignment_repo.assign_waiter(best_waiter.id, table_number)
        logger.info(
            f"Table {table_number} auto-assigned to waiter {best_waiter.id} "
            f"(previous load: {best_load})."
        )
        return assignment

    async def get_assignment(self, table_number: int) -> Optional[WaiterAssignment]:
        """Get the assignment for a table.

        Args:
            table_number: The table number.

        Returns:
            WaiterAssignment instance if found, None otherwise.
        """
        return await self._assignment_repo.get_by_table(table_number)

    async def get_open_assignment(self, table_number: int) -> Optional[WaiterAssignment]:
        """Get the open assignment for a table.

        Args:
            table_number: The table number.

        Returns:
            WaiterAssignment instance if open assignment exists, None otherwise.
        """
        return await self._assignment_repo.get_open_assignment(table_number)

    async def is_table_open(self, table_number: int) -> bool:
        """Check if a table has an open assignment.

        Args:
            table_number: The table number.

        Returns:
            True if the table has an open assignment, False otherwise.
        """
        return await self._assignment_repo.is_table_open(table_number)

    async def request_bill(self, table_number: int) -> bool:
        """Mark that the guest has requested the bill for a table.

        Args:
            table_number: The table number.

        Returns:
            True if the assignment was found and updated, False otherwise.
        """
        result = await self._assignment_repo.update_payment_status(
            table_number, "requested"
        )
        if result:
            logger.info(f"Bill requested for table {table_number}.")
        return result

    async def pay_bill(self, table_number: int) -> bool:
        """Guest pressed "Pay" — mark the bill as awaiting waiter confirmation.

        The bill is NOT final yet. The waiter assigned to the table must confirm
        the payment via `confirm_payment` before the table can be closed.

        Args:
            table_number: The table number.

        Returns:
            True if the assignment was found and marked payment_pending,
            False otherwise.
        """
        result = await self._assignment_repo.update_payment_status(
            table_number, "payment_pending"
        )
        if result:
            logger.info(
                f"Bill for table {table_number} marked payment_pending "
                f"(awaiting waiter confirmation)."
            )
        return result

    async def confirm_payment(
        self, table_number: int, confirmer_id: int, is_admin: bool = False
    ) -> bool:
        """Waiter confirms that the guest has actually paid.

        Only the waiter assigned to the table may confirm the payment.
        Admins are allowed to confirm as an override (e.g. when a waiter is
        unavailable).

        Args:
            table_number: The table number.
            confirmer_id: The user id of the confirming staff member.
            is_admin: Whether the confirmer is an admin (override allowed).

        Returns:
            True if the payment was confirmed successfully.

        Raises:
            PaymentConfirmationError: If the confirmer is not the assigned
                waiter (and not an admin).
            ValueError: If the table has no assignment or is not in the
                'payment_pending' state.
        """
        assignment = await self._assignment_repo.get_open_assignment(table_number)
        if assignment is None:
            raise ValueError(
                f"Cannot confirm payment: no open assignment for table {table_number}."
            )

        if assignment.payment_status != "payment_pending":
            raise ValueError(
                f"Cannot confirm payment for table {table_number}: "
                f"current payment_status='{assignment.payment_status}', "
                f"expected 'payment_pending'."
            )

        if not is_admin and assignment.waiter_id != confirmer_id:
            raise PaymentConfirmationError(table_number, confirmer_id)

        result = await self._assignment_repo.update_payment_status(
            table_number, "paid"
        )
        if result:
            logger.info(
                f"Payment for table {table_number} confirmed by user "
                f"{confirmer_id} (admin={is_admin})."
            )
        return result

    async def close_table(self, table_number: int) -> bool:
        """Close a table: set assignment to 'closed' and clear the cart.

        Closing a table from the staff side means the guest has already paid:
        if the payment had not been confirmed yet (payment_status != 'paid'),
        it is automatically marked as 'paid' right before closing. The table
        is then released for the next guests and its cart is cleared.

        Args:
            table_number: The table number.

        Returns:
            True if assignment was found and closed, False otherwise.
        """
        # Use the repository's public acquire_connection() instead of reaching
        # into its private _pool. The connection is shared by all repositories
        # involved in this transaction via their conn= parameter.
        async with self._assignment_repo.acquire_connection() as conn:
            tx_result = False
            async with conn.transaction():
                assignment = await self._assignment_repo.get_open_assignment(table_number)

                if assignment is not None and assignment.payment_status != "paid":
                    await self._assignment_repo.update_payment_status(
                        table_number, "paid", conn=conn
                    )
                    logger.info(
                        f"Payment for table {table_number} auto-confirmed on close "
                        f"(previous status='{assignment.payment_status}')."
                    )

                cart = await self._cart_repo.get_cart_by_table(table_number, conn=conn)
                bill_amount = (
                    await self._cart_repo.get_cart_total(cart.id, conn=conn) if cart else 0.0
                )
                waiter_id = assignment.waiter_id if assignment else None

                tx_result = await self._assignment_repo.close_table(table_number, conn=conn)
                if tx_result:
                    if self._closed_bill_repo is not None:
                        try:
                            await self._closed_bill_repo.record_bill(
                                waiter_id, table_number, bill_amount, conn=conn
                            )
                        except Exception:
                            logger.exception(
                                f"Failed to record closed bill for table {table_number}."
                            )
                    await self._cart_repo.clear_cart(table_number, conn=conn)
                    await self._cart_repo.delete_cart(table_number, conn=conn)
                    logger.info(f"Table {table_number} closed and cart cleared.")
            return tx_result

    async def unassign_table(self, table_number: int) -> bool:
        """Release a table from its waiter (admin action).

        This removes the assignment so the table becomes unassigned. The
        table's cart is left intact, so the current order isn't lost — the
        table will simply be auto-assigned again the next time a guest checks
        out. Use this when an admin wants to pull a table off a waiter.

        Args:
            table_number: The table number to release.

        Returns:
            True if an assignment was removed, False if the table had none.
        """
        result = await self._assignment_repo.unassign_table(table_number)
        if result:
            logger.info(f"Table {table_number} unassigned by admin.")
        return result

    def _period_start(self, period: str) -> datetime:
        """Compute the `since` timestamp for a named period.

        Args:
            period: One of 'day', 'week', 'month'.

        Returns:
            The start datetime (now - delta).

        Raises:
            ValueError: If the period name is not recognized.
        """
        delta = PERIOD_DELTAS.get(period)
        if delta is None:
            raise ValueError(
                f"Unknown period '{period}'. Use one of: {list(PERIOD_DELTAS)}."
            )
        return datetime.now() - delta

    async def get_revenue(self, period: str) -> tuple[float, int]:
        """Get total revenue and number of closed bills for a period.

        Args:
            period: 'day', 'week', or 'month'.

        Returns:
            A tuple of (total_amount, bill_count). Returns (0.0, 0) if the
            closed-bill repository is not configured.
        """
        if self._closed_bill_repo is None:
            return 0.0, 0
        since = self._period_start(period)
        return await self._closed_bill_repo.get_revenue_since(since)

    async def get_waiter_stats(self, period: str) -> list[dict]:
        """Get per-waiter revenue and closed-table counts for a period.

        Args:
            period: 'day', 'week', or 'month'.

        Returns:
            A list of stat dicts (see ClosedBillRepository.get_waiter_stats_since).
            Returns an empty list if the closed-bill repository is not
            configured.
        """
        if self._closed_bill_repo is None:
            return []
        since = self._period_start(period)
        return await self._closed_bill_repo.get_waiter_stats_since(since)

    async def get_all_open_tables(self) -> list[WaiterAssignment]:
        """Get all open table assignments.

        Returns:
            List of open WaiterAssignment instances.
        """
        return await self._assignment_repo.get_all_open()

    async def get_waiter_open_tables(self, waiter_id: int) -> list[WaiterAssignment]:
        """Get all open table assignments for a specific waiter.

        Args:
            waiter_id: The waiter's user ID.

        Returns:
            List of open WaiterAssignment instances assigned to the waiter.
        """
        return await self._assignment_repo.get_open_by_waiter(waiter_id)

    async def get_table_overview(
        self,
        waiter_id: Optional[int] = None,
        *,
        is_admin: bool = False,
        total_tables: Optional[int] = None,
    ) -> dict[int, dict]:
        """Build an overview of all tables for the staff "Tables" view.

        This is pure business logic (which table is open/closed, who owns it,
        its cart total and payment status) extracted from the handler. The
        handler used to assemble this dict itself, reaching into the
        assignment/cart repositories directly.

        Args:
            waiter_id: The current staff user's id. Non-admins only "own" the
                tables assigned to them, which is reflected via ``is_mine``.
            is_admin: When True, every open table is considered "mine" and is
                fully visible (admins manage all tables).
            total_tables: Total number of tables in the restaurant. When
                ``None``, only tables that currently have an assignment are
                included (no empty slots). When provided, every table number
                from 1..total_tables is present in the result.

        Returns:
            A mapping ``{table_number: info_dict}`` where each ``info_dict``
            has the keys:

            * ``is_open`` (bool)
            * ``is_mine`` (bool) — True if the table is visible to the user
              (assigned to them, or any table for admins).
            * ``waiter_id`` (int | None)
            * ``payment_status`` (str)
            * ``total`` (float) — cart total for the table (0.0 if no cart).
        """
        # Open assignments the caller is allowed to see:
        #   * admins (and callers without a waiter_id) see ALL open tables;
        #   * a specific waiter only sees the tables assigned to them.
        if is_admin or waiter_id is None:
            visible = await self._assignment_repo.get_all_open()
        else:
            visible = await self._assignment_repo.get_open_by_waiter(waiter_id)

        visible_by_table: dict[int, WaiterAssignment] = {
            a.table_number: a for a in visible
        }

        # Determine the full set of table numbers to report. When total_tables
        # is provided, every table slot 1..N is included so the keyboard shows
        # empty tables too; otherwise only tables with assignments appear.
        table_numbers: set[int] = set(visible_by_table.keys())
        if total_tables is not None:
            table_numbers.update(range(1, total_tables + 1))

        overview: dict[int, dict] = {}
        for table_number in sorted(table_numbers):
            assignment = visible_by_table.get(table_number)

            is_open = assignment is not None and assignment.status == "open"
            if is_open and assignment is not None:
                is_mine = is_admin or assignment.waiter_id == waiter_id
            else:
                is_mine = False

            # Cart total — only fetch for tables the user actually "owns" so we
            # don't issue a DB query per foreign table.
            total = 0.0
            if is_mine:
                total = await self._cart_repo.get_cart_total(table_number)

            overview[table_number] = {
                "is_open": is_open,
                "is_mine": is_mine,
                "waiter_id": assignment.waiter_id if assignment else None,
                "payment_status": assignment.payment_status if assignment else "unpaid",
                "total": total,
            }

        return overview
