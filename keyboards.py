"""Inline keyboard builders for the VPN bot (user + admin panels)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Server, Tariff
from vpn_generator import PROTOCOLS


# --------------------------------------------------------------------- user
def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Купить VPN", callback_data="buy")
    kb.button(text="🔑 Мои ключи", callback_data="my_keys")
    kb.button(text="ℹ️ Помощь", callback_data="help")
    kb.adjust(1)
    return kb.as_markup()


def tariffs_menu(tariffs: list[Tariff], currency: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in tariffs:
        kb.button(
            text=f"{t.name} — {t.price} {currency} / {t.days} дн.",
            callback_data=f"buy_tariff:{t.id}",
        )
    kb.button(text="⬅️ Назад", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()


def confirm_purchase(tariff_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплатить", callback_data=f"pay:{tariff_id}")
    kb.button(text="⬅️ Назад", callback_data="buy")
    kb.adjust(1)
    return kb.as_markup()


def back_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Главное меню", callback_data="back_main")
    return kb.as_markup()


# -------------------------------------------------------------------- admin
def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="adm_stats")
    kb.button(text="🖥️ Серверы", callback_data="adm_servers")
    kb.button(text="💰 Тарифы", callback_data="adm_tariffs")
    kb.button(text="🔑 Создать ключ", callback_data="adm_createkey")
    kb.adjust(2)
    return kb.as_markup()


def admin_back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Админ-панель", callback_data="adm_back")
    return kb.as_markup()


def servers_menu(servers: list[Server]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить сервер", callback_data="adm_addserver")
    kb.button(text="➕ Добавить 3X-UI панель", callback_data="adm_addpanel")
    for s in servers:
        status = "🟢" if s.is_active else "🔴"
        badge = "🛡️ " if s.is_panel else ""
        kb.button(
            text=f"{status} {badge}{s.name} ({s.load_percent}%)",
            callback_data=f"adm_server:{s.id}",
        )
    kb.button(text="⬅️ Админ-панель", callback_data="adm_back")
    kb.adjust(1)
    return kb.as_markup()


def server_actions(server_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Изменить лимит", callback_data=f"adm_setlimit:{server_id}")
    kb.button(text="🗑️ Удалить сервер", callback_data=f"adm_delserver:{server_id}")
    kb.button(text="⬅️ Назад", callback_data="adm_servers")
    kb.adjust(1)
    return kb.as_markup()


def protocol_choice(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for proto in PROTOCOLS:
        kb.button(text=proto, callback_data=f"{prefix}:{proto}")
    kb.adjust(len(PROTOCOLS))
    return kb.as_markup()


def tariffs_admin_menu(tariffs: list[Tariff], currency: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить тариф", callback_data="adm_addtariff")
    for t in tariffs:
        status = "🟢" if t.is_active else "🔴"
        kb.button(
            text=f"{status} {t.name} — {t.price} {currency}",
            callback_data=f"adm_tariff:{t.id}",
        )
    kb.button(text="⬅️ Админ-панель", callback_data="adm_back")
    kb.adjust(1)
    return kb.as_markup()


def tariff_actions(tariff_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑️ Удалить тариф", callback_data=f"adm_deltariff:{tariff_id}")
    kb.button(text="⬅️ Назад", callback_data="adm_tariffs")
    kb.adjust(1)
    return kb.as_markup()


def pick_from_list(items: list, prefix: str, back: str) -> InlineKeyboardMarkup:
    """Generic picker used for selecting a server/tariff while creating a key."""
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.button(text=item.name, callback_data=f"{prefix}:{item.id}")
    kb.button(text="⬅️ Отмена", callback_data=back)
    kb.adjust(1)
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Отмена", callback_data="adm_back")
    return kb.as_markup()
