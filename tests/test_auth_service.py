"""Tests for AuthService."""
import pytest
from unittest.mock import AsyncMock

from database.models import User
from services.auth_service import AuthService


class TestAuthService:
    """Tests for the AuthService class."""

    async def test_authenticate_success(self, mock_user_repo, sample_user):
        """Test successful authentication."""
        mock_user_repo.find_by_username.return_value = sample_user
        service = AuthService(mock_user_repo)
        
        result = await service.authenticate("testadmin", "password123")
        
        assert result is not None
        assert result.username == "testadmin"
        assert result.role == "admin"
        mock_user_repo.find_by_username.assert_called_once_with("testadmin")

    async def test_authenticate_user_not_found(self, mock_user_repo):
        """Test authentication with non-existent user."""
        mock_user_repo.find_by_username.return_value = None
        service = AuthService(mock_user_repo)
        
        result = await service.authenticate("nonexistent", "password")
        
        assert result is None

    async def test_authenticate_wrong_password(self, mock_user_repo, sample_user):
        """Test authentication with wrong password."""
        mock_user_repo.find_by_username.return_value = sample_user
        service = AuthService(mock_user_repo)
        
        result = await service.authenticate("testadmin", "wrongpassword")
        
        assert result is None

    async def test_add_waiter_success(self, mock_user_repo, sample_waiter_user):
        """Test adding a new waiter successfully."""
        mock_user_repo.find_by_username.return_value = None
        mock_user_repo.create.return_value = sample_waiter_user
        service = AuthService(mock_user_repo)
        
        result = await service.add_waiter("newwaiter", "password")
        
        assert result == sample_waiter_user
        mock_user_repo.create.assert_called_once_with("newwaiter", "password", "waiter")

    async def test_add_waiter_already_exists(self, mock_user_repo, sample_user):
        """Test adding a waiter when username already exists."""
        mock_user_repo.find_by_username.return_value = sample_user
        service = AuthService(mock_user_repo)
        
        with pytest.raises(ValueError, match="already exists"):
            await service.add_waiter("testadmin", "password")

    async def test_update_chat_id(self, mock_user_repo):
        """Test updating chat_id."""
        service = AuthService(mock_user_repo)
        
        await service.update_chat_id(1, 123456)
        
        mock_user_repo.update_chat_id.assert_called_once_with(1, 123456)

    async def test_ensure_admin_exists(self, mock_user_repo):
        """Test ensuring admin account exists."""
        service = AuthService(mock_user_repo)
        
        await service.ensure_admin_exists("admin", "password")
        
        mock_user_repo.ensure_admin_exists.assert_called_once_with("admin", "password")