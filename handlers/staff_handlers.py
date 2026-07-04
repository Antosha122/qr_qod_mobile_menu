"""Handlers for the staff (waiters/admin) bot."""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from keyboards.staff_keyboards import (
    get_staff_main_keyboard,
    get_staff_admin_keyboard,
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
    router = Router(name="staff")
    
    @router.message(CommandStart())
    async def staff_start(message: Message, state: FSMContext, **kwargs):
        session = await get_session(message.from_user.id)
        if session:
            user = await kwargs["auth_service"].get_user_by_username(session)
            if user:
                await message.answer(f"👋 Вы вошли как {session} ({user.role}).", reply_markup=get_staff_main_keyboard(user.role))
                return
        await message.answer("🔑 Введите логин и пароль в формате login:password")
        await state.set_state(StaffStates.waiting_for_login)
    
    @router.message(StaffStates.waiting_for_login)
    async def process_login(message: Message, state: FSMContext, **kwargs):
        auth_service: AuthService = kwargs["auth_service"]
        if not message.text or ":" not in message.text:
            await message.answer("❌ Неверный формат. Используйте: login:password")
            return
        username, password = message.text.split(":", 1)
        user = await auth_service.authenticate(username.strip(), password.strip())
        if user is None:
            await message.answer("❌ Неверный логин или пароль.")
            return
        if user.chat_id != message.chat.id:
            await auth_service.update_chat_id(user.id, message.chat.id)
        await set_session(message.from_user.id, username.strip())
        if user.must_change_password:
            await message.answer("🔐 Это ваш первый вход. Придумайте новый пароль:")
            await state.set_state(StaffStates.waiting_for_new_password)
            return
        await state.clear()
        await message.answer(f"✅ Добро пожаловать, {username.strip()}! Роль: {user.role}", reply_markup=get_staff_main_keyboard(user.role))
    
    @router.message(StaffStates.waiting_for_new_password)
    async def process_new_password(message: Message, state: FSMContext, **kwargs):
        auth_service: AuthService = kwargs["auth_service"]
        session = await get_session(message.from_user.id)
        if not session:
            await message.answer("❌ Сессия истекла. Войдите заново.")
            await state.clear()
            return
        user = await auth_service.get_user_by_username(session)
        if user is None:
            await message.answer("❌ Пользователь не найден. Войдите заново.")
            await state.clear()
            return
        new_password = message.text.strip() if message.text else ""
        if not new_password:
            await message.answer("❌ Пароль не может быть пустым.")
            return
        if ":" in new_password:
            await message.answer("❌ Пароль не должен содержать двоеточие.")
            return
        try:
            await auth_service.change_password(user.id, new_password)
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return
        try:
            await message.delete()
        except Exception:
            pass
        await state.clear()
        await message.answer(f"✅ Пароль успешно изменён!\nДобро пожаловать, {session}! Роль: {user.role}", reply_markup=get_staff_main_keyboard(user.role))
    
    @router.message(F.text == "🚪 Выйти")
    async def logout(message: Message, state: FSMContext, **kwargs):
        await clear_session(message.from_user.id)
        await state.clear()
        await message.answer("👋 Вы вышли из системы.")
        await staff_start(message, state, **kwargs)
    
    @router.message(F.text == "❌ Отмена")
    async def cancel_action(message: Message, state: FSMContext, **kwargs):
        session = await get_session(message.from_user.id)
        await state.clear()
        if session:
            user = await kwargs["auth_service"].get_user_by_username(session)
            if user:
                await message.answer("❌ Действие отменено.", reply_markup=get_staff_main_keyboard(user.role))
                return
        await message.answer("❌ Действие отменено.")
    
    @router.message(F.text == "🔑 Сменить пароль")
    async def change_password_start(message: Message, state: FSMContext, **kwargs):
        if not await get_session(message.from_user.id):
            await message.answer("❌ Сначала войдите в систему.")
            return
        await message.answer("🔑 Введите новый пароль:", reply_markup=get_cancel_keyboard())
        await state.set_state(StaffStates.waiting_for_new_password)
    
    @router.message(F.text == "👨‍🍳 Добавить официанта")
    async def add_waiter_start(message: Message, state: FSMContext, **kwargs):
        session = await get_session(message.from_user.id)
        if not session:
            await message.answer("❌ Сначала войдите в систему.")
            return
        user = await kwargs["auth_service"].get_user_by_username(session)
        if user is None or user.role != "admin":
            await message.answer("❌ Только администратор может добавлять официантов.")
            return
        await message.answer("👤 Введите логин и пароль для нового официанта (login:password):", reply_markup=get_cancel_keyboard())
        await state.set_state(StaffStates.waiting_for_waiter_credentials)
    
    @router.message(StaffStates.waiting_for_waiter_credentials)
    async def process_add_waiter(message: Message, state: FSMContext, **kwargs):
        auth_service: AuthService = kwargs["auth_service"]
        if not message.text or ":" not in message.text:
            await message.answer("❌ Неверный формат. Используйте: login:password")
            return
        username, password = message.text.split(":", 1)
        try:
            await auth_service.add_waiter(username.strip(), password.strip())
            await message.answer(f"✅ Официант {username.strip()} успешно добавлен!", reply_markup=get_staff_admin_keyboard())
            await state.clear()
        except ValueError as e:
            await message.answer(f"❌ {e}")
    
    @router.message(F.text == "🍽️ Столы")
    async def show_tables(message: Message, state: FSMContext, **kwargs):
        session = await get_session(message.from_user.id)
        if not session:
            await message.answer("❌ Сначала войдите в систему.")
            return
        user = await kwargs["auth_service"].get_user_by_username(session)
        current_user_id = user.id if user else None
        is_admin = bool(user and user.role == "admin")
        # Business logic moved to TableService.get_table_overview()
        table_service: TableService = kwargs["table_service"]
        table_info = await table_service.get_table_overview(current_user_id, is_admin=is_admin)
        await message.answer("🍽️ Выберите стол:", reply_markup=get_table_selection_keyboard(table_info))
        await state.set_state(StaffStates.selecting_table)
    
    @router.message(StaffStates.selecting_table, F.text.startswith("Стол "))
    async def select_table(message: Message, state: FSMContext, **kwargs):
        table_number = int(message.text.split(maxsplit=1)[1].split()[0])
        cart_service: CartService = kwargs["cart_service"]
        table_service: TableService = kwargs["table_service"]
        items = await cart_service.get_items(table_number)
        total = await cart_service.get_cart_total(table_number)
        assignment = await table_service.get_assignment(table_number)
        if assignment is None:
            assignment = await table_service.auto_assign_waiter(table_number)
        response = f"🍽️ **Стол {table_number}**\n\n"
        is_open = assignment is not None and assignment.status == "open"
        session = await get_session(message.from_user.id)
        current_is_admin = False
        if session:
            auth_user = await kwargs["auth_service"].get_user_by_username(session)
            if auth_user:
                current_is_admin = auth_user.role == "admin"
        if assignment:
            response += format_assignment_message(assignment) + "\n\n"
        else:
            response += "👤 Стол не закреплён за официантом.\n\n"
        response += format_cart_message(items, total, table_number) if items else "🛒 Заказов нет."
        await message.answer(response)
        payment_status = assignment.payment_status if assignment else None
        needs_action = is_open or (payment_status not in (None, "unpaid"))
        if needs_action:
            await message.answer("Действия по столу:", reply_markup=get_staff_table_actions_keyboard(table_number, payment_status, is_open=is_open, is_admin=current_is_admin))
        await state.clear()
        if session:
            user = await kwargs["auth_service"].get_user_by_username(session)
            if user:
                await message.answer("Главное меню:", reply_markup=get_staff_main_keyboard(user.role))
    
    @router.message(F.text == "🍣 Меню")
    async def view_menu(message: Message, state: FSMContext, **kwargs):
        menu_service: MenuService = kwargs["menu_service"]
        categories = await menu_service.get_all_categories()
        if not categories:
            await message.answer("📭 Меню пустое.")
            return
        response = "🍣 **Меню ресторана:**\n\n"
        for category in categories:
            response += f"📂 **{category.name}**\n"
            for item in await menu_service.get_items_by_category(category.id):
                response += f"  • {item.name} — {item.price:.0f} ₽\n"
            response += "\n"
        await message.answer(response)
    
    @router.message(F.text == "⬅️ Назад")
    async def back_to_main(message: Message, state: FSMContext, **kwargs):
        await state.clear()
        session = await get_session(message.from_user.id)
        if session:
            user = await kwargs["auth_service"].get_user_by_username(session)
            if user:
                await message.answer("Главное меню:", reply_markup=get_staff_main_keyboard(user.role))
                return
        await message.answer("Главное меню.")
    
    @router.message(F.text == "📋 Заказы")
    async def view_orders(message: Message, state: FSMContext, **kwargs):
        orders = await kwargs["order_service"].get_all_orders()
        if not orders:
            await message.answer("📭 Заказов пока нет.")
            return
        response = "📋 **Все заказы:**\n\n"
        for order in orders[:10]:
            emoji = {"pending": "⏳", "accepted": "✅", "preparing": "👨‍🍳", "ready": "🔔", "served": "🍽️", "closed": "🚪"}.get(order.status, "📋")
            response += f"{emoji} #{order.id} — Стол {order.table_number} — {order.status}\n"
        await message.answer(response)

    @router.callback_query(F.data.startswith("staff_confirm_payment_"))
    async def staff_confirm_payment(callback: CallbackQuery, **kwargs):
        table_number = int(callback.data.replace("staff_confirm_payment_", ""))
        table_service: TableService = kwargs["table_service"]
        auth_service: AuthService = kwargs["auth_service"]
        confirmer_id = None
        is_admin = False
        session = await get_session(callback.from_user.id)
        if session:
            user = await auth_service.get_user_by_username(session)
            if user:
                confirmer_id = user.id
                is_admin = user.role == "admin"
        if confirmer_id is None:
            await callback.answer("❌ Сначала войдите в систему.", show_alert=True)
            return
        try:
            confirmed = await table_service.confirm_payment(table_number, confirmer_id, is_admin=is_admin)
        except PaymentConfirmationError:
            await callback.answer("❌ Только официант (или администратор) может подтвердить оплату.", show_alert=True)
            return
        except ValueError as e:
            await callback.answer(f"❌ {e}", show_alert=True)
            return
        if not confirmed:
            await callback.answer(f"Не удалось подтвердить оплату для стола {table_number}.", show_alert=True)
            return
        await callback.message.edit_text(f"✅ Оплата для стола {table_number} подтверждена.")
        await callback.answer(f"Оплата стола {table_number} подтверждена.")

    async def _require_admin(message_or_cb, **kwargs):
        session = await get_session(message_or_cb.from_user.id)
        if not session:
            msg = "❌ Сначала войдите в систему."
            if isinstance(message_or_cb, CallbackQuery):
                await message_or_cb.answer(msg, show_alert=True)
            else:
                await message_or_cb.answer(msg)
            return None
        user = await kwargs["auth_service"].get_user_by_username(session)
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
        if await _require_admin(message, **kwargs) is None:
            return
        await message.answer("🧾 Выберите период для отчёта:", reply_markup=get_report_keyboard())

    @router.message(F.text == "📊 За день")
    async def report_day(message: Message, state: FSMContext, **kwargs):
        await _send_report(message, "day", **kwargs)

    @router.message(F.text == "📊 За неделю")
    async def report_week(message: Message, state: FSMContext, **kwargs):
        await _send_report(message, "week", **kwargs)

    @router.message(F.text == "📊 За месяц")
    async def report_month(message: Message, state: FSMContext, **kwargs):
        await _send_report(message, "month", **kwargs)

    async def _send_report(message: Message, period: str, **kwargs):
        if await _require_admin(message, **kwargs) is None:
            return
        table_service: TableService = kwargs["table_service"]
        total_amount, bill_count = await table_service.get_revenue(period)
        stats = await table_service.get_waiter_stats(period)
        text = format_revenue_report(period, total_amount, bill_count) + "\n\n" + format_waiter_stats_report(period, stats)
        await message.answer(text, reply_markup=get_staff_admin_keyboard())

    @router.message(F.text == "👥 Официанты")
    async def show_waiters_menu(message: Message, state: FSMContext, **kwargs):
        if await _require_admin(message, **kwargs) is None:
            return
        waiters = await kwargs["auth_service"].get_all_waiters()
        if not waiters:
            await message.answer("👥 Официантов пока нет.")
            return
        await message.answer("👥 Выберите официанта:", reply_markup=get_waiters_list_keyboard(waiters))
        await state.set_state(StaffStates.selecting_waiter)

    @router.message(StaffStates.selecting_waiter, F.text.startswith("👤"))
    async def select_waiter(message: Message, state: FSMContext, **kwargs):
        if await _require_admin(message, **kwargs) is None:
            return
        waiter_id = int(message.text.split()[1])
        target = await kwargs["auth_service"].get_user_by_id(waiter_id)
        if target is None:
            await message.answer("❌ Официант не найден.")
            await state.clear()
            return
        await state.update_data(selected_waiter_id=waiter_id)
        await message.answer(f"👤 **{target.username}** (ID: {target.id}, роль: {target.role})\n\nВыберите действие:", reply_markup=get_waiter_actions_keyboard(waiter_id))
        await state.set_state(StaffStates.confirming_waiter_delete)

    @router.message(StaffStates.confirming_waiter_delete, F.text.startswith("🗑 Удалить"))
    async def delete_waiter(message: Message, state: FSMContext, **kwargs):
        if await _require_admin(message, **kwargs) is None:
            return
        waiter_id = (await state.get_data()).get("selected_waiter_id")
        if waiter_id is None:
            await message.answer("❌ Официант не выбран.")
            await state.clear()
            return
        try:
            deleted = await kwargs["auth_service"].delete_waiter(waiter_id)
        except ValueError as e:
            await message.answer(f"❌ {e}", reply_markup=get_staff_admin_keyboard())
            await state.clear()
            return
        msg = f"✅ Официант (ID: {waiter_id}) удалён." if deleted else "❌ Не удалось удалить официанта."
        await message.answer(msg, reply_markup=get_staff_admin_keyboard())
        await state.clear()

    @router.callback_query(F.data.startswith("staff_unassign_table_"))
    async def staff_unassign_table(callback: CallbackQuery, **kwargs):
        if await _require_admin(callback, **kwargs) is None:
            return
        table_number = int(callback.data.replace("staff_unassign_table_", ""))
        if not await kwargs["table_service"].unassign_table(table_number):
            await callback.answer(f"Стол {table_number} не был закреплён за официантом.", show_alert=True)
            return
        await callback.message.edit_text(f"↩️ Стол {table_number} снят с официанта. Корзина сохранена.")
        await callback.answer(f"Стол {table_number} снят с официанта.")

    @router.callback_query(F.data.startswith("staff_close_table_"))
    async def staff_close_table(callback: CallbackQuery, **kwargs):
        table_number = int(callback.data.replace("staff_close_table_", ""))
        if not await kwargs["table_service"].close_table(table_number):
            await callback.answer(f"Не удалось закрыть стол {table_number}.", show_alert=True)
            return
        await callback.message.edit_text(f"🚪 Стол {table_number} закрыт. Корзина очищена.")
        await callback.answer(f"Стол {table_number} закрыт.")

    # Catch-all: any text from a user whose session has expired gets a clear
    # message instead of being silently ignored. This prevents confusion when
    # the user sees stale keyboard buttons from a previous (pre-restart) session.
    @router.message(F.text)
    async def catch_all_expired_session(message: Message, state: FSMContext, **kwargs):
        session = await get_session(message.from_user.id)
        if session:
            user = await kwargs["auth_service"].get_user_by_username(session)
            if user:
                await message.answer("Главное меню:", reply_markup=get_staff_main_keyboard(user.role))
                return
        # Session expired — remove stale keyboard and prompt re-login.
        await state.clear()
        await message.answer(
            "❌ Сессия истекла. Пожалуйста, войдите заново через /start",
            reply_markup=ReplyKeyboardRemove(),
        )

    return router
