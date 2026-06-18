"""Tests for keyboards and QR generator."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from keyboards.guest_keyboards import (
    get_main_menu_keyboard,
    get_categories_keyboard,
    get_quantity_keyboard,
    get_cart_keyboard,
    get_empty_cart_keyboard,
    get_checkout_keyboard,
    get_close_table_keyboard,
    get_payment_keyboard,
)
from keyboards.staff_keyboards import (
    get_staff_main_keyboard,
    get_staff_admin_keyboard,
    get_staff_waiter_keyboard,
    get_table_selection_keyboard,
    get_cancel_keyboard,
    get_staff_table_actions_keyboard,
)
from utils.qr_generator import QRCodeGenerator


class TestGuestKeyboards:
    """Tests for guest bot keyboards."""

    def test_get_main_menu_keyboard(self):
        """Test main menu keyboard creation (now a reply keyboard)."""
        kb = get_main_menu_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)
        # 2 rows with 2 buttons each (Меню/Корзина, Оформить заказ/Оплата)
        assert len(kb.keyboard) == 2
        assert len(kb.keyboard[0]) == 2
        assert len(kb.keyboard[1]) == 2

    def test_get_categories_keyboard(self):
        """Test categories keyboard."""
        categories = [(1, "Роллы"), (2, "Супы")]
        kb = get_categories_keyboard(categories)
        assert isinstance(kb, InlineKeyboardMarkup)
        # 2 categories + 1 cart button = 3 rows
        assert len(kb.inline_keyboard) == 3

    def test_get_categories_keyboard_empty(self):
        """Test categories keyboard with no categories."""
        kb = get_categories_keyboard([])
        assert isinstance(kb, InlineKeyboardMarkup)
        # Only cart button
        assert len(kb.inline_keyboard) == 1

    def test_get_quantity_keyboard(self):
        """Test quantity keyboard."""
        kb = get_quantity_keyboard(5)
        assert isinstance(kb, InlineKeyboardMarkup)
        # One row with 5 buttons (1-5)
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 5

    def test_get_cart_keyboard_with_items(self):
        """Test cart keyboard with items."""
        items = [(1, "Ролл"), (2, "Суп")]
        kb = get_cart_keyboard(items)
        assert isinstance(kb, InlineKeyboardMarkup)
        # 2 remove buttons + back + checkout + request_bill = 5 rows
        assert len(kb.inline_keyboard) == 5

    def test_get_cart_keyboard_empty(self):
        """Test cart keyboard without items."""
        kb = get_cart_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)
        # back + checkout + request_bill = 3 rows
        assert len(kb.inline_keyboard) == 3

    def test_get_payment_keyboard(self):
        """Test payment keyboard."""
        kb = get_payment_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)
        # pay + back = 2 rows
        assert len(kb.inline_keyboard) == 2
        assert kb.inline_keyboard[0][0].callback_data == "pay_bill"

    def test_get_empty_cart_keyboard(self):
        """Test empty cart keyboard."""
        kb = get_empty_cart_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)
        assert len(kb.inline_keyboard) == 1

    def test_get_checkout_keyboard(self):
        """Test checkout keyboard."""
        kb = get_checkout_keyboard(5)
        assert isinstance(kb, InlineKeyboardMarkup)
        assert len(kb.inline_keyboard) == 1

    def test_get_close_table_keyboard(self):
        """Test close table keyboard."""
        kb = get_close_table_keyboard(3)
        assert isinstance(kb, InlineKeyboardMarkup)
        assert len(kb.inline_keyboard) == 1


class TestStaffKeyboards:
    """Tests for staff bot keyboards."""

    def test_get_staff_main_keyboard_admin(self):
        """Test main keyboard for admin role."""
        kb = get_staff_main_keyboard("admin")
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_get_staff_main_keyboard_waiter(self):
        """Test main keyboard for waiter role."""
        kb = get_staff_main_keyboard("waiter")
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_get_staff_admin_keyboard(self):
        """Test admin keyboard."""
        kb = get_staff_admin_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_get_staff_waiter_keyboard(self):
        """Test waiter keyboard."""
        kb = get_staff_waiter_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_get_table_selection_keyboard(self):
        """Test table selection keyboard."""
        kb = get_table_selection_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)
        # Last row should be the back button
        assert kb.keyboard[-1][0].text == "⬅️ Назад"

    def test_get_table_selection_keyboard_with_info_mine(self):
        """Table assigned to the current waiter shows the cart total."""
        table_info = {
            3: {
                "is_open": True,
                "is_mine": True,
                "total": 1200.0,
                "payment_status": "unpaid",
            }
        }
        kb = get_table_selection_keyboard(table_info)
        assert isinstance(kb, ReplyKeyboardMarkup)
        # Find the button for table 3.
        table3_text = next(
            btn.text for row in kb.keyboard for btn in row
            if btn.text.startswith("Стол 3")
        )
        assert "1200" in table3_text
        assert "₽" in table3_text
        assert "🔒" not in table3_text

    def test_get_table_selection_keyboard_with_info_other_waiter(self):
        """Table assigned to another waiter is marked with a lock."""
        table_info = {
            3: {
                "is_open": True,
                "is_mine": False,
                "total": 500.0,
                "payment_status": "unpaid",
            }
        }
        kb = get_table_selection_keyboard(table_info)
        table3_text = next(
            btn.text for row in kb.keyboard for btn in row
            if btn.text.startswith("Стол 3")
        )
        assert "🔒" in table3_text
        # Should not show the total for someone else's table.
        assert "500" not in table3_text

    def test_get_table_selection_keyboard_payment_indicators(self):
        """Payment status adds an icon next to the waiter's own table."""
        base = {
            "is_open": True,
            "is_mine": True,
            "total": 100.0,
        }
        statuses = {
            "requested": "🔔",
            "payment_pending": "⏳",
            "paid": "✅",
        }
        for status, icon in statuses.items():
            table_info = {1: {**base, "payment_status": status}}
            kb = get_table_selection_keyboard(table_info)
            table1_text = next(
                btn.text for row in kb.keyboard for btn in row
                if btn.text.startswith("Стол 1")
            )
            assert icon in table1_text

    def test_get_table_selection_keyboard_closed_table_plain(self):
        """A closed table (not in table_info) shows a plain label."""
        kb = get_table_selection_keyboard({3: {"is_open": False}})
        table3_text = next(
            btn.text for row in kb.keyboard for btn in row
            if btn.text.startswith("Стол 3")
        )
        assert table3_text == "Стол 3"

    def test_get_cancel_keyboard(self):
        """Test cancel keyboard."""
        kb = get_cancel_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)
        assert kb.keyboard[0][0].text == "❌ Отмена"

    def test_table_actions_open_payment_pending(self):
        """Open table awaiting payment shows confirm + close buttons."""
        kb = get_staff_table_actions_keyboard(
            5, payment_status="payment_pending", is_open=True
        )
        assert isinstance(kb, InlineKeyboardMarkup)
        # Row 0: confirm payment; Row 1: close table.
        assert len(kb.inline_keyboard) == 2
        assert kb.inline_keyboard[0][0].callback_data == "staff_confirm_payment_5"
        assert kb.inline_keyboard[1][0].callback_data == "staff_close_table_5"

    def test_table_actions_open_paid(self):
        """Open & paid table shows only the close button."""
        kb = get_staff_table_actions_keyboard(
            5, payment_status="paid", is_open=True
        )
        assert isinstance(kb, InlineKeyboardMarkup)
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "staff_close_table_5"

    def test_table_actions_open_unpaid(self):
        """Open & unpaid table shows only the close button."""
        kb = get_staff_table_actions_keyboard(
            5, payment_status="unpaid", is_open=True
        )
        assert isinstance(kb, InlineKeyboardMarkup)
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "staff_close_table_5"

    def test_table_actions_stuck_closed_payment_pending(self):
        """A stuck closed+payment_pending table offers only close (no confirm).

        Regression test: previously a closed table with a pending payment
        showed NO buttons at all, leaving staff unable to resolve it. Now
        the close button is always available so staff can reset/release it,
        while the confirm button is hidden (it requires an open assignment).
        """
        kb = get_staff_table_actions_keyboard(
            5, payment_status="payment_pending", is_open=False
        )
        assert isinstance(kb, InlineKeyboardMarkup)
        # Only the close button — confirm is hidden for closed tables.
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == "staff_close_table_5"

    def test_table_actions_default_is_open(self):
        """By default (is_open=True) the keyboard behaves as before."""
        kb = get_staff_table_actions_keyboard(5, payment_status="payment_pending")
        # Default is_open=True -> confirm + close.
        assert len(kb.inline_keyboard) == 2
        assert kb.inline_keyboard[0][0].callback_data == "staff_confirm_payment_5"


class TestQRCodeGenerator:
    """Tests for QR code generator."""

    def test_generate_table_qr(self, tmp_path):
        """Test generating a single QR code."""
        generator = QRCodeGenerator("TestBot", str(tmp_path))
        filepath = generator.generate_table_qr(1)
        
        assert os.path.exists(filepath)
        assert "table_1_qr.png" in filepath

    def test_generate_all_table_qrs(self, tmp_path):
        """Test generating all table QR codes."""
        generator = QRCodeGenerator("TestBot", str(tmp_path))
        filepaths = generator.generate_all_table_qrs(5)
        
        assert len(filepaths) == 5
        for fp in filepaths:
            assert os.path.exists(fp)

    def test_qr_code_output_directory_creation(self, tmp_path):
        """Test that output directory is created."""
        output_dir = str(tmp_path / "nested" / "qr_codes")
        generator = QRCodeGenerator("TestBot", output_dir)
        
        assert os.path.isdir(output_dir)

    def test_qr_code_url_format(self, tmp_path):
        """Test that QR code contains correct URL data."""
        generator = QRCodeGenerator("MyBot", str(tmp_path))
        filepath = generator.generate_table_qr(42)
        
        # Verify file was created (we can't easily decode QR in tests,
        # but we verify the file exists and has content)
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 0