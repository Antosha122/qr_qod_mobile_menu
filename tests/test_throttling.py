"""Tests for the ThrottlingMiddleware rate-limiting logic."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from middlewares.throttling_middleware import (
    ThrottlingMiddleware,
    _check_rate_limit,
    _memory,
)


class TestRateLimitLogic:
    """Tests for the _check_rate_limit helper function (in-memory mode)."""

    def setup_method(self):
        """Clear in-memory state before each test."""
        _memory.clear()

    async def test_allows_under_limit(self):
        """Requests under the limit are allowed."""
        for _ in range(5):
            allowed = await _check_rate_limit(1, "login", 5, 60)
            assert allowed is True

    async def test_blocks_over_limit(self):
        """Requests over the limit are blocked."""
        for _ in range(3):
            await _check_rate_limit(1, "login", 3, 60)
        # 4th request should be blocked.
        allowed = await _check_rate_limit(1, "login", 3, 60)
        assert allowed is False

    async def test_separate_keys_independent(self):
        """Different keys have independent limits."""
        # Exhaust the "login" limit.
        for _ in range(5):
            await _check_rate_limit(1, "login", 5, 60)
        assert await _check_rate_limit(1, "login", 5, 60) is False
        # "cart" key should still be allowed.
        assert await _check_rate_limit(1, "cart", 5, 60) is True

    async def test_separate_users_independent(self):
        """Different users have independent limits."""
        for _ in range(5):
            await _check_rate_limit(1, "login", 5, 60)
        assert await _check_rate_limit(1, "login", 5, 60) is False
        # User 2 should still be allowed.
        assert await _check_rate_limit(2, "login", 5, 60) is True

    async def test_window_expiry(self):
        """Old requests outside the window are pruned."""
        # Fill the limit with a 1-second window.
        for _ in range(3):
            await _check_rate_limit(1, "test", 3, 1)
        assert await _check_rate_limit(1, "test", 3, 1) is False
        # Wait for the window to expire.
        await asyncio.sleep(1.1)
        assert await _check_rate_limit(1, "test", 3, 1) is True


class TestThrottlingMiddleware:
    """Tests for the ThrottlingMiddleware aiogram middleware."""

    def setup_method(self):
        """Clear in-memory state before each test."""
        _memory.clear()

    async def test_allows_normal_request(self):
        """Normal requests within limits pass through to the handler."""
        mw = ThrottlingMiddleware()
        handler = AsyncMock(return_value="ok")

        user = MagicMock(id=123)
        message = MagicMock()
        data = {"event_from_user": user, "event": message}

        result = await mw(handler, message, data)
        assert result == "ok"
        handler.assert_called_once()

    async def test_blocks_excessive_requests(self):
        """Requests exceeding the limit are dropped (None returned)."""
        # Use a custom limit: 2 calls per 60s.
        mw = ThrottlingMiddleware(limits={"default": (2, 60)})
        handler = AsyncMock(return_value="ok")

        user = MagicMock(id=123)
        message = MagicMock()
        data = {"event_from_user": user, "event": message}

        # First 2 requests pass.
        await mw(handler, message, data)
        await mw(handler, message, data)
        # 3rd request is blocked.
        result = await mw(handler, message, data)
        assert result is None
        assert handler.call_count == 2  # Only called for the first 2.

    async def test_no_user_passes_through(self):
        """Updates without a user (e.g. channel posts) are not throttled."""
        mw = ThrottlingMiddleware()
        handler = AsyncMock(return_value="ok")

        event = MagicMock()
        data = {"event_from_user": None, "event": event}

        result = await mw(handler, event, data)
        assert result == "ok"

    async def test_login_key_inferred(self):
        """Messages containing ':' are classified as 'login'."""
        mw = ThrottlingMiddleware(limits={"login": (1, 60), "default": (10, 60)})
        handler = AsyncMock(return_value="ok")

        user = MagicMock(id=123)
        message = MagicMock(text="admin:password")
        data = {"event_from_user": user, "event": message}

        # First request passes.
        await mw(handler, message, data)
        # Second request is blocked (login limit = 1).
        result = await mw(handler, message, data)
        assert result is None