"""Admin inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Server, Tariff


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📡 Серверы", callback_data="adm_servers"))
    kb.row(InlineKeyboardButton(text="💰 Тарифы", callback_data="adm_tariffs"))
    kb.row(InlineKeyboardButton(text="👥 Клиенты", callback_data="adm_clients"))
    kb.row(InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"))
    kb.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_mailing"))
    kb.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm_settings"))
    return kb.as_markup()


def servers_menu(servers: list[Server]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ Добавить сервер", callback_data="adm_add_server"))
    for s in servers:
        status = "🟢" if s.is_active else "🔴"
        kb.row(
            InlineKeyboardButton(text=f"{status} {s.name}", callback_data=f"adm_srv:{s.id}")
        )
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def server_actions(server_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔍 Проверить", callback_data=f"adm_srv_check:{server_id}"))
    kb.row(InlineKeyboardButton(text="🔴 Выключить", callback_data=f"adm_srv_off:{server_id}"))
    kb.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_srv_del:{server_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Серверы", callback_data="adm_servers"))
    return kb.as_markup()


def tariffs_menu(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ Добавить тариф", callback_data="adm_add_tariff"))
    for t in tariffs:
        status = "🟢" if t.is_active else "🔴"
        kb.row(
            InlineKeyboardButton(
                text=f"{status} {t.name} ({int(t.price)}₽/{t.days}д)",
                callback_data=f"adm_tariff:{t.id}",
            )
        )
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def tariff_actions(tariff_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✏️ Изменить цену", callback_data=f"adm_t_price:{tariff_id}"))
    kb.row(InlineKeyboardButton(text="✏️ Изменить срок", callback_data=f"adm_t_days:{tariff_id}"))
    kb.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_t_del:{tariff_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Тарифы", callback_data="adm_tariffs"))
    return kb.as_markup()


def mailing_target() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📨 Все пользователи", callback_data="mail_all"))
    kb.row(InlineKeyboardButton(text="🟢 Активные", callback_data="mail_active"))
    kb.row(InlineKeyboardButton(text="⏰ Заканчивается подписка", callback_data="mail_expiring"))
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def confirm_kb(action: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm:{action}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="adm_back"),
    )
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return kb.as_markup()
