"""Service middleware for dependency injection."""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services import (
    AuthService,
    CartService,
    MenuService,
    OrderService,
    TableService,
)


class ServiceMiddleware(BaseMiddleware):
    """Injects service instances into handler kwargs.
    
    This allows handlers to access services via `data['services']` or individual
    services via their names (e.g., `data['menu_service']`).
    """

    def __init__(
        self,
        auth_service: AuthService,
        menu_service: MenuService,
        cart_service: CartService,
        order_service: OrderService,
        table_service: TableService,
    ):
        self._services = {
            "auth_service": auth_service,
            "menu_service": menu_service,
            "cart_service": cart_service,
            "order_service": order_service,
            "table_service": table_service,
        }

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Inject all services into handler data
        data.update(self._services)
        return await handler(event, data)