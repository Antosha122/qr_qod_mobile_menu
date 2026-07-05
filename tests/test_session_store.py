"""Tests for the staff session store (Redis-backed with in-memory fallback)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.session_store import SessionStore


class TestInMemorySessionStore:
    """SessionStore behaviour when Redis is unavailable (in-memory mode)."""

    @pytest.fixture
    def store(self):
        return SessionStore()

    async def test_set_and_get(self, store):
        await store.set(111, "admin")
        assert await store.get(111) == "admin"

    async def test_get_missing_returns_none(self, store):
        assert await store.get(999) is None

    async def test_clear_removes_session(self, store):
        await store.set(111, "admin")
        await store.clear(111)
        assert await store.get(111) is None

    async def test_clear_missing_is_noop(self, store):
        await store.clear(404)

    async def test_set_overwrites(self, store):
        await store.set(111, "admin")
        await store.set(111, "waiter")
        assert await store.get(111) == "waiter"

    async def test_revoke_all(self, store):
        await store.set(1, "a")
        await store.set(2, "b")
        count = await store.revoke_all()
        assert count >= 2
        assert await store.get(1) is None
        assert await store.get(2) is None


class TestRedisSessionStore:
    """SessionStore behaviour when Redis is available (mocked)."""

    @pytest.fixture
    def fake_redis(self):
        data = {}
        client = MagicMock()
        client.get = AsyncMock(side_effect=lambda k: data.get(k))
        client.set = AsyncMock(side_effect=lambda k, v, ex=None: data.__setitem__(k, v))
        client.delete = AsyncMock(side_effect=lambda k: data.pop(k, None))
        client.expire = AsyncMock()
        client.ping = AsyncMock(return_value=True)

        keys_iter = []

        def _scan_iter(match=None, count=None):
            class _Iter:
                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if keys_iter:
                        return keys_iter.pop(0)
                    raise StopAsyncIteration

            prefix = (match or "*").rstrip("*")
            keys_iter.clear()
            keys_iter.extend([k for k in list(data.keys()) if k.startswith(prefix)])
            return _Iter()

        client.scan_iter = _scan_iter
        return client, data

    async def test_redis_set_and_get(self, fake_redis):
        client, data = fake_redis
        store = SessionStore()
        with patch("services.session_store.get_redis", return_value=client), patch("database.redis_connection.get_redis", return_value=client):
            await store.set(111, "admin")
            assert data.get("tokio:session:111") == "admin"
            assert await store.get(111) == "admin"

    async def test_redis_get_refreshes_ttl(self, fake_redis):
        client, data = fake_redis
        store = SessionStore()
        with patch("services.session_store.get_redis", return_value=client), patch("database.redis_connection.get_redis", return_value=client):
            await store.set(111, "admin")
            await store.get(111)
            client.expire.assert_called_once()

    async def test_redis_clear_revokes(self, fake_redis):
        client, data = fake_redis
        store = SessionStore()
        with patch("services.session_store.get_redis", return_value=client), patch("database.redis_connection.get_redis", return_value=client):
            await store.set(111, "admin")
            await store.clear(111)
            assert "tokio:session:111" not in data
            assert await store.get(111) is None

    async def test_redis_get_missing_returns_none(self, fake_redis):
        client, data = fake_redis
        store = SessionStore()
        with patch("services.session_store.get_redis", return_value=client), patch("database.redis_connection.get_redis", return_value=client):
            assert await store.get(999) is None

    async def test_redis_get_failure_returns_none(self):
        client = MagicMock()
        client.get = AsyncMock(side_effect=Exception("connection lost"))
        store = SessionStore()
        with patch("services.session_store.get_redis", return_value=client), patch("database.redis_connection.get_redis", return_value=client):
            assert await store.get(111) is None