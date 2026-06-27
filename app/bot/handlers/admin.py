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
from app.bot.states.states import AddServer, AddTariff, Customize, Mailing
from app.database.database import async_session
from app.database.models import Payment, Server, Setting, Subscription, Tariff, User
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


# ================================================================= STATS
@router.callback_query(F.data == "adm_stats")
async def cb_stats(call: CallbackQuery) -> None:
    async with async_session() as session:
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        active_subs = (
            await session.execute(
                select(func.count()).select_from(Subscription).where(Subscription.is_active.is_(True))
            )
        ).scalar() or 0
        total_income = (
            await session.execute(
                select(func.sum(Payment.amount)).where(Payment.status == "paid")
            )
        ).scalar() or 0
        total_servers = (
            await session.execute(
                select(func.count()).select_from(Server).where(Server.is_active.is_(True))
            )
        ).scalar() or 0

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего клиентов: {total_users}\n"
        f"🟢 Активные подписки: {active_subs}\n"
        f"💰 Доход: {int(total_income)}₽\n"
        f"📡 Серверов: {total_servers}"
    )
    await call.message.edit_text(text, reply_markup=admin_kb.admin_menu())  # type: ignore[union-attr]
    await call.answer()


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

    text = (
        f"🎨 <b>Кастомизация бота</b>\n\n"
        f"Название: <b>{html.escape(name)}</b>\n"
        f"Поддержка: {html.escape(support)}\n"
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
