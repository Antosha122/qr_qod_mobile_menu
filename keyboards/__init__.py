"""Keyboard factories for both bots."""
from .guest_keyboards import (
    get_main_menu_keyboard,
    get_categories_keyboard,
    get_cart_keyboard,
    get_empty_cart_keyboard,
    get_checkout_keyboard,
    get_close_table_keyboard,
    get_quantity_keyboard,
    get_payment_keyboard,
)
from .staff_keyboards import (
    get_staff_main_keyboard,
    get_staff_admin_keyboard,
    get_staff_waiter_keyboard,
    get_table_selection_keyboard,
    get_cancel_keyboard,
)

__all__ = [
    # Guest keyboards
    "get_main_menu_keyboard",
    "get_categories_keyboard",
    "get_cart_keyboard",
    "get_empty_cart_keyboard",
    "get_checkout_keyboard",
    "get_close_table_keyboard",
    "get_quantity_keyboard",
    "get_payment_keyboard",
    # Staff keyboards
    "get_staff_main_keyboard",
    "get_staff_admin_keyboard",
    "get_staff_waiter_keyboard",
    "get_table_selection_keyboard",
    "get_cancel_keyboard",
]