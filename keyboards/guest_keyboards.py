"""Inline keyboards for the guest (customer-facing) bot."""
from typing import Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Get the main reply keyboard shown after /start.

    Provides persistent access to the same core actions that staff have:
    menu, cart, checkout and payment.

    Returns:
        ReplyKeyboardMarkup with main action buttons.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍣 Меню"), KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="✅ Оформить заказ"), KeyboardButton(text="💳 Оплата")],
        ],
        resize_keyboard=True,
    )


def get_categories_keyboard(categories: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Get categories selection keyboard.

    Args:
        categories: List of tuples (category_id, category_name).

    Returns:
        InlineKeyboardMarkup with category buttons and cart.
    """
    keyboard = [
        [InlineKeyboardButton(text=f"🍽 {name}", callback_data=f"category_{cat_id}")]
        for cat_id, name in categories
    ]
    keyboard.append([InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_quantity_keyboard(dish_id: int) -> InlineKeyboardMarkup:
    """Get quantity selection keyboard for a dish.

    Args:
        dish_id: The menu item ID.

    Returns:
        InlineKeyboardMarkup with quantity buttons 1-5.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=str(i), callback_data=f"add_to_cart_{dish_id}_{i}")
                for i in range(1, 6)
            ]
        ]
    )


def get_cart_keyboard(
    items: Optional[list[tuple[int, str]]] = None,
) -> InlineKeyboardMarkup:
    """Get cart keyboard with remove buttons and checkout.

    Args:
        items: Optional list of tuples (menu_item_id, dish_name) for removal buttons.

    Returns:
        InlineKeyboardMarkup with remove, back and checkout buttons.
    """
    keyboard = []

    if items:
        for menu_item_id, dish_name in items:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑️ {dish_name}",
                    callback_data=f"remove_from_cart_{menu_item_id}",
                )
            ])

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_categories")])
    keyboard.append([InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")])
    keyboard.append([InlineKeyboardButton(text="💳 Запросить счёт", callback_data="request_bill")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_empty_cart_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for empty cart state.

    Returns:
        InlineKeyboardMarkup with back to menu button only.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_categories")]
        ]
    )


def get_checkout_keyboard(table_number: int) -> InlineKeyboardMarkup:
    """Get keyboard for checkout confirmation sent to waiters.

    Args:
        table_number: The table number being checked out.

    Returns:
        InlineKeyboardMarkup with accept table button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять стол", callback_data=f"accept_table_{table_number}")]
        ]
    )


def get_close_table_keyboard(table_number: int) -> InlineKeyboardMarkup:
    """Get keyboard for closing a table (shown to waiter).

    Args:
        table_number: The table number to close.

    Returns:
        InlineKeyboardMarkup with close table button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Закрыть стол", callback_data=f"close_table_{table_number}")]
        ]
    )


def get_payment_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for the guest to pay the bill after requesting it.

    Returns:
        InlineKeyboardMarkup with a pay button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", callback_data="pay_bill")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_categories")],
        ]
    )