"""Guest table-session validation service.

Encapsulates the business logic of validating a guest's table session,
which previously lived inside ``guest_handlers._require_active_table``.

A guest starts a table session by scanning the QR code (``/start table_N``).
The session is bound to the table's *open* assignment at that moment via the
assignment's ``assigned_at`` timestamp (the "session token"). If staff later
closes the table, the session becomes invalid and the guest must rescan.

The service is framework-agnostic: it takes plain values (table number,
token) and returns a :class:`SessionValidationResult` describing what the
caller (a handler) should do. This keeps the service unit-testable without
any aiogram/FSM dependency.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from services.table_service import TableService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionValidationResult:
    """Outcome of validating a guest table session.

    Attributes:
        table_number: The validated table number, or ``None`` if the session
            is invalid and the guest must rescan the QR code.
        session_assigned_at: The session token that should be persisted back
            into the guest's FSM state (may update an existing token or set
            a new one). ``None`` means "do not change the stored token".
        error_message: A user-facing message to send to the guest when the
            session is invalid (``table_number is None``). ``None`` if valid.
        requires_rescan: When True, the guest's session has been invalidated
            (e.g. the table was closed) and the stored table_number/token
            should be cleared so the guest rescans the QR code.
    """

    table_number: Optional[int]
    session_assigned_at: Optional[str] = None
    error_message: Optional[str] = None
    requires_rescan: bool = False


class GuestSessionService:
    """Validates guest table sessions against open table assignments."""

    def __init__(self, table_service: TableService):
        self._table_service = table_service

    async def validate_table_session(
        self,
        table_number: Optional[int],
        token: Optional[str],
        *,
        for_payment: bool = False,
    ) -> SessionValidationResult:
        """Validate a guest's table session and return the required action.

        Rules:
          * No ``table_number`` at all -> ask to scan the QR code.
          * Fresh session (token is ``None``): browsing is allowed. If the
            table is already open, the token is latched onto it. If
            ``for_payment`` is True and the table is not open yet, a waiter is
            auto-assigned and the token is captured.
          * Active session (token is set): the table must currently be open
            under the *same* assignment (matching ``assigned_at``). Otherwise
            the session is invalidated (requires rescan).

        Args:
            table_number: The table number stored in the guest's session, or
                ``None`` if the guest hasn't scanned a QR code yet.
            token: The session token (an assignment's ``assigned_at`` value),
                or ``None`` for a fresh session.
            for_payment: When True, a fresh (never-opened) table is
                auto-assigned a waiter so the payment flow has an assignment
                to update.

        Returns:
            A :class:`SessionValidationResult` describing what the caller
            should do.
        """
        if table_number is None:
            return SessionValidationResult(
                table_number=None,
                error_message="Сначала отсканируйте QR-код стола.",
            )

        open_assignment = await self._table_service.get_open_assignment(table_number)

        if token is None:
            # Fresh session: the guest just scanned and hasn't opened the
            # table themselves yet (no checkout/payment performed).
            if open_assignment is not None:
                # Latch onto an already-open table (e.g. a rescan of an
                # active table) so subsequent close/reopen detection works.
                return SessionValidationResult(
                    table_number=table_number,
                    session_assigned_at=open_assignment.assigned_at,
                )
            if for_payment:
                # Payment needs an open assignment; auto-assign for the fresh
                # guest and capture the token. This does NOT reopen a table
                # that was closed under an existing session (those guests have
                # a token and take the branch below).
                assignment = await self._table_service.auto_assign_waiter(table_number)
                if assignment is None:
                    return SessionValidationResult(
                        table_number=None,
                        error_message="Сейчас нет доступных официантов. Обратитесь к персоналу.",
                    )
                return SessionValidationResult(
                    table_number=table_number,
                    session_assigned_at=assignment.assigned_at,
                )
            return SessionValidationResult(table_number=table_number)

        # Existing session: the table must still be open under the SAME
        # assignment (matching assigned_at token). Otherwise the table was
        # closed/reopened and the session is invalid.
        if open_assignment is None or open_assignment.assigned_at != token:
            logger.info(
                "Guest session for table %s invalidated (closed/reopened).",
                table_number,
            )
            return SessionValidationResult(
                table_number=None,
                error_message=(
                    "Ваш стол был закрыт. Отсканируйте QR-код на столе заново, "
                    "чтобы сделать новый заказ."
                ),
                requires_rescan=True,
            )

        return SessionValidationResult(table_number=table_number)