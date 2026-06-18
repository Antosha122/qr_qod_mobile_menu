"""Reply keyboards for the staff (waiters/admin) bot."""
from typing import Optional

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config.settings import settings


def get_staff_main_keyboard(role: str) -> ReplyKeyboardMarkup:
    """Get the main keyboard based on user role.
    
    Args:
        role: User role ('admin' or 'waiter').
        
    Returns:
        ReplyKeyboardMarkup appropriate for the role.
    """
    if role == "waiter":
        return get_staff_waiter_keyboard()
    return get_staff_admin_keyboard()


def get_staff_admin_keyboard() -> ReplyKeyboardMarkup:
    """Get the admin keyboard with all available actions.
    
    Returns:
        ReplyKeyboardMarkup with admin actions.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍣 Меню"), KeyboardButton(text="🍽️ Столы")],
            [KeyboardButton(text="👨‍🍳 Добавить официанта"), KeyboardButton(text="🧾 Отчёты")],
            [KeyboardButton(text="👥 Официанты"), KeyboardButton(text="📋 Заказы")],
            [KeyboardButton(text="🚪 Выйти")],
        ],
        resize_keyboard=True,
    )


def get_report_keyboard() -> ReplyKeyboardMarkup:
    """Get keyboard for choosing a reporting period.
    
    Returns:
        ReplyKeyboardMarkup with day/week/month buttons and a back button.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 За день"), KeyboardButton(text="📊 За неделю"), KeyboardButton(text="📊 За месяц")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def get_waiters_list_keyboard(waiters) -> ReplyKeyboardMarkup:
    """Get a keyboard listing waiters for selection.
    
    Args:
        waiters: List of User instances with role='waiter'.
        
    Returns:
        ReplyKeyboardMarkup with a button per waiter (id and username) and a back button.
    """
    rows = [[KeyboardButton(text=f"👤 {w.id} — {w.username}")] for w in waiters]
    rows.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_waiter_actions_keyboard(waiter_id: int) -> ReplyKeyboardMarkup:
    """Get keyboard with actions for a selected waiter (admin).
    
    Args:
        waiter_id: The waiter's user ID.
        
    Returns:
        ReplyKeyboardMarkup with actions (e.g. delete) and a back button.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"🗑 Удалить официанта ({waiter_id})")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def get_staff_waiter_keyboard() -> ReplyKeyboardMarkup:
    """Get the waiter keyboard.
    
    Returns:
        ReplyKeyboardMarkup with waiter actions.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍣 Меню"), KeyboardButton(text="🍽️ Столы")],
            [KeyboardButton(text="🚪 Выйти")],
        ],
        resize_keyboard=True,
    )


def _table_button_text(table_number: int, info: Optional[dict] = None) -> str:
    """Build the button label for a table.

    The label tells the waiter at a glance:
      • whether the table is open and assigned to *them* (shown with a
        cart total),
      • whether it is open but belongs to another waiter (🔒),
      • whether the guest has requested payment / is awaiting payment
        confirmation (🔔 / ⏳ / ✅).

    Args:
        table_number: The table number.
        info: Optional dict with keys 'total' (float), 'is_mine' (bool),
            'payment_status' (str). When None or when the table is not
            open, a plain "Стол N" label is returned.

    Returns:
        The button label string. The label always starts with "Стол N"
        so the handler can parse the number reliably.
    """
    base = f"Стол {table_number}"
    if not info or not info.get("is_open"):
        return base

    # Open but assigned to a different waiter — show a lock so the
    # current waiter knows it's not theirs to manage.
    if not info.get("is_mine"):
        return f"{base} 🔒"

    total = info.get("total", 0.0)
    payment_status = info.get("payment_status", "unpaid")
    suffix = {
        "requested": " 🔔",
        "payment_pending": " ⏳",
        "paid": " ✅",
    }.get(payment_status, "")
    return f"{base} • {total:.0f} ₽{suffix}"


def get_table_selection_keyboard(
    table_info: Optional[dict[int, dict]] = None,
) -> ReplyKeyboardMarkup:
    """Get keyboard for table selection.

    When ``table_info`` is provided, each table button reflects the
    table's live state for the current waiter: tables assigned to them
    show the running cart total (and a payment-state indicator), tables
    assigned to other waiters are marked with 🔒, and free tables show
    just "Стол N".

    Args:
        table_info: Optional mapping of ``table_number -> info dict``.
            Each info dict may contain: ``is_open`` (bool), ``is_mine``
            (bool), ``total`` (float), ``payment_status`` (str). If
            omitted, the keyboard shows plain "Стол N" buttons.

    Returns:
        ReplyKeyboardMarkup with table buttons and back button.
    """
    table_info = table_info or {}
    tables = [
        KeyboardButton(text=_table_button_text(i, table_info.get(i)))
        for i in range(1, settings.total_tables + 1)
    ]

    # Arrange tables in rows of 3
    rows = [tables[i:i + 3] for i in range(0, len(tables), 3)]
    rows.append([KeyboardButton(text="⬅️ Назад")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Get a simple cancel keyboard.
    
    Returns:
        ReplyKeyboardMarkup with a cancel button.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def get_staff_table_actions_keyboard(
    table_number: int,
    payment_status: Optional[str] = None,
    is_open: bool = True,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """Get inline keyboard with actions for a specific open table.

    The buttons shown depend on the table's payment status:
      - 'payment_pending' → show a "Confirm payment" button alongside
        "Close table" (the waiter may either confirm explicitly or just
        close — closing a table marks it as paid automatically).
      - any other status → show a "Close table" button. Closing a table is
        itself the confirmation that the guest has paid, so it is always
        allowed and auto-marks the payment as 'paid' if needed.

    Args:
        table_number: The table number to manage.
        payment_status: The current payment_status of the table assignment
            (e.g. 'unpaid', 'requested', 'payment_pending', 'paid').
        is_open: Whether the table currently has an open assignment. When
            False (e.g. a stuck 'closed' table that still has a pending
            payment), the "Confirm payment" button is hidden because it
            requires an open assignment; only "Close table" is offered so
            staff can reset/release the table.
        is_admin: When True, an extra "Unassign table" button is offered so
            an admin can pull the table off its current waiter without
            clearing the cart.

    Returns:
        InlineKeyboardMarkup with the appropriate action buttons.
    """
    rows: list[list[InlineKeyboardButton]] = []

    close_button = InlineKeyboardButton(
        text="🚪 Закрыть стол",
        callback_data=f"staff_close_table_{table_number}",
    )

    # "Confirm payment" only works for an OPEN table whose guest pressed
    # "Pay" (payment_status='payment_pending'). For a closed/stuck table
    # there is no open assignment, so confirming is impossible — in that
    # case we only offer "Close table", which resets and releases it.
    if is_open and payment_status == "payment_pending":
        rows.append([
            InlineKeyboardButton(
                text="✅ Подтвердить оплату",
                callback_data=f"staff_confirm_payment_{table_number}",
            )
        ])

    # Admins can pull a table off its waiter without closing/clearing it.
    if is_admin and is_open:
        rows.append([
            InlineKeyboardButton(
                text="↩️ Снять с официанта",
                callback_data=f"staff_unassign_table_{table_number}",
            )
        ])

    # Closing a table is itself the confirmation that the guest has paid:
    # it auto-marks the payment as 'paid' (if needed) and releases the
    # table. It is always offered so staff can resolve any table state,
    # including stuck "closed + payment_pending" ones.
    rows.append([close_button])

    return InlineKeyboardMarkup(inline_keyboard=rows)
