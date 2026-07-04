"""Tests for AuthService."""
import pytest
from database.models import User
from services.auth_service import AuthService
from utils.security import hash_password, is_hashed


class TestAuthService:
    async def test_authenticate_success(self, mock_user_repo, sample_user):
        user = User(
            id=sample_user.id,
            username=sample_user.username,
            password=hash_password("password123"),
            role=sample_user.role,
            chat_id=sample_user.chat_id,
            must_change_password=False,
        )
        mock_user_repo.find_by_username.return_value = user
        service = AuthService(mock_user_repo)
        result = await service.authenticate("testadmin", "password123")
        assert result is not None
        assert result.username == "testadmin"

    async def test_authenticate_user_not_found(self, mock_user_repo):
        mock_user_repo.find_by_username.return_value = None
        service = AuthService(mock_user_repo)
        result = await service.authenticate("nonexistent", "password")
        assert result is None

    async def test_authenticate_wrong_password(self, mock_user_repo, sample_user):
        mock_user_repo.find_by_username.return_value = sample_user
        service = AuthService(mock_user_repo)
        result = await service.authenticate("testadmin", "wrongpassword")
        assert result is None

    async def test_add_waiter_success(self, mock_user_repo, sample_waiter_user):
        mock_user_repo.find_by_username.return_value = None
        mock_user_repo.create.return_value = sample_waiter_user
        service = AuthService(mock_user_repo)
        await service.add_waiter("newwaiter", "password")
        args = mock_user_repo.create.call_args.args
        assert args[0] == "newwaiter"
        assert is_hashed(args[1])
        assert args[2] == "waiter"

    async def test_add_waiter_already_exists(self, mock_user_repo, sample_user):
        mock_user_repo.find_by_username.return_value = sample_user
        service = AuthService(mock_user_repo)
        with pytest.raises(ValueError, match="already exists"):
            await service.add_waiter("testadmin", "password")

    async def test_update_chat_id(self, mock_user_repo):
        service = AuthService(mock_user_repo)
        await service.update_chat_id(1, 123456)
        mock_user_repo.update_chat_id.assert_called_once_with(1, 123456)

    async def test_ensure_admin_exists(self, mock_user_repo):
        service = AuthService(mock_user_repo)
        await service.ensure_admin_exists("admin", "password")
        args = mock_user_repo.ensure_admin_exists.call_args.args
        assert args[0] == "admin"
        assert is_hashed(args[1])
