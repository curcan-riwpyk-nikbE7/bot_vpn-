"""Admin handlers: servers, tariffs, clients, stats, mailing, settings."""

from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.filters.admin import IsAdmin
from app.bot.keyboards import admin_kb
from app.bot.states.states import AddServer, AddTariff, Mailing
from app.database.database import async_session
from app.database.models import Payment, Server, Setting, Subscription, Tariff, User
from app.services.mailing import broadcast, get_target_users
from app.services.xui import XUIError, XUIService

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


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
        f"Протокол: {html.escape(server.protocol)}\n"
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
    # Return to servers list
    async with async_session() as session:
        result = await session.execute(select(Server))
        servers = list(result.scalars().all())
    await call.message.edit_text("📡 <b>Серверы</b>", reply_markup=admin_kb.servers_menu(servers))  # type: ignore[union-attr]


# ---- Add server FSM
@router.callback_query(F.data == "adm_add_server")
async def cb_add_server(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddServer.name)
    await call.message.edit_text("Введите название сервера:", reply_markup=admin_kb.cancel_kb())  # type: ignore[union-attr]
    await call.answer()


@router.message(AddServer.name)
async def st_srv_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())  # type: ignore[union-attr]
    await state.set_state(AddServer.url)
    await message.answer("URL панели (например https://1.2.3.4:2053):")


@router.message(AddServer.url)
async def st_srv_url(message: Message, state: FSMContext) -> None:
    await state.update_data(url=message.text.strip())  # type: ignore[union-attr]
    await state.set_state(AddServer.login)
    await message.answer("Логин:")


@router.message(AddServer.login)
async def st_srv_login(message: Message, state: FSMContext) -> None:
    await state.update_data(login=message.text.strip())  # type: ignore[union-attr]
    await state.set_state(AddServer.password)
    await message.answer("Пароль:")


@router.message(AddServer.password)
async def st_srv_password(message: Message, state: FSMContext) -> None:
    await state.update_data(password=message.text)  # type: ignore[union-attr]
    await state.set_state(AddServer.inbound_id)
    await message.answer("Inbound ID (число):")


@router.message(AddServer.inbound_id)
async def st_srv_inbound(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    if not text.isdigit():
        await message.answer("Введите число.")
        return
    await state.update_data(inbound_id=int(text))
    await state.set_state(AddServer.domain)
    await message.answer("Домен для клиентов (IP/домен, или «-» чтобы взять из URL):")


@router.message(AddServer.domain)
async def st_srv_domain(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""  # type: ignore[union-attr]
    domain = "" if text in ("-", "—") else text
    await state.update_data(domain=domain)
    await state.set_state(AddServer.protocol)
    await message.answer("Протокол (по умолчанию VLESS Reality, или введите свой):")


@router.message(AddServer.protocol)
async def st_srv_protocol(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else "vless-reality"  # type: ignore[union-attr]
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        from urllib.parse import urlsplit
        domain = data.get("domain") or urlsplit(data["url"]).hostname or ""
        server = Server(
            name=data["name"],
            url=data["url"],
            login=data["login"],
            password=data["password"],
            inbound_id=data["inbound_id"],
            domain=domain,
            protocol=text or "vless-reality",
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)

        # Verify connection
        xui = XUIService(
            base_url=server.url, username=server.login,
            password=server.password, inbound_id=server.inbound_id, domain=server.domain,
        )
        note = ""
        try:
            await xui.check()
            note = "\n🔌 Подключение к панели успешно."
        except XUIError as exc:
            note = f"\n⚠️ Не удалось подключиться: {html.escape(str(exc))}"

    await message.answer(
        f"✅ Сервер добавлен: <b>{html.escape(data['name'])}</b>{note}",
        reply_markup=admin_kb.admin_menu(),
    )


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
    # Refresh list
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
