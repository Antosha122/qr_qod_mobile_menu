"""Handlers for the guest (customer-facing) bot.

This bot serves customers who scan QR codes at restaurant tables.
Flow: /start table_N -> browse menu -> add to cart -> checkout -> notify waiters.

The guest gets a persistent reply keyboard (like the staff bot) with quick
access to: Меню, Корзина, Оформить заказ, Оплата.
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from keyboards.guest_keyboards import (
    get_main_menu_keyboard,
    get_categories_keyboard,
    get_quantity_keyboard,
    get_cart_keyboard,
    get_empty_cart_keyboard,
    get_payment_keyboard,
)
from services import CartService, GuestSessionService, MenuService, OrderService, TableService
from utils.formatters import format_cart_message

logger = logging.getLogger(__name__)


async def _send_dish(message: Message, dish, menu_service=None):
    """Send a dish card. Uses photo if image_url exists, otherwise text only."""
    caption = f"🍴 **{dish.name}**\n"
    if dish.description:
        caption += f"{dish.description}\n"
    caption += f"💰 Цена: {dish.price:.0f} ₽"

    keyboard = get_quantity_keyboard(dish.id)

    if dish.image_url:
        await message.answer_photo(
            photo=dish.image_url,
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await message.answer(
            text=caption,
            reply_markup=keyboard,
        )


async def _invalidate_session(state: FSMContext, respond) -> None:
    """Invalidate the guest's table session.

    Called when the table the guest scanned has been closed by staff (or
    reopened for another group). The table number and session token are
    cleared from the FSM state so the guest must scan the QR code again
    before they can do anything else.
    """
    await state.update_data(table_number=None, session_assigned_at=None)
    await respond(
        "Ваш стол был закрыт. Отсканируйте QR-код на столе заново, "
        "чтобы сделать новый заказ."
    )


async def _require_active_table(
    state: FSMContext,
    guest_session_service: "GuestSessionService",
    respond,
    *,
    for_payment: bool = False,
) -> Optional[int]:
    """Validate the guest's table session via GuestSessionService.

    Thin adapter that reads FSM state, delegates the business logic to
    :class:`GuestSessionService`, and applies the resulting action (persisting
    the session token, invalidating on rescan, or surfacing an error message)
    back onto the aiogram layer.
    """
    data = await state.get_data()
    table_number = data.get("table_number")
    token = data.get("session_assigned_at")

    result = await guest_session_service.validate_table_session(
        table_number, token, for_payment=for_payment
    )

    if result.error_message is not None:
        await respond(result.error_message)

    if result.requires_rescan:
        await state.update_data(table_number=None, session_assigned_at=None)
        return None

    if result.session_assigned_at is not None:
        await state.update_data(session_assigned_at=result.session_assigned_at)

    return result.table_number


def create_guest_router() -> Router:
    """Create and configure the guest bot router with all handlers.

    Returns:
        Configured Router instance.
    """
    router = Router(name="guest")

    # ------------------------------------------------------------------ #
    # /start handlers
    # ------------------------------------------------------------------ #
    @router.message(CommandStart(deep_link=True))
    async def start_with_table(message: Message, command, state: FSMContext, **kwargs):
        """Handle /start with deep link (table_N)."""
        deep_link = command.args
        if not deep_link or not deep_link.startswith("table_"):
            await message.answer("Неверная ссылка. Отсканируйте QR-код на столе.")
            return

        table_str = deep_link.replace("table_", "")
        if not table_str.isdigit():
            await message.answer("Номер стола должен быть числом.")
            return

        table_number = int(table_str)

        # Bind the guest's session to the table's current open assignment (if
        # any). If the table is closed or has never been used, the token is
        # None and will be captured on the first checkout/payment. If staff
        # later closes this table, the token mismatch invalidates the session
        # and the guest must scan the QR code again to order further.
        table_service: TableService = kwargs["table_service"]
        assignment = await table_service.get_open_assignment(table_number)
        await state.update_data(
            table_number=table_number,
            session_assigned_at=assignment.assigned_at if assignment else None,
        )

        await message.answer(
            f"Привет! Вы за столом {table_number}.\n"
            "Используйте кнопки внизу, чтобы сделать заказ.",
            reply_markup=get_main_menu_keyboard(),
        )

    @router.message(CommandStart())
    async def start_no_table(message: Message, **kwargs):
        """Handle /start without deep link."""
        await message.answer(
            "Привет! Отсканируйте QR-код на столе, чтобы сделать заказ."
        )

    # ------------------------------------------------------------------ #
    # Reply-keyboard buttons (persistent main menu)
    # ------------------------------------------------------------------ #
    @router.message(F.text == "🍣 Меню")
    async def menu_button(
        message: Message,
        state: FSMContext,
        menu_service: MenuService,
        table_service: TableService,
        **kwargs,
    ):
        """Show categories menu (reply button 'Меню')."""
        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], message.answer
        )
        if table_number is None:
            return

        categories = await menu_service.get_all_categories()
        if not categories:
            await message.answer("Меню пока пустое.")
            return

        keyboard = get_categories_keyboard([(c.id, c.name) for c in categories])
        await message.answer("Выберите категорию:", reply_markup=keyboard)

    @router.message(F.text == "🛒 Корзина")
    async def cart_button(
        message: Message,
        state: FSMContext,
        cart_service: CartService,
        table_service: TableService,
        **kwargs,
    ):
        """Show cart contents (reply button 'Корзина')."""
        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], message.answer
        )
        if table_number is None:
            return

        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)

        if not items:
            await message.answer(
                "Ваша корзина пуста.",
                reply_markup=get_empty_cart_keyboard(),
            )
            return

        message_text = format_cart_message(items, total, table_number)
        remove_items = [(item.id, item.name) for item, _, _ in items]
        keyboard = get_cart_keyboard(remove_items)
        await message.answer(message_text, reply_markup=keyboard)

    @router.message(F.text == "✅ Оформить заказ")
    async def checkout_button(
        message: Message,
        state: FSMContext,
        cart_service: CartService,
        order_service: OrderService,
        table_service: TableService,
        **kwargs,
    ):
        """Process checkout from the reply button."""
        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], message.answer
        )
        if table_number is None:
            return

        items = await cart_service.get_items(table_number)
        if not items:
            await message.answer("Корзина пуста.")
            return

        order = await order_service.create_order_from_cart(None, table_number, "pending")

        assignment = await table_service.auto_assign_waiter(table_number)
        if assignment is not None:
            # Capture the session token: this checkout is what "opens" the
            # table for this guest, binding the session to this assignment.
            await state.update_data(session_assigned_at=assignment.assigned_at)
            logger.info(
                f"Order #{order.id}: table {table_number} assigned to "
                f"waiter {assignment.waiter_id}."
            )

        await message.answer(
            f"Заказ #{order.id} оформлен!\n"
            "Официант скоро подойдёт к вашему столу."
        )

    @router.message(F.text == "💳 Оплата")
    async def payment_button(
        message: Message,
        state: FSMContext,
        cart_service: CartService,
        table_service: TableService,
        **kwargs,
    ):
        """Request the bill from the reply button."""
        # for_payment=True: a fresh table is auto-assigned a waiter here, but
        # a table closed under an existing session is rejected (rescan).
        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], message.answer, for_payment=True
        )
        if table_number is None:
            return

        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)
        if not items:
            await message.answer("Корзина пуста — нечего оплачивать.")
            return

        await table_service.request_bill(table_number)

        message_text = (
            format_cart_message(items, total, table_number)
            + f"\n\n💳 К оплате: {total:.0f} ₽\n"
            "Нажмите «Оплатить», чтобы завершить оплату."
        )
        await message.answer(message_text, reply_markup=get_payment_keyboard())

    # ------------------------------------------------------------------ #
    # Inline-keyboard navigation
    # ------------------------------------------------------------------ #
    @router.callback_query(F.data.startswith("category_"))
    async def show_category(
        callback: CallbackQuery, state: FSMContext, menu_service: MenuService, **kwargs
    ):
        """Show dishes in selected category."""
        category_id = int(callback.data.split("_")[1])

        dishes = await menu_service.get_items_by_category(category_id)
        if not dishes:
            await callback.answer("В этой категории нет блюд.", show_alert=True)
            return

        # Acknowledge the callback so Telegram stops the loading spinner.
        await callback.answer()

        for dish in dishes:
            await _send_dish(callback.message, dish)

    @router.callback_query(F.data.startswith("add_to_cart_"))
    async def add_to_cart(
        callback: CallbackQuery,
        state: FSMContext,
        cart_service: CartService,
        table_service: TableService,
        **kwargs,
    ):
        """Add item to cart."""
        parts = callback.data.split("_")
        dish_id = int(parts[3])
        quantity = int(parts[4])

        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], lambda t: callback.answer(t, show_alert=True)
        )
        if table_number is None:
            return

        try:
            await cart_service.add_item(table_number, dish_id, quantity)
            await callback.answer(f"Добавлено: {quantity} шт.")
        except ValueError as e:
            await callback.answer(str(e), show_alert=True)

    @router.callback_query(F.data == "view_cart")
    async def view_cart(
        callback: CallbackQuery,
        state: FSMContext,
        cart_service: CartService,
        table_service: TableService,
        **kwargs,
    ):
        """Show cart contents (inline 'Корзина' button)."""
        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], lambda t: callback.answer(t, show_alert=True)
        )
        if table_number is None:
            return

        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)

        if not items:
            await callback.message.edit_text(
                "Ваша корзина пуста.",
                reply_markup=get_empty_cart_keyboard(),
            )
            await callback.answer()
            return

        message_text = format_cart_message(items, total, table_number)
        remove_items = [(item.id, item.name) for item, _, _ in items]
        keyboard = get_cart_keyboard(remove_items)
        await callback.message.edit_text(message_text, reply_markup=keyboard)
        await callback.answer()

    @router.callback_query(F.data.startswith("remove_from_cart_"))
    async def remove_from_cart(
        callback: CallbackQuery,
        state: FSMContext,
        cart_service: CartService,
        table_service: TableService,
        **kwargs,
    ):
        """Remove item from cart completely."""
        dish_id = int(callback.data.split("_")[3])

        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], lambda t: callback.answer(t, show_alert=True)
        )
        if table_number is None:
            return

        removed = await cart_service.remove_item_completely(table_number, dish_id)
        if removed:
            await callback.answer("Удалено из корзины.")
        else:
            await callback.answer("Блюдо не найдено в корзине.", show_alert=True)
            return

        # Refresh cart view
        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)

        if not items:
            await callback.message.edit_text(
                "Ваша корзина пуста.",
                reply_markup=get_empty_cart_keyboard(),
            )
        else:
            message_text = format_cart_message(items, total, table_number)
            remove_items = [(item.id, item.name) for item, _, _ in items]
            keyboard = get_cart_keyboard(remove_items)
            await callback.message.edit_text(message_text, reply_markup=keyboard)

    @router.callback_query(F.data == "checkout")
    async def checkout(
        callback: CallbackQuery,
        state: FSMContext,
        cart_service: CartService,
        order_service: OrderService,
        table_service: TableService,
        **kwargs,
    ):
        """Process checkout - create order and auto-assign a waiter."""
        table_number = await _require_active_table(
            state, kwargs["guest_session_service"], lambda t: callback.answer(t, show_alert=True)
        )
        if table_number is None:
            return

        items = await cart_service.get_items(table_number)
        if not items:
            await callback.answer("Корзина пуста.", show_alert=True)
            return

        # Create order
        order = await order_service.create_order_from_cart(None, table_number, "pending")

        # Auto-assign the least busy (or free) waiter to this table.
        assignment = await table_service.auto_assign_waiter(table_number)
        if assignment is not None:
            # Capture the session token: this checkout "opens" the table for
            # this guest, binding the session to this assignment.
            await state.update_data(session_assigned_at=assignment.assigned_at)
            logger.info(
                f"Order #{order.id}: table {table_number} assigned to "
                f"waiter {assignment.waiter_id}."
            )

        await callback.message.edit_text(
            f"Заказ #{order.id} оформлен!\n"
            "Официант скоро подойдёт к вашему столу."
        )
        await callback.answer()

    @router.callback_query(F.data == "request_bill")
    async def request_bill(
        callback: CallbackQuery,
        state: FSMContext,
        cart_service: CartService,
        table_service: TableService,
        **kwargs,
    ):
        """Guest requested the bill — show total and offer to pay."""
        # for_payment=True: a fresh table is auto-assigned here, but a table
        # closed under an existing session is rejected (rescan required).
        table_number = await _require_active_table(
            state,
            kwargs["guest_session_service"],
            lambda t: callback.answer(t, show_alert=True),
            for_payment=True,
        )
        if table_number is None:
            return

        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)
        if not items:
            await callback.answer("Корзина пуста — нечего оплачивать.", show_alert=True)
            return

        # Mark payment as requested so staff can see it in the table view.
        await table_service.request_bill(table_number)

        message_text = (
            format_cart_message(items, total, table_number)
            + f"\n\n💳 К оплате: {total:.0f} ₽\n"
            "Нажмите «Оплатить», чтобы завершить оплату."
        )
        await callback.message.edit_text(
            message_text, reply_markup=get_payment_keyboard()
        )
        await callback.answer()

    @router.callback_query(F.data == "pay_bill")
    async def pay_bill(
        callback: CallbackQuery,
        state: FSMContext,
        table_service: TableService,
        **kwargs,
    ):
        """Guest confirmed payment — mark the bill as paid.

        The table remains open and accessible to the guest until a waiter
        explicitly closes it. Once closed, the guest must scan the QR code
        again to do anything further.
        """
        # for_payment=True: a fresh table is auto-assigned here, but a table
        # closed under an existing session is rejected (rescan required).
        table_number = await _require_active_table(
            state,
            kwargs["guest_session_service"],
            lambda t: callback.answer(t, show_alert=True),
            for_payment=True,
        )
        if table_number is None:
            return

        paid = await table_service.pay_bill(table_number)
        if not paid:
            await callback.answer(
                "Стол не найден. Обратитесь к официанту.", show_alert=True
            )
            return

        await callback.message.edit_text(
            "⏳ Ожидание подтверждения оплаты.\n"
            "Официант подойдёт, чтобы подтвердить оплату. "
            "Спасибо за ожидание!"
        )
        await callback.answer()

    @router.callback_query(F.data == "back_to_categories")
    async def back_to_categories(
        callback: CallbackQuery, menu_service: MenuService, **kwargs
    ):
        """Navigate back to categories."""
        await callback.answer()
        categories = await menu_service.get_all_categories()
        if not categories:
            await callback.message.edit_text("Меню пока пустое.")
            return
        keyboard = get_categories_keyboard([(c.id, c.name) for c in categories])
        await callback.message.edit_text("Выберите категорию:", reply_markup=keyboard)

    return router