"""Reply keyboards for the staff (waiters/admin) bot."""
from typing import Optional

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config.settings import settings


def get_staff_main_keyboard(role: str) -> ReplyKeyboardMarkup:
    """Get the main keyboard based on user role."""
    if role == "waiter":
        return get_staff_waiter_keyboard()
    return get_staff_admin_keyboard()


def get_staff_admin_keyboard() -> ReplyKeyboardMarkup:
    """Get the admin keyboard with all available actions."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍣 Меню"), KeyboardButton(text="🍽️ Столы")],
            [KeyboardButton(text="👨‍🍳 Добавить официанта"), KeyboardButton(text="🧾 Отчёты")],
            [KeyboardButton(text="👥 Официанты"), KeyboardButton(text="📋 Заказы")],
            [KeyboardButton(text="🔑 Сменить пароль"), KeyboardButton(text="🚪 Выйти")],
        ],
        resize_keyboard=True,
    )


def get_report_keyboard() -> ReplyKeyboardMarkup:
    """Get keyboard for choosing a reporting period."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 За день"), KeyboardButton(text="📊 За неделю"), KeyboardButton(text="📊 За месяц")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def get_waiters_list_keyboard(waiters) -> ReplyKeyboardMarkup:
    """Get a keyboard listing waiters for selection."""
    rows = [[KeyboardButton(text=f"👤 {w.id} — {w.username}")] for w in waiters]
    rows.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_waiter_actions_keyboard(waiter_id: int) -> ReplyKeyboardMarkup:
    """Get keyboard with actions for a selected waiter (admin)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"🗑 Удалить официанта ({waiter_id})")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def get_staff_waiter_keyboard() -> ReplyKeyboardMarkup:
    """Get the waiter keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍣 Меню"), KeyboardButton(text="🍽️ Столы")],
            [KeyboardButton(text="🔑 Сменить пароль"), KeyboardButton(text="🚪 Выйти")],
        ],
        resize_keyboard=True,
    )


def _table_button_text(table_number: int, info: Optional[dict] = None) -> str:
    """Build the button label for a table."""
    base = f"Стол {table_number}"
    if not info or not info.get("is_open"):
        return base

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
    """Get keyboard for table selection."""
    table_info = table_info or {}
    tables = [
        KeyboardButton(text=_table_button_text(i, table_info.get(i)))
        for i in range(1, settings.total_tables + 1)
    ]

    rows = [tables[i:i + 3] for i in range(0, len(tables), 3)]
    rows.append([KeyboardButton(text="⬅️ Назад")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Get a simple cancel keyboard."""
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
    """Get inline keyboard with actions for a specific open table."""
    rows: list[list[InlineKeyboardButton]] = []

    close_button = InlineKeyboardButton(
        text="🚪 Закрыть стол",
        callback_data=f"staff_close_table_{table_number}",
    )

    if is_open and payment_status == "payment_pending":
        rows.append([
            InlineKeyboardButton(
                text="✅ Подтвердить оплату",
                callback_data=f"staff_confirm_payment_{table_number}",
            )
        ])

    if is_admin and is_open:
        rows.append([
            InlineKeyboardButton(
                text="↩️ Снять с официанта",
                callback_data=f"staff_unassign_table_{table_number}",
            )
        ])

    rows.append([close_button])

    return InlineKeyboardMarkup(inline_keyboard=rows)