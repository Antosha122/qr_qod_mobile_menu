"""Handlers for the staff (waiters/admin) bot.

This bot handles staff authentication, menu viewing, table management,
waiter assignment, and order management.
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.staff_keyboards import (
    get_staff_main_keyboard,
    get_staff_admin_keyboard,
    get_staff_waiter_keyboard,
    get_table_selection_keyboard,
    get_cancel_keyboard,
    get_staff_table_actions_keyboard,
    get_report_keyboard,
    get_waiters_list_keyboard,
    get_waiter_actions_keyboard,
)
from middlewares.auth_middleware import set_session, clear_session, get_session
from services import (
    AuthService,
    CartService,
    MenuService,
    OrderService,
    TableService,
    PaymentConfirmationError,
)
from states import StaffStates
from utils.formatters import (
    format_cart_message,
    format_assignment_message,
    format_revenue_report,
    format_waiter_stats_report,
)

logger = logging.getLogger(__name__)


def create_staff_router() -> Router:
    """Create and configure the staff bot router with all handlers.
    
    Returns:
        Configured Router instance.
    """
    router = Router(name="staff")
    
    @router.message(CommandStart())
    async def staff_start(message: Message, state: FSMContext, **kwargs):
        """Handle /start command for staff bot."""
        user_id = message.from_user.id
        session = get_session(user_id)
        
        if session:
            # Already authenticated - find role
            auth_service: AuthService = kwargs["auth_service"]
            user = await auth_service._user_repo.find_by_username(session)
            if user:
                keyboard = get_staff_main_keyboard(user.role)
                await message.answer(
                    f"👋 Вы вошли как {session} ({user.role}).",
                    reply_markup=keyboard,
                )
                return
        
        await message.answer(
            "🔑 Введите логин и пароль в формате login:password"
        )
        await state.set_state(StaffStates.waiting_for_login)
    
    @router.message(StaffStates.waiting_for_login)
    async def process_login(message: Message, state: FSMContext, **kwargs):
        """Process login credentials."""
        auth_service: AuthService = kwargs["auth_service"]
        
        if ":" not in message.text:
            await message.answer(
                "❌ Неверный формат. Используйте: login:password"
            )
            return
        
        username, password = message.text.split(":", 1)
        username = username.strip()
        password = password.strip()
        
        user = await auth_service.authenticate(username, password)
        if user is None:
            await message.answer("❌ Неверный логин или пароль.")
            return
        
        # Update chat_id for notifications
        if user.chat_id != message.chat.id:
            await auth_service.update_chat_id(user.id, message.chat.id)
        
        set_session(message.from_user.id, username)
        await state.clear()
        
        keyboard = get_staff_main_keyboard(user.role)
        await message.answer(
            f"✅ Добро пожаловать, {username}! Роль: {user.role}",
            reply_markup=keyboard,
        )
    
    @router.message(F.text == "🚪 Выйти")
    async def logout(message: Message, state: FSMContext, **kwargs):
        """Handle logout."""
        clear_session(message.from_user.id)
        await state.clear()
        await message.answer("👋 Вы вышли из системы.")
        await staff_start(message, state, **kwargs)
    
    @router.message(F.text == "❌ Отмена")
    async def cancel_action(message: Message, state: FSMContext, **kwargs):
        """Handle cancel button."""
        user_id = message.from_user.id
        session = get_session(user_id)
        
        await state.clear()
        
        if session:
            auth_service: AuthService = kwargs["auth_service"]
            user = await auth_service._user_repo.find_by_username(session)
            if user:
                keyboard = get_staff_main_keyboard(user.role)
                await message.answer("❌ Действие отменено.", reply_markup=keyboard)
                return
        
        await message.answer("❌ Действие отменено.")
    
    @router.message(F.text == "👨‍🍳 Добавить официанта")
    async def add_waiter_start(message: Message, state: FSMContext, **kwargs):
        """Start add waiter flow (admin only)."""
        user_id = message.from_user.id
        session = get_session(user_id)
        
        if not session:
            await message.answer("❌ Сначала войдите в систему.")
            return
        
        auth_service: AuthService = kwargs["auth_service"]
        user = await auth_service._user_repo.find_by_username(session)
        if user is None or user.role != "admin":
            await message.answer("❌ Только администратор может добавлять официантов.")
            return
        
        await message.answer(
            "👤 Введите логин и пароль для нового официанта (login:password):",
            reply_markup=get_cancel_keyboard(),
        )
        await state.set_state(StaffStates.waiting_for_waiter_credentials)
    
    @router.message(StaffStates.waiting_for_waiter_credentials)
    async def process_add_waiter(message: Message, state: FSMContext, **kwargs):
        """Process new waiter credentials."""
        auth_service: AuthService = kwargs["auth_service"]
        
        if ":" not in message.text:
            await message.answer("❌ Неверный формат. Используйте: login:password")
            return
        
        username, password = message.text.split(":", 1)
        username = username.strip()
        password = password.strip()
        
        try:
            await auth_service.add_waiter(username, password)
            await message.answer(
                f"✅ Официант {username} успешно добавлен!",
                reply_markup=get_staff_admin_keyboard(),
            )
            await state.clear()
        except ValueError as e:
            await message.answer(f"❌ {e}")
    
    async def _build_table_info(
        current_user_id: Optional[int],
        is_admin: bool = False,
        **kwargs,
    ) -> dict[int, dict]:
        """Build live per-table info for the table selection keyboard.

        For each open table the returned dict contains:
          - ``is_open``: True
          - ``is_mine``: True if the table is assigned to the current
            waiter (always True for admins, who oversee the whole floor)
          - ``total``: current cart total for the table
          - ``payment_status``: the table's payment status

        Closed/empty tables are omitted from the dict, which makes the
        keyboard render them as plain "Стол N".

        Args:
            current_user_id: The staff user's DB id (None if unknown).
            is_admin: When True, every open table is treated as "mine"
                so the admin sees totals for all tables (no 🔒 markers).
            **kwargs: Handler kwargs with services injected.

        Returns:
            Mapping of ``table_number -> info dict``.
        """
        table_service: TableService = kwargs["table_service"]
        cart_service: CartService = kwargs["cart_service"]

        info: dict[int, dict] = {}
        open_tables = await table_service.get_all_open_tables()
        for assignment in open_tables:
            total = await cart_service.get_cart_total(assignment.table_number)
            info[assignment.table_number] = {
                "is_open": True,
                "is_mine": is_admin or assignment.waiter_id == current_user_id,
                "total": total,
                "payment_status": assignment.payment_status,
            }
        return info

    @router.message(F.text == "🍽️ Столы")
    async def show_tables(message: Message, state: FSMContext, **kwargs):
        """Show table selection with live waiter/table info.

        For each open table the buttons show who owns it and the running
        cart total: the waiter's own tables are annotated with the amount
        and a payment-state icon, while tables assigned to other waiters
        are marked with 🔒.
        """
        user_id = message.from_user.id
        session = get_session(user_id)

        if not session:
            await message.answer("❌ Сначала войдите в систему.")
            return

        auth_service: AuthService = kwargs["auth_service"]
        user = await auth_service._user_repo.find_by_username(session)
        current_user_id = user.id if user else None
        is_admin = bool(user and user.role == "admin")

        table_info = await _build_table_info(
            current_user_id, is_admin=is_admin, **kwargs
        )

        await message.answer(
            "🍽️ Выберите стол:",
            reply_markup=get_table_selection_keyboard(table_info),
        )
        await state.set_state(StaffStates.selecting_table)

    @router.message(StaffStates.selecting_table, F.text.startswith("Стол "))
    async def select_table(message: Message, state: FSMContext, **kwargs):
        """Handle table selection - show orders or manage."""
        # Button labels look like "Стол 3", "Стол 3 • 1200 ₽" or "Стол 3 🔒".
        # The table number is always the first whitespace-separated token
        # after "Стол".
        table_number = int(message.text.split(maxsplit=1)[1].split()[0])
        
        cart_service: CartService = kwargs["cart_service"]
        order_service: OrderService = kwargs["order_service"]
        table_service: TableService = kwargs["table_service"]
        
        # Get cart items for this table
        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)
        
        # Get assignment info. If the table is unassigned, try to auto-assign
        # it to the least busy (or free) waiter automatically.
        assignment = await table_service.get_assignment(table_number)
        if assignment is None:
            assignment = await table_service.auto_assign_waiter(table_number)
        
        response = f"🍽️ **Стол {table_number}**\n\n"

        is_open = assignment is not None and assignment.status == "open"

        # Resolve the current staff user's role so we can offer admin-only
        # actions (e.g. unassigning a table).
        session = get_session(message.from_user.id)
        current_is_admin = False
        if session:
            auth_user = await kwargs["auth_service"]._user_repo.find_by_username(session)
            if auth_user:
                current_is_admin = auth_user.role == "admin"
        if assignment:
            response += format_assignment_message(assignment) + "\n\n"
        else:
            response += "👤 Стол не закреплён за официантом (нет доступных официантов).\n\n"

        if items:
            response += format_cart_message(items, total, table_number)
        else:
            response += "🛒 Заказов нет."

        await message.answer(response)

        # Show the action buttons whenever staff may need to act on the
        # table: when it is open, OR when it is in a non-fresh state that
        # needs resolving (e.g. a stuck "closed + payment_pending" table
        # that the guest could still pay into because the cart wasn't
        # cleared). A freshly closed table (status='closed',
        # payment_status='unpaid') needs no action.
        payment_status = assignment.payment_status if assignment else None
        needs_action = is_open or (payment_status not in (None, "unpaid"))
        if needs_action:
            await message.answer(
                "Действия по столу:",
                reply_markup=get_staff_table_actions_keyboard(
                    table_number,
                    payment_status,
                    is_open=is_open,
                    is_admin=current_is_admin,
                ),
            )
        
        await state.clear()
        
        # Return to main keyboard
        session = get_session(message.from_user.id)
        if session:
            auth_service: AuthService = kwargs["auth_service"]
            user = await auth_service._user_repo.find_by_username(session)
            if user:
                await message.answer(
                    "Главное меню:",
                    reply_markup=get_staff_main_keyboard(user.role),
                )
    
    @router.message(F.text == "🍣 Меню")
    async def view_menu(message: Message, state: FSMContext, **kwargs):
        """View full menu."""
        menu_service: MenuService = kwargs["menu_service"]
        
        categories = await menu_service.get_all_categories()
        if not categories:
            await message.answer("📭 Меню пустое.")
            return
        
        response = "🍣 **Меню ресторана:**\n\n"
        for category in categories:
            response += f"📂 **{category.name}**\n"
            items = await menu_service.get_items_by_category(category.id)
            for item in items:
                response += f"  • {item.name} — {item.price:.0f} ₽\n"
            response += "\n"
        
        await message.answer(response)
    
    @router.message(F.text == "⬅️ Назад")
    async def back_to_main(message: Message, state: FSMContext, **kwargs):
        """Return to main menu."""
        await state.clear()
        user_id = message.from_user.id
        session = get_session(user_id)
        
        if session:
            auth_service: AuthService = kwargs["auth_service"]
            user = await auth_service._user_repo.find_by_username(session)
            if user:
                keyboard = get_staff_main_keyboard(user.role)
                await message.answer("Главное меню:", reply_markup=keyboard)
                return
        
        await message.answer("Главное меню.")
    
    @router.message(F.text == "📋 Заказы")
    async def view_orders(message: Message, state: FSMContext, **kwargs):
        """View all orders."""
        order_service: OrderService = kwargs["order_service"]
        
        orders = await order_service.get_all_orders()
        if not orders:
            await message.answer("📭 Заказов пока нет.")
            return
        
        response = "📋 **Все заказы:**\n\n"
        for order in orders[:10]:  # Show last 10 orders
            status_emoji = {
                "pending": "⏳",
                "accepted": "✅",
                "preparing": "👨‍🍳",
                "ready": "🔔",
                "served": "🍽️",
                "closed": "🚪",
            }.get(order.status, "📋")
            response += f"{status_emoji} #{order.id} — Стол {order.table_number} — {order.status}\n"
        
        await message.answer(response)

    @router.callback_query(F.data.startswith("staff_confirm_payment_"))
    async def staff_confirm_payment(callback: CallbackQuery, **kwargs):
        """A staff member confirms the guest's payment for a table.

        Only the waiter assigned to the table may confirm the payment
        (admins may override). The table can only be closed AFTER this
        confirmation.
        """
        table_number = int(callback.data.replace("staff_confirm_payment_", ""))
        table_service: TableService = kwargs["table_service"]
        auth_service: AuthService = kwargs["auth_service"]

        # Resolve the confirmer's staff user id and role.
        confirmer_id = None
        is_admin = False
        session = get_session(callback.from_user.id)
        if session:
            user = await auth_service._user_repo.find_by_username(session)
            if user:
                confirmer_id = user.id
                is_admin = user.role == "admin"

        if confirmer_id is None:
            await callback.answer(
                "❌ Сначала войдите в систему.", show_alert=True
            )
            return

        try:
            confirmed = await table_service.confirm_payment(
                table_number, confirmer_id, is_admin=is_admin
            )
        except PaymentConfirmationError:
            await callback.answer(
                "❌ Только официант, обслуживающий этот стол (или администратор), "
                "может подтвердить оплату.",
                show_alert=True,
            )
            return
        except ValueError as e:
            await callback.answer(f"❌ {e}", show_alert=True)
            return

        if not confirmed:
            await callback.answer(
                f"Не удалось подтвердить оплату для стола {table_number}.",
                show_alert=True,
            )
            return

        await callback.message.edit_text(
            f"✅ Оплата для стола {table_number} подтверждена. "
            f"Теперь стол можно закрыть."
        )
        await callback.answer(f"Оплата стола {table_number} подтверждена.")

    async def _require_admin(message_or_cb, **kwargs):
        """Resolve the current staff user and enforce admin role.

        Returns the User instance if the caller is an admin, otherwise None
        (and sends an error message).
        """
        session = get_session(message_or_cb.from_user.id)
        if not session:
            if isinstance(message_or_cb, CallbackQuery):
                await message_or_cb.answer("❌ Сначала войдите в систему.", show_alert=True)
            else:
                await message_or_cb.answer("❌ Сначала войдите в систему.")
            return None
        auth_service: AuthService = kwargs["auth_service"]
        user = await auth_service._user_repo.find_by_username(session)
        if user is None or user.role != "admin":
            msg = "❌ Эта функция доступна только администратору."
            if isinstance(message_or_cb, CallbackQuery):
                await message_or_cb.answer(msg, show_alert=True)
            else:
                await message_or_cb.answer(msg)
            return None
        return user

    @router.message(F.text == "🧾 Отчёты")
    async def show_reports_menu(message: Message, state: FSMContext, **kwargs):
        """Show the reports period selection menu (admin only)."""
        user = await _require_admin(message, **kwargs)
        if user is None:
            return
        await message.answer(
            "🧾 Выберите период для отчёта:", reply_markup=get_report_keyboard()
        )

    @router.message(F.text == "📊 За день")
    async def report_day(message: Message, state: FSMContext, **kwargs):
        """Show revenue and waiter stats for the last day."""
        await _send_report(message, "day", **kwargs)

    @router.message(F.text == "📊 За неделю")
    async def report_week(message: Message, state: FSMContext, **kwargs):
        """Show revenue and waiter stats for the last week."""
        await _send_report(message, "week", **kwargs)

    @router.message(F.text == "📊 За месяц")
    async def report_month(message: Message, state: FSMContext, **kwargs):
        """Show revenue and waiter stats for the last month."""
        await _send_report(message, "month", **kwargs)

    async def _send_report(message: Message, period: str, **kwargs):
        """Build and send the revenue + per-waiter stats report for a period."""
        user = await _require_admin(message, **kwargs)
        if user is None:
            return
        table_service: TableService = kwargs["table_service"]
        total_amount, bill_count = await table_service.get_revenue(period)
        stats = await table_service.get_waiter_stats(period)
        text = format_revenue_report(period, total_amount, bill_count)
        text += "\n\n" + format_waiter_stats_report(period, stats)
        await message.answer(text, reply_markup=get_staff_admin_keyboard())

    @router.message(F.text == "👥 Официанты")
    async def show_waiters_menu(message: Message, state: FSMContext, **kwargs):
        """Show the list of waiters for management (admin only)."""
        user = await _require_admin(message, **kwargs)
        if user is None:
            return
        auth_service: AuthService = kwargs["auth_service"]
        waiters = await auth_service.get_all_waiters()
        if not waiters:
            await message.answer("👥 Официантов пока нет.")
            return
        await message.answer(
            "👥 Выберите официанта:",
            reply_markup=get_waiters_list_keyboard(waiters),
        )
        await state.set_state(StaffStates.selecting_waiter)

    @router.message(StaffStates.selecting_waiter, F.text.startswith("👤"))
    async def select_waiter(message: Message, state: FSMContext, **kwargs):
        """Show actions for a selected waiter (admin only)."""
        user = await _require_admin(message, **kwargs)
        if user is None:
            return
        # Button label: "👤 {id} — {username}".
        waiter_id = int(message.text.split()[1])
        auth_service: AuthService = kwargs["auth_service"]
        target = await auth_service.get_user_by_id(waiter_id)
        if target is None:
            await message.answer("❌ Официант не найден.")
            await state.clear()
            return
        await state.update_data(selected_waiter_id=waiter_id)
        await message.answer(
            f"👤 **{target.username}** (ID: {target.id}, роль: {target.role})\n\n"
            "Выберите действие:",
            reply_markup=get_waiter_actions_keyboard(waiter_id),
        )
        await state.set_state(StaffStates.confirming_waiter_delete)

    @router.message(StaffStates.confirming_waiter_delete, F.text.startswith("🗑 Удалить"))
    async def delete_waiter(message: Message, state: FSMContext, **kwargs):
        """Delete the selected waiter (admin only)."""
        user = await _require_admin(message, **kwargs)
        if user is None:
            return
        data = await state.get_data()
        waiter_id = data.get("selected_waiter_id")
        if waiter_id is None:
            await message.answer("❌ Официант не выбран.")
            await state.clear()
            return
        auth_service: AuthService = kwargs["auth_service"]
        try:
            deleted = await auth_service.delete_waiter(waiter_id)
        except ValueError as e:
            await message.answer(f"❌ {e}", reply_markup=get_staff_admin_keyboard())
            await state.clear()
            return
        if deleted:
            await message.answer(
                f"✅ Официант (ID: {waiter_id}) удалён.",
                reply_markup=get_staff_admin_keyboard(),
            )
        else:
            await message.answer(
                "❌ Не удалось удалить официанта.",
                reply_markup=get_staff_admin_keyboard(),
            )
        await state.clear()

    @router.callback_query(F.data.startswith("staff_unassign_table_"))
    async def staff_unassign_table(callback: CallbackQuery, **kwargs):
        """Admin pulls a table off its current waiter (keeps the cart)."""
        user = await _require_admin(callback, **kwargs)
        if user is None:
            return
        table_number = int(callback.data.replace("staff_unassign_table_", ""))
        table_service: TableService = kwargs["table_service"]
        unassigned = await table_service.unassign_table(table_number)
        if not unassigned:
            await callback.answer(
                f"Стол {table_number} не был закреплён за официантом.",
                show_alert=True,
            )
            return
        await callback.message.edit_text(
            f"↩️ Стол {table_number} снят с официанта. Корзина сохранена."
        )
        await callback.answer(f"Стол {table_number} снят с официанта.")

    @router.callback_query(F.data.startswith("staff_close_table_"))
    async def staff_close_table(callback: CallbackQuery, **kwargs):
        """Close a table from staff side.

        This is the only action that releases the table. A table that was
        opened (waiter assigned) stays open and accessible to the guest until
        staff explicitly closes it here.

        Closing a table means the guest has paid: if the payment hadn't been
        confirmed explicitly yet, it is automatically marked as 'paid' before
        the table is released.
        """
        table_number = int(callback.data.replace("staff_close_table_", ""))
        table_service: TableService = kwargs["table_service"]

        closed = await table_service.close_table(table_number)

        if not closed:
            await callback.answer(
                f"Не удалось закрыть стол {table_number} (он уже закрыт или не найден).",
                show_alert=True,
            )
            return

        await callback.message.edit_text(
            f"🚪 Стол {table_number} закрыт. Корзина очищена."
        )
        await callback.answer(f"Стол {table_number} закрыт.")

    return router
