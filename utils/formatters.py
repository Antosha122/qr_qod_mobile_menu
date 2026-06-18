"""Message formatting utilities for bot responses."""
from typing import Optional

from database.models import Cart, MenuItem, Order, WaiterAssignment, ClosedBill


def format_cart_message(
    items: list[tuple[MenuItem, int, float]], total: float, table_number: Optional[int] = None
) -> str:
    """Format cart contents into a readable message.
    
    Args:
        items: List of tuples (MenuItem, quantity, line_total).
        total: Total cart price.
        table_number: Optional table number for context.
        
    Returns:
        Formatted cart message string.
    """
    if not items:
        return "🛒 Ваша корзина пуста."
    
    header = f"🛒 **Ваша корзина**"
    if table_number is not None:
        header += f" (стол {table_number})"
    header += ":\n\n"
    
    lines = []
    for item, quantity, line_total in items:
        lines.append(
            f"🍽 {item.name} — {quantity} шт. × {item.price:.0f} ₽ = {line_total:.0f} ₽"
        )
    
    lines.append(f"\n💰 **Итого: {total:.0f} ₽**")
    return header + "\n".join(lines)


def format_order_message(order: Order, items_text: Optional[str] = None) -> str:
    """Format an order into a readable message.
    
    Args:
        order: The Order instance.
        items_text: Optional pre-formatted items text.
        
    Returns:
        Formatted order message string.
    """
    status_emoji = {
        "pending": "⏳",
        "accepted": "✅",
        "preparing": "👨‍🍳",
        "ready": "🔔",
        "served": "🍽️",
        "closed": "🚪",
        "cancelled": "❌",
    }.get(order.status, "📋")
    
    message = f"{status_emoji} **Заказ #{order.id}**\n"
    message += f"📍 Стол: {order.table_number}\n"
    message += f"📊 Статус: {order.status}\n"
    if order.created_at:
        message += f"🕐 Создан: {order.created_at}\n"
    if items_text:
        message += f"\n{items_text}"
    return message


def format_revenue_report(period: str, total_amount: float, bill_count: int) -> str:
    """Format a revenue report for a given period.

    Args:
        period: 'day', 'week', or 'month'.
        total_amount: Total revenue in the period.
        bill_count: Number of closed bills in the period.

    Returns:
        Formatted revenue report string.
    """
    period_label = {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }.get(period, period)
    return (
        f"📊 **Отчёт по выручке ({period_label})**\n\n"
        f"💰 Общая сумма: {total_amount:.0f} ₽\n"
        f"🍽 Закрыто счетов: {bill_count}"
    )


def format_waiter_stats_report(period: str, stats: list[dict]) -> str:
    """Format per-waiter statistics for a given period.

    Args:
        period: 'day', 'week', or 'month'.
        stats: List of stat dicts from TableService.get_waiter_stats, each
            with keys: waiter_id, waiter_username, tables_closed,
            total_amount.

    Returns:
        Formatted per-waiter statistics string.
    """
    period_label = {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }.get(period, period)
    header = f"👥 **Статистика официантов ({period_label})**\n\n"
    if not stats:
        return header + "Нет данных за выбранный период."

    lines = []
    total_closed = 0
    grand_total = 0.0
    for s in stats:
        tables = s["tables_closed"]
        amount = s["total_amount"]
        total_closed += tables
        grand_total += amount
        lines.append(
            f"👤 {s['waiter_username']} (ID: {s['waiter_id']}) — "
            f"{tables} столов, {amount:.0f} ₽"
        )
    lines.append(f"\n**Итого:** {total_closed} столов, {grand_total:.0f} ₽")
    return header + "\n".join(lines)


def format_assignment_message(assignment: WaiterAssignment) -> str:
    """Format a waiter assignment into a readable message.
    
    Args:
        assignment: The WaiterAssignment instance.
        
    Returns:
        Formatted assignment message string.
    """
    status_emoji = "🟢" if assignment.status == "open" else "🔴"
    payment_label = {
        "unpaid": "❌ Не оплачен",
        "requested": "🔔 Запрошен счёт",
        "payment_pending": "⏳ Ожидает подтверждения оплаты",
        "paid": "✅ Оплачен",
    }.get(assignment.payment_status, assignment.payment_status)
    message = f"{status_emoji} **Стол {assignment.table_number}**\n"
    if assignment.waiter_id:
        message += f"👤 Официант ID: {assignment.waiter_id}\n"
    else:
        message += "👤 Официант: не назначен\n"
    message += f"📊 Статус: {assignment.status}\n"
    message += f"💳 Оплата: {payment_label}\n"
    if assignment.assigned_at:
        message += f"🕐 Назначен: {assignment.assigned_at}"
    return message
