"""Client-facing inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Tariff


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🌍 Купить VPN", callback_data="buy_vpn"))
    kb.row(InlineKeyboardButton(text="🔑 Мой VPN", callback_data="my_vpn"))
    kb.row(InlineKeyboardButton(text="💳 Продлить", callback_data="extend_vpn"))
    kb.row(InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="referral"))
    kb.row(InlineKeyboardButton(text="⭐ Бонусы", callback_data="bonuses"))
    kb.row(InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"))
    return kb.as_markup()


def tariffs_menu(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in tariffs:
        label = f"{t.name} — {int(t.price)}₽"
        kb.row(InlineKeyboardButton(text=label, callback_data=f"tariff:{t.id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main"))
    return kb.as_markup()


def payment_kb(payment_url: str, payment_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 Оплатить", url=payment_url))
    kb.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_pay:{payment_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_main"))
    return kb.as_markup()


def check_payment_kb(payment_id: str) -> InlineKeyboardMarkup:
    """Keyboard for SBP QR payment (no redirect URL, just check button)."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_pay:{payment_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_main"))
    return kb.as_markup()


def back_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main"))
    return kb.as_markup()
