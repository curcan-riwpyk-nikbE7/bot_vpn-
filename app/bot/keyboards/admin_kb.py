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
    kb.row(InlineKeyboardButton(text="📈 Аналитика", callback_data="adm_analytics"))
    kb.row(InlineKeyboardButton(text="💳 История платежей", callback_data="adm_payments"))
    kb.row(InlineKeyboardButton(text="🎁 Промокоды", callback_data="adm_promo"))
    kb.row(InlineKeyboardButton(text="🎁 Выдать ключ", callback_data="adm_gift"))
    kb.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_mailing"))
    kb.row(InlineKeyboardButton(text="🎨 Кастомизация", callback_data="adm_customize"))
    kb.row(InlineKeyboardButton(text="📝 Инструкция", callback_data="adm_instruction"))
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


def srv_step_kb(step: int) -> InlineKeyboardMarkup:
    """Back + Cancel for server add steps."""
    kb = InlineKeyboardBuilder()
    buttons = []
    if step > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"srv_back:{step}"))
    buttons.append(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    kb.row(*buttons)
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


def customize_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✏️ Название сервиса", callback_data="cust_name"))
    kb.row(InlineKeyboardButton(text="📝 Приветствие", callback_data="cust_greeting"))
    kb.row(InlineKeyboardButton(text="🖼 Логотип", callback_data="cust_logo"))
    kb.row(InlineKeyboardButton(text="🆘 Контакт поддержки", callback_data="cust_support"))
    kb.row(InlineKeyboardButton(text="📢 Ссылка на канал", callback_data="cust_channel"))
    kb.row(InlineKeyboardButton(text="💳 Оплата (способ)", callback_data="cust_payment"))
    kb.row(InlineKeyboardButton(text="📱 Номер для СБП", callback_data="cust_phone"))
    kb.row(InlineKeyboardButton(text="🎁 Пробный период", callback_data="cust_trial"))
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def payment_method_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💳 ЮKassa (карта)", callback_data="paymethod_card"))
    kb.row(InlineKeyboardButton(text="📱 Перевод по номеру (СБП)", callback_data="paymethod_transfer"))
    kb.row(InlineKeyboardButton(text="💳 + 📱 Оба", callback_data="paymethod_both"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_customize"))
    return kb.as_markup()


def trial_settings_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Включить", callback_data="trial_on"))
    kb.row(InlineKeyboardButton(text="❌ Выключить", callback_data="trial_off"))
    kb.row(InlineKeyboardButton(text="📅 Изменить дни", callback_data="trial_days"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_customize"))
    return kb.as_markup()


def sbp_confirm_kb(payment_id: int) -> InlineKeyboardMarkup:
    """Admin confirmation for SBP transfer."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"sbp_approve:{payment_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"sbp_reject:{payment_id}"),
    )
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


def analytics_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📅 За сегодня", callback_data="analytics_today"))
    kb.row(InlineKeyboardButton(text="📅 За 7 дней", callback_data="analytics_7d"))
    kb.row(InlineKeyboardButton(text="📅 За 30 дней", callback_data="analytics_30d"))
    kb.row(InlineKeyboardButton(text="📅 За всё время", callback_data="analytics_all"))
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def payments_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Успешные", callback_data="payments_paid"))
    kb.row(InlineKeyboardButton(text="⏳ Ожидают", callback_data="payments_pending"))
    kb.row(InlineKeyboardButton(text="❌ Отклонённые", callback_data="payments_failed"))
    kb.row(InlineKeyboardButton(text="📋 Все", callback_data="payments_all"))
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def promo_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_add"))
    kb.row(InlineKeyboardButton(text="📋 Список промокодов", callback_data="promo_list"))
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()


def instruction_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✏️ Изменить инструкцию", callback_data="instruction_edit"))
    kb.row(InlineKeyboardButton(text="👁 Просмотреть", callback_data="instruction_view"))
    kb.row(InlineKeyboardButton(text="⬅️ Админ", callback_data="adm_back"))
    return kb.as_markup()
