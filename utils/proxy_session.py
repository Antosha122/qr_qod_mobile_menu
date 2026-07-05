"""Custom aiohttp session for aiogram with robust proxy support.

aiogram's built-in ``AiohttpSession`` uses ``aiohttp-socks`` for *all* proxy
types. However, ``aiohttp-socks`` does not correctly handle **HTTP** proxies
for HTTPS targets (TLS handshake is reset). This module provides a subclass
that:

  * For ``http://`` and ``https://`` proxies → uses aiohttp's native
    ``proxy=`` parameter (CONNECT tunneling), which works correctly.
  * For ``socks4://`` and ``socks5://`` proxies → falls back to aiogram's
    default behaviour (``aiohttp-socks`` connector).

This fixes ``ConnectionResetError`` when ``PROXY_URL`` is an HTTP proxy.
"""
from typing import Any, Dict, Optional, Type
from urllib.parse import urlparse

import certifi
import ssl
from aiohttp import TCPConnector, ClientSession, FormData
from aiogram import Bot, __version__
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import TelegramMethod
from aiohttp.client_exceptions import ClientError

from yarl import URL

import asyncio

try:
    from aiohttp import USER_AGENT, SERVER_SOFTWARE  # type: ignore
except ImportError:  # pragma: no cover — older aiohttp
    USER_AGENT = "User-Agent"
    SERVER_SOFTWARE = "Python/aiohttp"


def _is_http_proxy(proxy_url: str) -> bool:
    """Return True for ``http://`` and ``https://`` proxy schemes."""
    scheme = urlparse(proxy_url).scheme.lower()
    return scheme in ("http", "https", "")


class ProxyAwareAiohttpSession(AiohttpSession):
    """AiohttpSession subclass with robust HTTP proxy support.

    ``aiohttp-socks`` (used by aiogram's default session) mishandles HTTP
    proxies for HTTPS targets. This subclass detects HTTP proxies and routes
    them through aiohttp's native ``proxy=`` parameter instead, while still
    using ``aiohttp-socks`` for SOCKS proxies.
    """

    def __init__(self, proxy: Optional[str] = None, **kwargs: Any) -> None:
        # We bypass the parent's proxy setup entirely and do it ourselves.
        super(AiohttpSession, self).__init__(**kwargs)  # skip AiohttpSession.__init__

        self._session: Optional[ClientSession] = None
        self._connector_type: Type[TCPConnector] = TCPConnector
        self._connector_init: Dict[str, Any] = {
            "ssl": ssl.create_default_context(cafile=certifi.where()),
        }
        self._should_reset_connector: bool = True
        self._proxy: Optional[str] = None
        # For HTTP proxies, we use aiohttp's native proxy= parameter rather
        # than a custom connector. We store the proxy URL and pass it to each
        # request. For SOCKS proxies, we fall back to the parent behaviour.
        self._http_proxy_url: Optional[str] = None

        if proxy:
            proxy = proxy.strip()
            if _is_http_proxy(proxy):
                # Use aiohttp native proxy support (CONNECT tunneling).
                self._http_proxy_url = proxy
                self._proxy = proxy
            else:
                # SOCKS proxy → use aiohttp-socks via parent's setup.
                self._setup_proxy_connector(proxy)  # type: ignore[arg-type]

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: Optional[int] = None,
    ) -> Any:
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)

        request_kwargs: Dict[str, Any] = {
            "data": form,
            "timeout": self.timeout if timeout is None else timeout,
        }
        # Pass the proxy URL to aiohttp's native proxy support.
        if self._http_proxy_url:
            request_kwargs["proxy"] = self._http_proxy_url

        # Retry loop: transient proxy/network errors are retried with backoff.
        max_retries = 3
        base_delay = 2.0
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                async with session.post(url, **request_kwargs) as resp:
                    raw_result = await resp.text()
                response = self.check_response(
                    bot=bot,
                    method=method,
                    status_code=resp.status,
                    content=raw_result,
                )
                return response.result
            except asyncio.TimeoutError as e:
                last_exc = TelegramNetworkError(
                    method=method, message="Request timeout error"
                )
            except ClientError as e:
                last_exc = TelegramNetworkError(
                    method=method, message=f"{type(e).__name__}: {e}"
                )

            # If we have retries left, wait and try again.
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        # All retries exhausted → raise the last error.
        raise last_exc  # type: ignore[misc]

    async def stream_content(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> Any:
        if headers is None:
            headers = {}
        session = await self.create_session()

        request_kwargs: Dict[str, Any] = {
            "timeout": timeout,
            "headers": headers,
            "raise_for_status": raise_for_status,
        }
        if self._http_proxy_url:
            request_kwargs["proxy"] = self._http_proxy_url

        async with session.get(url, **request_kwargs) as resp:
            async for chunk in resp.content.iter_chunked(chunk_size):
                yield chunk