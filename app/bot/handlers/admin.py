"""Admin handlers: servers, tariffs, clients, stats, mailing, customization."""

from __future__ import annotations

import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.filters.admin import IsAdmin
from app.bot.keyboards import admin_kb
from app.bot.states.states import (
    AddServer, AddTariff, Customize, Mailing,
    AddPromo, EditInstruction, GiftKey,
    EditTariffField, BlockUser, ExtendUserSub, NotifySettings,
)
from app.database.database import async_session
from app.database.models import Payment, PromoCode, Server, Setting, Subscription, Tariff, User
from app.services.mailing import broadcast, get_target_users
from app.services.xui import XUIError, XUIService

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ----------------------------------------------------------------- helpers
async def _get_setting(session, key: str, default: str = "") -> str:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def _set_setting(session, key: str, value: str) -> None:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()


def _srv_summary(data: dict, step: int) -> str:
    """Build server add progress text with checkmarks."""
    lines = [f"📡 <b>Добавление сервера ({step}/4)</b>\n"]
    if data.get("name"):
        lines.append(f"✅ Название: {html.escape(data['name'])}")
    if data.get("url"):
        lines.append(f"✅ URL панели: {html.escape(data['url'])}")
    if data.get("login"):
        lines.append(f"✅ Логин: {html.escape(data['login'])}")
    return "\n".join(lines)


# ----------------------------------------------------------------- /admin
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_kb.admin_menu())


@router.callback_query(F.data == "adm_back")
async def cb_adm_back(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]
    await call.answer()


# ================================================================= SERVERS
@router.callback_query(F.data == "adm_servers")
async def cb_servers(call: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Server))
        servers = list(result.scalars().all())
    await call.message.edit_text("📡 <b>Серверы</b>", reply_markup=admin_kb.servers_menu(servers))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("adm_srv:"))
async def cb_server_detail(call: CallbackQuery) -> None:
    srv_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        server = await session.get(Server, srv_id)
        if not server:
            await call.answer("Сервер не найден.", show_alert=True)
            return
        sub_count = await session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.server_id == server.id, Subscription.is_active.is_(True)
            )
        )
        clients = sub_count.scalar() or 0

    status = "🟢 Онлайн" if server.is_active else "🔴 Выключен"
    text = (
        f"📡 <b>{html.escape(server.name)}</b>\n\n"
        f"Статус: {status}\n"
        f"Клиентов: {clients}\n"
        f"URL: <code>{html.escape(server.url)}</code>\n"
        f"Inbound: {server.inbound_id}\n"
        f"Домен: {html.escape(server.domain)}"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.server_actions(server.id))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("adm_srv_check:"))
async def cb_server_check(call: CallbackQuery) -> None:
    srv_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        server = await session.get(Server, srv_id)
        if not server:
            await call.answer("Не найден.", show_alert=True)
            return
    xui = XUIService(
        base_url=server.url, username=server.login,
        password=server.password, inbound_id=server.inbound_id, domain=server.domain,
    )
    try:
        await xui.check()
        await call.answer("✅ Сервер доступен!", show_alert=True)
    except XUIError as exc:
        await call.answer(f"❌ {exc}", show_alert=True)


@router.callback_query(F.data.startswith("adm_srv_off:"))
async def cb_server_off(call: CallbackQuery) -> None:
    srv_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        server = await session.get(Server, srv_id)
        if server:
            server.is_active = not server.is_active
            await session.commit()
            status = "включён" if server.is_active else "выключен"
            await call.answer(f"Сервер {status}.", show_alert=True)
        else:
            await call.answer("Не найден.", show_alert=True)


@router.callback_query(F.data.startswith("adm_srv_del:"))
async def cb_server_del(call: CallbackQuery) -> None:
    srv_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        server = await session.get(Server, srv_id)
        if server:
            await session.delete(server)
            await session.commit()
            await call.answer("🗑 Сервер удалён.", show_alert=True)
        else:
            await call.answer("Не найден.", show_alert=True)
    async with async_session() as session:
        result = await session.execute(select(Server))
        servers = list(result.scalars().all())
    await call.message.edit_text("📡 <b>Серверы</b>", reply_markup=admin_kb.servers_menu(servers))  # type: ignore[union-attr]


# ---- Add server FSM (step-by-step with back)
@router.callback_query(F.data == "adm_add_server")
async def cb_add_server(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddServer.name)
    await state.update_data(name="", url="", login="", password="")
    text = (
        "📡 <b>Добавление сервера (1/4)</b>\n\n"
        "Введите <b>название</b>:\n"
        "<i>(например: Server-DE, Германия-1)</i>"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.srv_step_kb(1))  # type: ignore[union-attr]
    await call.answer()


@router.message(AddServer.name)
async def st_srv_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())  # type: ignore[union-attr]
    await state.set_state(AddServer.url)
    data = await state.get_data()
    text = (
        f"{_srv_summary(data, 2)}\n\n"
        "Введите <b>url панели</b>:\n"
        "<i>(например: https://192.168.1.1:2053/secretpath/ или просто 192.168.1.1:2053)</i>"
    )
    await message.answer(text, reply_markup=admin_kb.srv_step_kb(2))


@router.message(AddServer.url)
async def st_srv_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip()  # type: ignore[union-attr]
    if not url.startswith("http"):
        url = f"https://{url}"
    # Strip /panel, /panel/, /panel/settings etc. — user often copies full browser URL
    url = re.sub(r"/panel(/.*)?$", "", url)
    url = url.rstrip("/")
    await state.update_data(url=url)
    await state.set_state(AddServer.login)
    data = await state.get_data()
    text = (
        f"{_srv_summary(data, 3)}\n\n"
        "Введите <b>логин</b>:\n"
        "<i>(логин для входа в панель)</i>"
    )
    await message.answer(text, reply_markup=admin_kb.srv_step_kb(3))


@router.message(AddServer.login)
async def st_srv_login(message: Message, state: FSMContext) -> None:
    await state.update_data(login=message.text.strip())  # type: ignore[union-attr]
    await state.set_state(AddServer.password)
    data = await state.get_data()
    text = (
        f"{_srv_summary(data, 4)}\n\n"
        "Введите <b>пароль</b>:\n"
        "<i>(пароль для входа в панель)</i>"
    )
    await message.answer(text, reply_markup=admin_kb.srv_step_kb(4))


@router.message(AddServer.password)
async def st_srv_password(message: Message, state: FSMContext) -> None:
    password = message.text  # type: ignore[union-attr]
    data = await state.get_data()
    await state.clear()

    await message.answer("🔌 <b>Проверка подключения...</b>")

    from urllib.parse import urlsplit
    url = data["url"]
    domain = urlsplit(url).hostname or ""

    xui = XUIService(
        base_url=url, username=data["login"],
        password=password, inbound_id=1, domain=domain,
    )
    try:
        inbound_info = await xui.check()
        inbound_id = inbound_info.get("id", 1)
    except XUIError as exc:
        err = str(exc)
        hints = [
            "Бот пробовал подключиться по http и https.",
            "",
            "Возможные причины:",
            "• Неправильный логин или пароль",
            "• Секретный путь (URI Path) указан неверно",
            "• Панель недоступна извне (файрвол)",
            "",
            "Что попробовать:",
            "• Скопируйте URL прямо из адресной строки браузера",
            "  (всё до /panel/, например: https://ip:port/path)",
            "• Убедитесь что логин/пароль верные (те же что в браузере)",
        ]
        hint_text = "\n".join(hints)
        await message.answer(
            f"❌ <b>Не удалось подключиться</b>\n\n"
            f"Ошибка: <code>{html.escape(err)}</code>\n\n"
            f"{hint_text}",
            reply_markup=admin_kb.admin_menu(),
        )
        return

    async with async_session() as session:
        server = Server(
            name=data["name"],
            url=url,
            login=data["login"],
            password=password,
            inbound_id=inbound_id,
            domain=domain,
            protocol="vless-reality",
        )
        session.add(server)
        await session.commit()

    await message.answer(
        f"✅ <b>Сервер добавлен!</b>\n\n"
        f"Название: {html.escape(data['name'])}\n"
        f"URL: {html.escape(url)}\n"
        f"Inbound ID: {inbound_id}\n"
        f"🔌 Подключение успешно!",
        reply_markup=admin_kb.admin_menu(),
    )


# Back buttons in server add flow
@router.callback_query(F.data.startswith("srv_back:"))
async def cb_srv_back(call: CallbackQuery, state: FSMContext) -> None:
    step = int(call.data.split(":")[1])  # type: ignore[union-attr]
    data = await state.get_data()
    if step == 2:
        await state.set_state(AddServer.name)
        text = (
            "📡 <b>Добавление сервера (1/4)</b>\n\n"
            "Введите <b>название</b>:\n"
            "<i>(например: Server-DE, Германия-1)</i>"
        )
        await call.message.edit_text(text, reply_markup=admin_kb.srv_step_kb(1))  # type: ignore[union-attr]
    elif step == 3:
        await state.set_state(AddServer.url)
        text = (
            f"{_srv_summary(data, 2)}\n\n"
            "Введите <b>url панели</b>:\n"
            "<i>(например: https://192.168.1.1:2053/secretpath/)</i>"
        )
        await call.message.edit_text(text, reply_markup=admin_kb.srv_step_kb(2))  # type: ignore[union-attr]
    elif step == 4:
        await state.set_state(AddServer.login)
        text = (
            f"{_srv_summary(data, 3)}\n\n"
            "Введите <b>логин</b>:\n"
            "<i>(логин для входа в панель)</i>"
        )
        await call.message.edit_text(text, reply_markup=admin_kb.srv_step_kb(3))  # type: ignore[union-attr]
    await call.answer()


# ================================================================= TARIFFS
@router.callback_query(F.data == "adm_tariffs")
async def cb_tariffs(call: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Tariff).order_by(Tariff.sort_order))
        tariffs = list(result.scalars().all())
    await call.message.edit_text("💰 <b>Тарифы</b>", reply_markup=admin_kb.tariffs_menu(tariffs))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("adm_tariff:"))
async def cb_tariff_detail(call: CallbackQuery) -> None:
    t_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        tariff = await session.get(Tariff, t_id)
        if not tariff:
            await call.answer("Не найден.", show_alert=True)
            return
    text = (
        f"💰 <b>{html.escape(tariff.name)}</b>\n\n"
        f"Цена: {int(tariff.price)}₽\n"
        f"Дней: {tariff.days}\n"
        f"Устройств: {tariff.devices}"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.tariff_actions(tariff.id))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("adm_t_del:"))
async def cb_tariff_del(call: CallbackQuery) -> None:
    t_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        tariff = await session.get(Tariff, t_id)
        if tariff:
            tariff.is_active = False
            await session.commit()
    await call.answer("Тариф деактивирован.", show_alert=True)
    async with async_session() as session:
        result = await session.execute(select(Tariff).order_by(Tariff.sort_order))
        tariffs = list(result.scalars().all())
    await call.message.edit_text("💰 <b>Тарифы</b>", reply_markup=admin_kb.tariffs_menu(tariffs))  # type: ignore[union-attr]


# ---- Add tariff FSM
@router.callback_query(F.data == "adm_add_tariff")
async def cb_add_tariff(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddTariff.name)
    await call.message.edit_text("Название тарифа:", reply_markup=admin_kb.cancel_kb())  # type: ignore[union-attr]
    await call.answer()


@router.message(AddTariff.name)
async def st_tariff_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())  # type: ignore[union-attr]
    await state.set_state(AddTariff.days)
    await message.answer("Количество дней:")


@router.message(AddTariff.days)
async def st_tariff_days(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    if not text.isdigit():
        await message.answer("Введите число.")
        return
    await state.update_data(days=int(text))
    await state.set_state(AddTariff.price)
    await message.answer("Цена (₽):")


@router.message(AddTariff.price)
async def st_tariff_price(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    try:
        price = float(text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(price=price)
    await state.set_state(AddTariff.devices)
    await message.answer("Лимит устройств (число):")


@router.message(AddTariff.devices)
async def st_tariff_devices(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    if not text.isdigit():
        await message.answer("Введите число.")
        return
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        tariff = Tariff(
            name=data["name"],
            days=data["days"],
            price=data["price"],
            devices=int(text),
        )
        session.add(tariff)
        await session.commit()

    await message.answer(
        f"✅ Тариф <b>{html.escape(data['name'])}</b> добавлен.",
        reply_markup=admin_kb.admin_menu(),
    )


# ================================================================= CLIENTS
@router.callback_query(F.data == "adm_clients")
async def cb_clients(call: CallbackQuery) -> None:
    text = "👥 <b>Клиенты</b>\n\nОтправьте Telegram ID для поиска."
    await call.message.edit_text(text, reply_markup=admin_kb.cancel_kb())  # type: ignore[union-attr]
    await call.answer()


# ================================================================= STATS (see full version at bottom of file)


# ================================================================= MAILING
@router.callback_query(F.data == "adm_mailing")
async def cb_mailing(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_text("📢 <b>Рассылка</b>\n\nВыберите аудиторию:", reply_markup=admin_kb.mailing_target())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("mail_"))
async def cb_mail_target(call: CallbackQuery, state: FSMContext) -> None:
    target = call.data.replace("mail_", "")  # type: ignore[union-attr]
    await state.set_state(Mailing.text)
    await state.update_data(target=target)
    await call.message.edit_text("Введите текст рассылки:", reply_markup=admin_kb.cancel_kb())  # type: ignore[union-attr]
    await call.answer()


@router.message(Mailing.text)
async def st_mailing_text(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text or ""  # type: ignore[union-attr]
    data = await state.get_data()
    await state.clear()

    target = data.get("target", "all")
    async with async_session() as session:
        user_ids = await get_target_users(session, target)  # type: ignore[arg-type]

    sent, failed = await broadcast(bot, user_ids, text)
    await message.answer(
        f"📢 Рассылка завершена.\n\nОтправлено: {sent}\nОшибок: {failed}",
        reply_markup=admin_kb.admin_menu(),
    )


# ================================================================= CUSTOMIZATION
@router.callback_query(F.data == "adm_customize")
async def cb_customize(call: CallbackQuery) -> None:
    async with async_session() as session:
        name = await _get_setting(session, "service_name", "VPN SERVICE")
        support = await _get_setting(session, "support_username", "@support")
        pay_method = await _get_setting(session, "payment_method", "both")
        has_logo = await _get_setting(session, "logo_file_id", "")
        channel = await _get_setting(session, "channel_url", "")

    text = (
        f"🎨 <b>Кастомизация бота</b>\n\n"
        f"Название: <b>{html.escape(name)}</b>\n"
        f"Поддержка: {html.escape(support)}\n"
        f"Канал: {html.escape(channel) if channel else '❌ не указан'}\n"
        f"Оплата: {pay_method}\n"
        f"Логотип: {'✅ загружен' if has_logo else '❌ нет'}"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.customize_menu())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "cust_name")
async def cb_cust_name(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.name)
    await call.message.edit_text(  # type: ignore[union-attr]
        "✏️ Введите <b>новое название</b> вашего VPN-сервиса:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.name)
async def st_cust_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "service_name", name)
    await message.answer(
        f"✅ Название изменено: <b>{html.escape(name)}</b>",
        reply_markup=admin_kb.admin_menu(),
    )


@router.callback_query(F.data == "cust_greeting")
async def cb_cust_greeting(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.greeting)
    await call.message.edit_text(  # type: ignore[union-attr]
        "📝 Введите <b>текст приветствия</b>, который увидят клиенты при /start:\n"
        "<i>(поддерживается HTML-разметка: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;)</i>",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.greeting)
async def st_cust_greeting(message: Message, state: FSMContext) -> None:
    text = message.text or ""  # type: ignore[union-attr]
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "greeting", text)
    await message.answer("✅ Приветствие обновлено.", reply_markup=admin_kb.admin_menu())


@router.callback_query(F.data == "cust_logo")
async def cb_cust_logo(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.logo)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🖼 Отправьте <b>изображение</b> (логотип), которое будет отображаться "
        "при /start:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.logo)
async def st_cust_logo(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
    else:
        await message.answer("❌ Отправьте изображение.", reply_markup=admin_kb.admin_menu())
        return

    async with async_session() as session:
        await _set_setting(session, "logo_file_id", file_id)
    await message.answer("✅ Логотип обновлён!", reply_markup=admin_kb.admin_menu())


@router.callback_query(F.data == "cust_support")
async def cb_cust_support(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.support)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🆘 Введите <b>контакт поддержки</b> (username или ссылку):",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.support)
async def st_cust_support(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "support_username", text)
    await message.answer(
        f"✅ Контакт поддержки: {html.escape(text)}", reply_markup=admin_kb.admin_menu()
    )


@router.callback_query(F.data == "cust_channel")
async def cb_cust_channel(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.channel_url)
    await call.message.edit_text(  # type: ignore[union-attr]
        "📢 Введите <b>ссылку на ваш канал</b> (например https://t.me/your_channel):",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.channel_url)
async def st_cust_channel(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "channel_url", text)
    await message.answer(
        f"✅ Ссылка на канал: {html.escape(text)}", reply_markup=admin_kb.admin_menu()
    )


@router.callback_query(F.data == "cust_payment")
async def cb_cust_payment(call: CallbackQuery) -> None:
    await call.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Способ оплаты</b>\n\nВыберите, как клиенты будут оплачивать:",
        reply_markup=admin_kb.payment_method_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("paymethod_"))
async def cb_paymethod(call: CallbackQuery) -> None:
    method = call.data.replace("paymethod_", "")  # type: ignore[union-attr]
    async with async_session() as session:
        await _set_setting(session, "payment_method", method)
    labels = {"card": "💳 Карта", "transfer": "📱 Перевод СБП", "both": "💳 + 📱 Оба"}
    await call.answer(f"✅ Способ оплаты: {labels.get(method, method)}", show_alert=True)
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]


# ---- Phone number for SBP
@router.callback_query(F.data == "cust_phone")
async def cb_cust_phone(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.phone)
    await call.message.edit_text(  # type: ignore[union-attr]
        "📱 Введите <b>номер телефона</b> для приёма переводов по СБП:\n"
        "<i>(например: +79991234567)</i>\n\n"
        "Можно также указать название банка.",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.phone)
async def st_cust_phone(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "sbp_phone", text)
    await message.answer(
        f"✅ Номер для СБП: <b>{html.escape(text)}</b>", reply_markup=admin_kb.admin_menu()
    )


# ---- Trial period settings
@router.callback_query(F.data == "cust_trial")
async def cb_cust_trial(call: CallbackQuery) -> None:
    async with async_session() as session:
        enabled = await _get_setting(session, "trial_enabled", "true")
        days = await _get_setting(session, "trial_days", "3")
    status = "✅ Включён" if enabled == "true" else "❌ Выключен"
    text = (
        f"🎁 <b>Пробный период</b>\n\n"
        f"Статус: {status}\n"
        f"Длительность: {days} дней\n\n"
        f"Каждый новый пользователь может получить бесплатный VPN один раз."
    )
    await call.message.edit_text(text, reply_markup=admin_kb.trial_settings_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "trial_on")
async def cb_trial_on(call: CallbackQuery) -> None:
    async with async_session() as session:
        await _set_setting(session, "trial_enabled", "true")
    await call.answer("✅ Пробный период включён!", show_alert=True)
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]


@router.callback_query(F.data == "trial_off")
async def cb_trial_off(call: CallbackQuery) -> None:
    async with async_session() as session:
        await _set_setting(session, "trial_enabled", "false")
    await call.answer("❌ Пробный период выключен.", show_alert=True)
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]


@router.callback_query(F.data == "trial_days")
async def cb_trial_days(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Customize.trial_days)
    await call.message.edit_text(  # type: ignore[union-attr]
        "📅 Введите <b>количество дней</b> пробного периода:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(Customize.trial_days)
async def st_trial_days(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    if not text.isdigit() or int(text) < 1:
        await message.answer("Введите число дней (минимум 1).")
        return
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "trial_days", text)
    await message.answer(
        f"✅ Пробный период: <b>{text} дней</b>", reply_markup=admin_kb.admin_menu()
    )


# ---- Admin SBP payment confirmations
@router.callback_query(F.data.startswith("sbp_approve:"))
async def cb_sbp_approve(call: CallbackQuery, bot: Bot) -> None:
    pmt_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        pmt = await session.get(Payment, pmt_id)
        if not pmt or pmt.status == "paid":
            await call.answer("Уже обработан.", show_alert=True)
            return
        pmt.status = "paid"

        user = await session.get(User, pmt.user_id)
        tariff = await session.get(Tariff, pmt.tariff_id) if pmt.tariff_id else None
        if not user or not tariff:
            await call.answer("Данные не найдены.", show_alert=True)
            return

        from app.services.vpn_generator import generate_qr, generate_vpn_key, select_best_server
        from app.services.vpn_generator import VPNGeneratorError

        server = await select_best_server(session)
        if not server:
            await call.answer("Нет доступных серверов!", show_alert=True)
            return

        try:
            sub = await generate_vpn_key(session, user, tariff, server)
        except (VPNGeneratorError, Exception) as exc:
            logger.error("VPN key generation failed for payment %s: %s", pmt_id, exc)
            err_text = f"Ошибка: {exc}"[:180]
            await call.answer(err_text, show_alert=True)
            return

        await session.commit()

        # Notify client with key + instructions
        from aiogram.types import BufferedInputFile

        instructions = (
            "📲 <b>Инструкция по подключению:</b>\n\n"
            "1️⃣ Скачайте приложение:\n"
            "• iPhone/iPad: <b>Streisand</b> или <b>V2Box</b> (App Store)\n"
            "• Android: <b>V2rayNG</b> (Google Play)\n"
            "• Windows: <b>Nekoray</b> или <b>Hiddify</b>\n"
            "• macOS: <b>V2Box</b> или <b>Streisand</b>\n\n"
            "2️⃣ Скопируйте ключ ниже и вставьте в приложение\n"
            "   (или отсканируйте QR-код)\n\n"
            "3️⃣ Подключитесь и пользуйтесь! 🚀"
        )
        key_text = (
            f"✅ <b>VPN активирован!</b>\n\n"
            f"Тариф: {html.escape(tariff.name)} ({tariff.days} дн.)\n"
            f"Устройств: {tariff.devices}\n"
            f"Истекает: {sub.expire_date.strftime('%d.%m.%Y')}\n\n"
            f"{instructions}\n\n"
            f"🔑 <b>Ваш ключ:</b>\n<code>{html.escape(sub.vless_link)}</code>"
        )
        try:
            await bot.send_message(user.telegram_id, key_text)
            qr_buf = generate_qr(sub.vless_link)
            await bot.send_photo(
                user.telegram_id,
                BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
                caption="📱 QR-код — отсканируйте в приложении для подключения",
            )
        except Exception as exc:
            logger.error("Failed to send key to user %s: %s", user.telegram_id, exc)
            await call.answer("Ключ создан, но не удалось отправить клиенту.", show_alert=True)
            return

    await call.answer("✅ Оплата подтверждена, ключ выдан!", show_alert=True)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ Оплата #{pmt_id} подтверждена.\nКлюч выдан пользователю.",
    )


@router.callback_query(F.data.startswith("sbp_reject:"))
async def cb_sbp_reject(call: CallbackQuery, bot: Bot) -> None:
    pmt_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        pmt = await session.get(Payment, pmt_id)
        if not pmt:
            await call.answer("Не найден.", show_alert=True)
            return
        pmt.status = "canceled"
        user = await session.get(User, pmt.user_id)
        await session.commit()
        if user:
            try:
                await bot.send_message(
                    user.telegram_id,
                    "❌ Ваша оплата не подтверждена. Обратитесь в поддержку.",
                )
            except Exception:
                pass
    await call.answer("❌ Оплата отклонена.", show_alert=True)
    await call.message.edit_text(f"❌ Оплата #{pmt_id} отклонена.")  # type: ignore[union-attr]


# ================================================================= SETTINGS
@router.callback_query(F.data == "adm_settings")
async def cb_settings(call: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(Setting))
        all_settings = list(result.scalars().all())

    lines = ["⚙️ <b>Настройки</b>\n"]
    for s in all_settings:
        lines.append(f"• <code>{html.escape(s.key)}</code> = {html.escape(s.value[:50])}")
    if not all_settings:
        lines.append("Пусто. Настройки создаются через бота.")
    lines.append("\nОтправьте: <code>ключ=значение</code> для изменения.")

    await call.message.edit_text("\n".join(lines), reply_markup=admin_kb.cancel_kb())  # type: ignore[union-attr]
    await call.answer()


# ================================================================= ANALYTICS
@router.callback_query(F.data == "adm_analytics")
async def cb_analytics(call: CallbackQuery) -> None:
    await call.message.edit_text(  # type: ignore[union-attr]
        "📈 <b>Аналитика</b>\n\nВыберите период:",
        reply_markup=admin_kb.analytics_menu(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("analytics_"))
async def cb_analytics_period(call: CallbackQuery) -> None:
    from datetime import datetime, timedelta
    from sqlalchemy import and_

    period = call.data.split("_")[1]  # type: ignore[union-attr]
    now = datetime.utcnow()

    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "сегодня"
    elif period == "7d":
        since = now - timedelta(days=7)
        label = "за 7 дней"
    elif period == "30d":
        since = now - timedelta(days=30)
        label = "за 30 дней"
    else:
        since = datetime(2000, 1, 1)
        label = "за всё время"

    async with async_session() as session:
        # Новые пользователи
        new_users = await session.execute(
            select(func.count()).select_from(User).where(User.created_at >= since)
        )
        new_users_count = new_users.scalar() or 0

        # Новые подписки
        new_subs = await session.execute(
            select(func.count()).select_from(Subscription).where(Subscription.created_at >= since)
        )
        new_subs_count = new_subs.scalar() or 0

        # Доход
        income = await session.execute(
            select(func.sum(Payment.amount)).where(
                and_(Payment.status == "paid", Payment.created_at >= since)
            )
        )
        income_val = income.scalar() or 0

        # Всего платежей
        total_pmts = await session.execute(
            select(func.count()).select_from(Payment).where(Payment.created_at >= since)
        )
        total_pmts_count = total_pmts.scalar() or 0

        # Успешных платежей
        paid_pmts = await session.execute(
            select(func.count()).select_from(Payment).where(
                and_(Payment.status == "paid", Payment.created_at >= since)
            )
        )
        paid_pmts_count = paid_pmts.scalar() or 0

        # Активные подписки сейчас
        active_subs = await session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.is_active.is_(True)
            )
        )
        active_subs_count = active_subs.scalar() or 0

        # Всего пользователей
        total_users = await session.execute(select(func.count()).select_from(User))
        total_users_count = total_users.scalar() or 0

    conversion = round(paid_pmts_count / total_pmts_count * 100, 1) if total_pmts_count > 0 else 0

    text = (
        f"📈 <b>Аналитика {label}</b>\n\n"
        f"👥 Новых пользователей: <b>{new_users_count}</b>\n"
        f"🔑 Новых подписок: <b>{new_subs_count}</b>\n"
        f"💰 Доход: <b>{int(income_val)}₽</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 Платежей всего: <b>{total_pmts_count}</b>\n"
        f"✅ Успешных: <b>{paid_pmts_count}</b>\n"
        f"📊 Конверсия: <b>{conversion}%</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Всего пользователей: <b>{total_users_count}</b>\n"
        f"🟢 Активных подписок: <b>{active_subs_count}</b>\n"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.analytics_menu())  # type: ignore[union-attr]
    await call.answer()


# ================================================================= PAYMENTS HISTORY
@router.callback_query(F.data == "adm_payments")
async def cb_payments(call: CallbackQuery) -> None:
    await call.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>История платежей</b>\n\nВыберите фильтр:",
        reply_markup=admin_kb.payments_menu(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("payments_"))
async def cb_payments_filter(call: CallbackQuery) -> None:
    from sqlalchemy import desc

    status_filter = call.data.split("_")[1]  # type: ignore[union-attr]
    status_map = {
        "paid": "paid",
        "pending": "pending",
        "failed": "canceled",
        "all": None,
    }
    status = status_map.get(status_filter)

    async with async_session() as session:
        query = select(Payment).order_by(desc(Payment.created_at)).limit(20)
        if status:
            query = query.where(Payment.status == status)
        result = await session.execute(query)
        payments = list(result.scalars().all())

        lines = ["💳 <b>История платежей</b> (последние 20)\n"]
        if not payments:
            lines.append("Платежей не найдено.")
        for p in payments:
            user = await session.get(User, p.user_id)
            username = f"@{user.username}" if user and user.username else f"ID:{p.user_id}"
            status_emoji = {"paid": "✅", "pending": "⏳", "canceled": "❌"}.get(p.status, "❓")
            date_str = p.created_at.strftime("%d.%m %H:%M") if p.created_at else "—"
            lines.append(
                f"{status_emoji} {date_str} | {html.escape(username)} | "
                f"<b>{int(p.amount)}₽</b> | {p.provider}"
            )

    await call.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines), reply_markup=admin_kb.payments_menu()
    )
    await call.answer()


# ================================================================= PROMO CODES
@router.callback_query(F.data == "adm_promo")
async def cb_promo(call: CallbackQuery) -> None:
    await call.message.edit_text(  # type: ignore[union-attr]
        "🎁 <b>Промокоды</b>", reply_markup=admin_kb.promo_menu()
    )
    await call.answer()


@router.callback_query(F.data == "promo_list")
async def cb_promo_list(call: CallbackQuery) -> None:
    from app.database.models import PromoCode
    async with async_session() as session:
        result = await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
        promos = list(result.scalars().all())

    if not promos:
        text = "🎁 <b>Промокоды</b>\n\nПромокодов ещё нет."
    else:
        lines = ["🎁 <b>Промокоды</b>\n"]
        for p in promos:
            status = "🟢" if p.is_active else "🔴"
            discount_str = f"{p.discount_percent}% скидка" if p.discount_percent else ""
            days_str = f"+{p.bonus_days} дней" if p.bonus_days else ""
            reward = " | ".join(filter(None, [discount_str, days_str]))
            lines.append(
                f"{status} <code>{html.escape(p.code)}</code> — {reward} "
                f"({p.used_count}/{p.max_uses} использований)"
            )
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=admin_kb.promo_menu())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "promo_add")
async def cb_promo_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPromo.code)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🎁 <b>Создание промокода</b>\n\nШаг 1/3: Введите код (например: SALE20):",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(AddPromo.code)
async def promo_step_code(message: Message, state: FSMContext) -> None:
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(AddPromo.discount)
    await message.answer(
        "Шаг 2/3: Скидка в процентах (0 если нет скидки):",
        reply_markup=admin_kb.cancel_kb(),
    )


@router.message(AddPromo.discount)
async def promo_step_discount(message: Message, state: FSMContext) -> None:
    try:
        discount = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число от 0 до 100:")
        return
    await state.update_data(discount=discount)
    await state.set_state(AddPromo.days)
    await message.answer(
        "Шаг 3/4: Бонусных дней (0 если не нужно):",
        reply_markup=admin_kb.cancel_kb(),
    )


@router.message(AddPromo.days)
async def promo_step_days(message: Message, state: FSMContext) -> None:
    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    await state.update_data(days=days)
    await state.set_state(AddPromo.uses)
    await message.answer(
        "Шаг 4/4: Максимум использований (например: 100):",
        reply_markup=admin_kb.cancel_kb(),
    )


@router.message(AddPromo.uses)
async def promo_step_uses(message: Message, state: FSMContext) -> None:
    from app.database.models import PromoCode
    try:
        uses = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        promo = PromoCode(
            code=data["code"],
            discount_percent=data["discount"],
            bonus_days=data["days"],
            max_uses=uses,
        )
        session.add(promo)
        await session.commit()

    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"Код: <code>{html.escape(data['code'])}</code>\n"
        f"Скидка: {data['discount']}%\n"
        f"Бонус дней: {data['days']}\n"
        f"Макс. использований: {uses}",
        reply_markup=admin_kb.promo_menu(),
    )


# ================================================================= GIFT KEY
@router.callback_query(F.data == "adm_gift")
async def cb_gift(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GiftKey.user_id)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🎁 <b>Выдать бесплатный ключ</b>\n\nВведите Telegram ID пользователя:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(GiftKey.user_id)
async def gift_step_user(message: Message, state: FSMContext) -> None:
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID:")
        return
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(user_id=tg_id)
    await state.set_state(GiftKey.days)
    await message.answer(
        f"Пользователь найден: {html.escape(user.full_name or str(tg_id))}\n\n"
        f"Введите количество дней для ключа:",
        reply_markup=admin_kb.cancel_kb(),
    )


@router.message(GiftKey.days)
async def gift_step_days(message: Message, state: FSMContext, bot: Bot) -> None:
    from app.services.vpn_generator import generate_qr, generate_vpn_key, select_best_server
    from aiogram.types import BufferedInputFile
    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число:")
        return
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == data["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return

        server = await select_best_server(session)
        if not server:
            await message.answer("Нет доступных серверов.")
            return

        class GiftTariff:
            id = None
            name = "Подарок"
            days_val = days
            devices = 1

        gt = GiftTariff()
        gt.days = days

        try:
            sub = await generate_vpn_key(session, user, gt, server)  # type: ignore[arg-type]
            sub.tariff_id = None
            await session.commit()
        except Exception as exc:
            logger.error("Gift VPN error: %s", exc)
            await message.answer(f"Ошибка: {exc}")
            return

    await message.answer(f"✅ Ключ выдан пользователю {data['user_id']} на {days} дней!")
    try:
        await bot.send_message(
            data["user_id"],
            f"🎁 <b>Вам выдан подарочный VPN!</b>\n\n"
            f"Срок: {days} дней\n\n"
            f"Ваш ключ:\n<code>{html.escape(sub.vless_link)}</code>",
        )
        qr_buf = generate_qr(sub.vless_link)
        await bot.send_photo(
            data["user_id"],
            BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
            caption="📱 QR-код для подключения",
        )
    except Exception:
        await message.answer("Ключ создан, но не удалось отправить пользователю.")


# ================================================================= INSTRUCTION
@router.callback_query(F.data == "adm_instruction")
async def cb_instruction(call: CallbackQuery) -> None:
    async with async_session() as session:
        text = await _get_setting(session, "connect_instruction", "")
    preview = html.escape(text[:200]) + "..." if len(text) > 200 else html.escape(text) if text else "Инструкция не задана."
    await call.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Инструкция по подключению</b>\n\n{preview}",
        reply_markup=admin_kb.instruction_menu(),
    )
    await call.answer()


@router.callback_query(F.data == "instruction_view")
async def cb_instruction_view(call: CallbackQuery) -> None:
    async with async_session() as session:
        text = await _get_setting(session, "connect_instruction", "")
    if not text:
        await call.answer("Инструкция не задана.", show_alert=True)
        return
    await call.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Инструкция:</b>\n\n{html.escape(text)}",
        reply_markup=admin_kb.instruction_menu(),
    )
    await call.answer()


@router.callback_query(F.data == "instruction_edit")
async def cb_instruction_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditInstruction.text)
    await call.message.edit_text(  # type: ignore[union-attr]
        "📝 Введите новый текст инструкции по подключению:\n\n"
        "(Поддерживается HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>)",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(EditInstruction.text)
async def instruction_save(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        await _set_setting(session, "connect_instruction", message.text or "")
    await message.answer(
        "✅ Инструкция сохранена!",
        reply_markup=admin_kb.instruction_menu(),
    )


# ================================================================= CLIENTS LIST + SEARCH
@router.callback_query(F.data == "adm_clients")
async def cb_clients(call: CallbackQuery) -> None:
    await _show_clients_page(call, 0)


@router.callback_query(F.data.startswith("clients_page:"))
async def cb_clients_page(call: CallbackQuery) -> None:
    page = int(call.data.split(":")[1])
    await _show_clients_page(call, page)


async def _show_clients_page(call: CallbackQuery, page: int) -> None:
    per_page = 10
    async with async_session() as session:
        total = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        total_pages = max(1, (total + per_page - 1) // per_page)
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).offset(page * per_page).limit(per_page)
        )
        users = list(result.scalars().all())

    lines = [f"👥 <b>Клиенты</b> (стр. {page+1}/{total_pages}, всего {total})\n"]
    for u in users:
        status = "🚫" if u.is_blocked else "✅"
        uname = f"@{u.username}" if u.username else f"ID:{u.telegram_id}"
        lines.append(f"{status} <code>{u.telegram_id}</code> — {html.escape(uname)}")

    await call.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines),
        reply_markup=admin_kb.clients_list_kb(page, total_pages),
    )
    await call.answer()


@router.callback_query(F.data == "adm_client_search")
async def cb_client_search(call: CallbackQuery, state: FSMContext) -> None:
    from app.bot.states.states import BlockUser
    await state.set_state("client_search")
    await call.message.edit_text(  # type: ignore[union-attr]
        "🔍 Введите Telegram ID пользователя:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(F.text)
async def handle_client_search(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current != "client_search":
        return
    await state.clear()
    try:
        tg_id = int(message.text.strip())  # type: ignore[union-attr]
    except (ValueError, AttributeError):
        await message.answer("Введите числовой ID.")
        return
    await _show_client_card(message, tg_id)


async def _show_client_card(obj, tg_id: int) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if not user:
            if hasattr(obj, "answer"):
                await obj.answer("Пользователь не найден.")
            else:
                await obj.message.edit_text("Пользователь не найден.", reply_markup=admin_kb.cancel_kb())
            return

        subs_res = await session.execute(
            select(Subscription).where(Subscription.user_id == user.id, Subscription.is_active.is_(True))
        )
        active_subs = list(subs_res.scalars().all())
        pmts_res = await session.execute(
            select(func.count(), func.sum(Payment.amount)).where(
                Payment.user_id == user.id, Payment.status == "paid"
            )
        )
        pmt_row = pmts_res.one()
        pmt_count = pmt_row[0] or 0
        pmt_total = int(pmt_row[1] or 0)

    uname = f"@{user.username}" if user.username else "—"
    reg = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"
    status = "🚫 Заблокирован" if user.is_blocked else "✅ Активен"

    sub_lines = []
    for s in active_subs:
        sub_lines.append(f"  🔑 до {s.expire_date.strftime('%d.%m.%Y')}")

    text = (
        f"👤 <b>Карточка клиента</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"👤 Имя: {html.escape(user.full_name or '—')}\n"
        f"📱 Username: {html.escape(uname)}\n"
        f"📅 Регистрация: {reg}\n"
        f"⚡ Статус: {status}\n"
        f"⭐ Бонусных дней: {user.bonus_days}\n\n"
        f"🔑 Активных подписок: {len(active_subs)}\n"
        + ("\n".join(sub_lines) + "\n" if sub_lines else "") +
        f"\n💳 Платежей: {pmt_count} на {pmt_total}₽"
    )
    kb = admin_kb.client_actions(user.telegram_id, user.is_blocked)
    if hasattr(obj, "answer"):
        await obj.answer(text, reply_markup=kb)
    else:
        await obj.message.edit_text(text, reply_markup=kb)


# ---- Block / Unblock
@router.callback_query(F.data.startswith("adm_block:"))
async def cb_block_user(call: CallbackQuery) -> None:
    tg_id = int(call.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_blocked = True
            await session.commit()
    await call.answer("🚫 Пользователь заблокирован.", show_alert=True)
    await _show_client_card(call, tg_id)


@router.callback_query(F.data.startswith("adm_unblock:"))
async def cb_unblock_user(call: CallbackQuery) -> None:
    tg_id = int(call.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_blocked = False
            await session.commit()
    await call.answer("✅ Пользователь разблокирован.", show_alert=True)
    await _show_client_card(call, tg_id)


# ---- Extend user subscription
@router.callback_query(F.data.startswith("adm_extend_sub:"))
async def cb_extend_sub_start(call: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(call.data.split(":")[1])
    await state.set_state(ExtendUserSub.days)
    await state.update_data(user_id=tg_id)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"⏳ Продление подписки для <code>{tg_id}</code>\n\nВведите количество дней:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(ExtendUserSub.days)
async def cb_extend_sub_days(message: Message, state: FSMContext) -> None:
    try:
        days = int(message.text.strip())  # type: ignore[union-attr]
    except (ValueError, AttributeError):
        await message.answer("Введите число.")
        return
    data = await state.get_data()
    await state.clear()
    tg_id = data["user_id"]

    from datetime import timedelta
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        subs_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user.id, Subscription.is_active.is_(True)
            )
        )
        subs = list(subs_res.scalars().all())
        if not subs:
            await message.answer("У пользователя нет активных подписок.")
            return
        for sub in subs:
            sub.expire_date = sub.expire_date + timedelta(days=days)
        await session.commit()

    await message.answer(f"✅ Подписка продлена на {days} дней для пользователя <code>{tg_id}</code>!")


# ---- Gift to specific user
@router.callback_query(F.data.startswith("adm_gift_to:"))
async def cb_gift_to(call: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(call.data.split(":")[1])
    await state.set_state(GiftKey.days)
    await state.update_data(user_id=tg_id)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🎁 Выдать ключ пользователю <code>{tg_id}</code>\n\nВведите количество дней:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


# ================================================================= TARIFF EDIT (name, devices, sort)
@router.callback_query(F.data.startswith("adm_t_name:"))
async def cb_tariff_edit_name(call: CallbackQuery, state: FSMContext) -> None:
    t_id = int(call.data.split(":")[1])
    await state.set_state(EditTariffField.value)
    await state.update_data(tariff_id=t_id, field="name")
    await call.message.edit_text(  # type: ignore[union-attr]
        "✏️ Введите новое название тарифа:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_t_devices:"))
async def cb_tariff_edit_devices(call: CallbackQuery, state: FSMContext) -> None:
    t_id = int(call.data.split(":")[1])
    await state.set_state(EditTariffField.value)
    await state.update_data(tariff_id=t_id, field="devices")
    await call.message.edit_text(  # type: ignore[union-attr]
        "✏️ Введите новый лимит устройств:",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_t_sort:"))
async def cb_tariff_edit_sort(call: CallbackQuery, state: FSMContext) -> None:
    t_id = int(call.data.split(":")[1])
    await state.set_state(EditTariffField.value)
    await state.update_data(tariff_id=t_id, field="sort_order")
    await call.message.edit_text(  # type: ignore[union-attr]
        "✏️ Введите порядок сортировки (меньше = выше в списке):",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(EditTariffField.value)
async def cb_tariff_field_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    t_id = data["tariff_id"]
    field = data["field"]
    value = message.text.strip() if message.text else ""

    async with async_session() as session:
        tariff = await session.get(Tariff, t_id)
        if not tariff:
            await message.answer("Тариф не найден.")
            return
        if field == "name":
            tariff.name = value
        elif field == "devices":
            if not value.isdigit():
                await message.answer("Введите число.")
                return
            tariff.devices = int(value)
        elif field == "sort_order":
            if not value.isdigit():
                await message.answer("Введите число.")
                return
            tariff.sort_order = int(value)
        await session.commit()
        await message.answer(
            f"✅ Тариф обновлён!\n\n"
            f"<b>{html.escape(tariff.name)}</b>\n"
            f"Цена: {int(tariff.price)}₽ | Дней: {tariff.days} | Устройств: {tariff.devices}",
            reply_markup=admin_kb.tariff_actions(t_id),
        )


# ================================================================= NOTIFICATIONS SETTINGS
@router.callback_query(F.data == "adm_notify")
async def cb_notify_settings(call: CallbackQuery) -> None:
    async with async_session() as session:
        enabled = await _get_setting(session, "notify_enabled", "true")
        days_str = await _get_setting(session, "notify_days", "7,3,1")

    status = "✅ Включены" if enabled == "true" else "❌ Выключены"
    text = (
        f"🔔 <b>Настройки уведомлений</b>\n\n"
        f"Статус: {status}\n"
        f"Дни для уведомлений: <b>{days_str}</b>\n\n"
        f"(клиенты получают уведомления за указанное кол-во дней до конца подписки)"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.notify_settings_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data == "notify_on")
async def cb_notify_on(call: CallbackQuery) -> None:
    async with async_session() as session:
        await _set_setting(session, "notify_enabled", "true")
    await call.answer("✅ Уведомления включены!", show_alert=True)
    await cb_notify_settings(call)


@router.callback_query(F.data == "notify_off")
async def cb_notify_off(call: CallbackQuery) -> None:
    async with async_session() as session:
        await _set_setting(session, "notify_enabled", "false")
    await call.answer("❌ Уведомления выключены!", show_alert=True)
    await cb_notify_settings(call)


@router.callback_query(F.data == "notify_edit_days")
async def cb_notify_edit_days(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NotifySettings.days)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🔔 Введите дни для уведомлений через запятую\n"
        "Например: <code>7,3,1</code>",
        reply_markup=admin_kb.cancel_kb(),
    )
    await call.answer()


@router.message(NotifySettings.days)
async def cb_notify_days_save(message: Message, state: FSMContext) -> None:
    await state.clear()
    value = message.text.strip() if message.text else "7,3,1"
    async with async_session() as session:
        await _set_setting(session, "notify_days", value)
    await message.answer(
        f"✅ Дни уведомлений обновлены: <b>{html.escape(value)}</b>",
        reply_markup=admin_kb.notify_settings_kb(),
    )


# ================================================================= PROMO DEACTIVATE
@router.callback_query(F.data.startswith("promo_deactivate:"))
async def cb_promo_deactivate(call: CallbackQuery) -> None:
    from app.database.models import PromoCode
    promo_id = int(call.data.split(":")[1])
    async with async_session() as session:
        promo = await session.get(PromoCode, promo_id)
        if promo:
            promo.is_active = False
            await session.commit()
    await call.answer("❌ Промокод деактивирован.", show_alert=True)
    await cb_promo_list(call)


# ================================================================= EXPORT CSV
@router.callback_query(F.data == "adm_export")
async def cb_export_csv(call: CallbackQuery, bot: Bot) -> None:
    import csv
    import io
    from aiogram.types import BufferedInputFile

    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        users = list(result.scalars().all())

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Telegram ID", "Имя", "Username", "Регистрация", "Бонусов", "Заблокирован"])

        for u in users:
            writer.writerow([
                u.id,
                u.telegram_id,
                u.full_name or "",
                u.username or "",
                u.created_at.strftime("%d.%m.%Y %H:%M") if u.created_at else "",
                u.bonus_days,
                "Да" if u.is_blocked else "Нет",
            ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    await bot.send_document(
        call.from_user.id,  # type: ignore[union-attr]
        BufferedInputFile(csv_bytes, filename="users_export.csv"),
        caption=f"📤 Экспорт пользователей — {len(users)} чел.",
    )
    await call.answer("✅ CSV отправлен!", show_alert=True)


# ================================================================= TOP CLIENTS in STATS
@router.callback_query(F.data == "adm_stats")
async def cb_stats(call: CallbackQuery) -> None:
    from sqlalchemy import desc
    async with async_session() as session:
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        active_subs = (await session.execute(
            select(func.count()).select_from(Subscription).where(Subscription.is_active.is_(True))
        )).scalar() or 0
        total_income = (await session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == "paid")
        )).scalar() or 0
        total_servers = (await session.execute(
            select(func.count()).select_from(Server).where(Server.is_active.is_(True))
        )).scalar() or 0
        blocked_users = (await session.execute(
            select(func.count()).select_from(User).where(User.is_blocked.is_(True))
        )).scalar() or 0
        total_promos_used = (await session.execute(
            select(func.sum(PromoCode.used_count)).select_from(PromoCode)
        )).scalar() or 0

        # Топ 5 клиентов
        top_res = await session.execute(
            select(User.telegram_id, User.username, func.sum(Payment.amount).label("total"))
            .join(Payment, Payment.user_id == User.id)
            .where(Payment.status == "paid")
            .group_by(User.id)
            .order_by(desc("total"))
            .limit(5)
        )
        top_clients = top_res.all()

        # Нагрузка серверов
        srv_res = await session.execute(
            select(Server.name, func.count(Subscription.id).label("cnt"))
            .outerjoin(Subscription, (Subscription.server_id == Server.id) & Subscription.is_active.is_(True))
            .group_by(Server.id)
            .order_by(desc("cnt"))
        )
        server_loads = srv_res.all()

    top_lines = []
    for i, (tg_id, uname, total) in enumerate(top_clients, 1):
        name = f"@{uname}" if uname else f"ID:{tg_id}"
        top_lines.append(f"  {i}. {html.escape(name)} — {int(total)}₽")

    srv_lines = []
    for srv_name, cnt in server_loads:
        srv_lines.append(f"  📡 {html.escape(srv_name)}: {cnt} клиентов")

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🚫 Заблокировано: <b>{blocked_users}</b>\n"
        f"🟢 Активных подписок: <b>{active_subs}</b>\n"
        f"💰 Общий доход: <b>{int(total_income)}₽</b>\n"
        f"📡 Активных серверов: <b>{total_servers}</b>\n"
        f"🎁 Промокодов использовано: <b>{int(total_promos_used)}</b>\n\n"
        f"🏆 <b>Топ клиентов:</b>\n" + ("\n".join(top_lines) if top_lines else "  —") + "\n\n"
        f"🖥️ <b>Нагрузка серверов:</b>\n" + ("\n".join(srv_lines) if srv_lines else "  —")
    )
    await call.message.edit_text(text, reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]
    await call.answer()
