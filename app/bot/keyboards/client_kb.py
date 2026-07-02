"""Client-facing inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Tariff


def main_menu(has_trial: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile"))
    if has_trial:
        kb.row(InlineKeyboardButton(text="🎁 Пробный период (бесплатно)", callback_data="trial"))
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


def tariffs_menu_extend(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
    """Тарифы для продления — те же тарифы но с пометкой."""
    kb = InlineKeyboardBuilder()
    for t in tariffs:
        label = f"🔄 {t.name} — {int(t.price)}₽ / {t.days} дн."
        kb.row(InlineKeyboardButton(text=label, callback_data=f"tariff:{t.id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main"))
    return kb.as_markup()


def buy_or_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🌍 Купить VPN", callback_data="buy_vpn"))
    kb.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main"))
    return kb.as_markup()


def payment_method_select(tariff_id: int, has_yookassa: bool, has_phone: bool) -> InlineKeyboardMarkup:
    """Let client choose payment method."""
    kb = InlineKeyboardBuilder()
    if has_yookassa:
        kb.row(InlineKeyboardButton(text="💳 Картой онлайн", callback_data=f"pay_card:{tariff_id}"))
    if has_phone:
        kb.row(InlineKeyboardButton(text="📱 Перевод по СБП", callback_data=f"pay_sbp:{tariff_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_vpn"))
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


def sbp_transfer_kb(payment_id: int) -> InlineKeyboardMarkup:
    """Keyboard after showing phone number for SBP transfer."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"sbp_paid:{payment_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_main"))
    return kb.as_markup()


def bonuses_kb(bonus_days: int) -> InlineKeyboardMarkup:
    """Bonuses menu with optional activation button."""
    kb = InlineKeyboardBuilder()
    if bonus_days > 0:
        kb.row(InlineKeyboardButton(text=f"🎁 Активировать ({bonus_days} дн.)", callback_data="activate_bonus"))
    kb.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main"))
    return kb.as_markup()


def main_menu_with_channel(has_trial: bool = False, channel_url: str = "") -> InlineKeyboardMarkup:
    """Main menu with optional channel button."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile"))
    if has_trial:
        kb.row(InlineKeyboardButton(text="🎁 Пробный период (бесплатно)", callback_data="trial"))
    kb.row(InlineKeyboardButton(text="🌍 Купить VPN", callback_data="buy_vpn"))
    kb.row(InlineKeyboardButton(text="🔑 Мой VPN", callback_data="my_vpn"))
    kb.row(InlineKeyboardButton(text="💳 Продлить", callback_data="extend_vpn"))
    kb.row(InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="referral"))
    kb.row(InlineKeyboardButton(text="⭐ Бонусы", callback_data="bonuses"))
    kb.row(InlineKeyboardButton(text="🏷 Ввести промокод", callback_data="enter_promo"))
    kb.row(InlineKeyboardButton(text="📝 Инструкция", callback_data="instruction"))
    if channel_url:
        kb.row(InlineKeyboardButton(text="📢 Наш канал", url=channel_url))
    kb.row(InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"))
    return kb.as_markup()


def back_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main"))
    return kb.as_markup()


def promo_result_kb(has_bonus: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_bonus:
        kb.row(InlineKeyboardButton(text="⭐ Мои бонусы", callback_data="bonuses"))
    kb.row(InlineKeyboardButton(text="🌍 Купить VPN", callback_data="buy_vpn"))
    kb.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main"))
    return kb.as_markup()
