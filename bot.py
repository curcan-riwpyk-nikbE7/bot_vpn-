"""VPN sales Telegram bot.

Run with: ``python bot.py``

Provides a user flow (browse tariffs, pay, receive a VPN key, manage keys) and a
full admin panel (statistics, server management with load balancing, tariff
management and manual key issuing).
"""

from __future__ import annotations

import asyncio
import html
import logging
import uuid
from urllib.parse import urlsplit

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import keyboards as kb
from config import Config, load_config
from database import Database, Server, Tariff
from vpn_generator import generate
from vpn_provisioner import ProvisionError, SSHTarget, WireGuardProvisioner
from xui_provisioner import XUIError, XUIPanel, XUIProvisioner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("vpn_bot")

router = Router()


# --------------------------------------------------------------- FSM states
class AddServer(StatesGroup):
    name = State()
    host = State()
    port = State()
    protocol = State()
    public_key = State()
    max_connections = State()


class AddPanel(StatesGroup):
    name = State()
    panel_url = State()
    username = State()
    password = State()
    inbound_id = State()
    public_host = State()
    max_connections = State()


class SetLimit(StatesGroup):
    value = State()


class AddTariff(StatesGroup):
    name = State()
    days = State()
    price = State()
    description = State()


class CreateKey(StatesGroup):
    user_id = State()
    server = State()
    tariff = State()


# ------------------------------------------------------------------ helpers
def _admin_only(config: Config, user_id: int) -> bool:
    return config.is_admin(user_id)


async def _safe_edit(call: CallbackQuery, text: str, markup=None) -> None:
    """Edit the message tied to a callback, falling back to sending a new one."""
    if call.message is None:
        return
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:  # message not modified / not editable
        await call.message.answer(text, reply_markup=markup)


def _server_label(s: Server) -> str:
    status = "🟢 активен" if s.is_active else "🔴 отключён"
    if s.is_panel:
        return (
            f"🛡️ <b>{html.escape(s.name)}</b> (3X-UI)\n"
            f"Панель: <code>{html.escape(s.panel_url or '-')}</code>\n"
            f"Адрес для клиентов: <code>{html.escape(s.host)}</code>\n"
            f"Inbound ID: {s.inbound_id}\n"
            f"Нагрузка: {s.load}/{s.max_connections} ({s.load_percent}%)\n"
            f"Статус: {status}"
        )
    return (
        f"🖥️ <b>{html.escape(s.name)}</b>\n"
        f"Адрес: <code>{html.escape(s.host)}:{s.port}</code>\n"
        f"Протокол: {html.escape(s.protocol)}\n"
        f"Нагрузка: {s.load}/{s.max_connections} ({s.load_percent}%)\n"
        f"Статус: {status}"
    )


def _tariff_label(t: Tariff, currency: str) -> str:
    status = "🟢 активен" if t.is_active else "🔴 отключён"
    desc = f"\n{html.escape(t.description)}" if t.description else ""
    return (
        f"💰 <b>{html.escape(t.name)}</b>\n"
        f"Цена: {t.price} {currency}\n"
        f"Срок: {t.days} дн.\n"
        f"Статус: {status}{desc}"
    )


def _ssh_target(config: Config, server: Server) -> SSHTarget:
    return SSHTarget(
        host=server.host,
        user=config.wg_ssh_user,
        port=config.wg_ssh_port,
        key_path=config.wg_ssh_key or None,
        password=config.wg_ssh_password or None,
    )


def _provision_wireguard(config: Config, server: Server, label: str) -> tuple[str, str, str | None]:
    """Register a real WireGuard peer on ``server``.

    Returns ``(config_text, access_link, peer_public_key)``. Raises
    :class:`ProvisionError` if the server cannot be reached/updated.
    """
    if not server.public_key:
        raise ProvisionError("server has no public key; add it via the install script output")
    provisioner = WireGuardProvisioner(
        ssh=_ssh_target(config, server),
        interface=config.wg_interface,
        subnet=config.wg_subnet,
    )
    result = provisioner.add_peer(
        server_public_key=server.public_key,
        endpoint_host=server.host,
        endpoint_port=server.port,
        dns=config.wg_dns,
        label=label,
    )
    return result.client_config, None, result.client_public_key


async def _provision_xui(
    config: Config, server: Server, user_id: int, days: int
) -> tuple[str, str, str]:
    """Create a client on a 3X-UI panel.

    Returns ``(access_link, access_link, client_uuid)``. Raises :class:`XUIError`
    if the panel rejects the request or is unreachable.
    """
    panel = XUIPanel(
        base_url=server.panel_url or "",
        username=server.panel_user or "",
        password=server.panel_pass or "",
        inbound_id=server.inbound_id or 0,
        public_host=server.host or "",
        verify_ssl=config.xui_verify_ssl,
    )
    provisioner = XUIProvisioner(panel)
    email = f"{user_id}-{uuid.uuid4().hex[:8]}"
    result = await provisioner.add_client(email=email, days=days, flow=config.xui_flow)
    return result.access_link, result.access_link, result.client_uuid


async def _deliver_key(
    bot: Bot,
    chat_id: int,
    db: Database,
    config: Config,
    *,
    user_id: int,
    tariff: Tariff | None,
    server: Server | None,
    days: int,
    record_payment: bool,
    amount: int,
) -> bool:
    """Generate, persist and deliver a VPN key. Returns True on success."""
    if server is None:
        server = await db.pick_best_server()
    if server is None:
        await bot.send_message(
            chat_id,
            "⚠️ Нет доступных серверов с свободными слотами. Попробуйте позже "
            "или обратитесь в поддержку.",
        )
        return False

    label = f"VPN-{server.name}-{user_id}"
    peer_public_key: str | None = None

    if server.is_panel:
        # 3X-UI panel: create a real client through the panel API. There is no
        # usable offline fallback, so abort (without charging) if it fails.
        try:
            config_text, access_link, peer_public_key = await _provision_xui(
                config, server, user_id, days
            )
            protocol = "3X-UI"
        except XUIError as exc:
            logger.error("3X-UI provisioning failed for server %s: %s", server.id, exc)
            await bot.send_message(
                chat_id,
                "⚠️ Не удалось создать ключ на панели. Попробуйте позже или "
                "обратитесь в поддержку.",
            )
            return False
    else:
        cred = generate(server.protocol, server.host, server.port, server.public_key, label)
        config_text = cred.config
        access_link = cred.access_link
        protocol = cred.protocol

        # When enabled, register a real peer on the WireGuard server over SSH so
        # the issued config actually works. Fall back to offline config on failure.
        if config.wg_auto_provision and protocol.lower() == "wireguard":
            try:
                config_text, access_link, peer_public_key = await asyncio.to_thread(
                    _provision_wireguard, config, server, label
                )
            except ProvisionError as exc:
                logger.error("WireGuard provisioning failed for server %s: %s", server.id, exc)

    key_id = await db.add_key(
        user_id=user_id,
        server_id=server.id,
        tariff_id=tariff.id if tariff else None,
        protocol=protocol,
        config=config_text,
        access_link=access_link,
        days=days,
        peer_public_key=peer_public_key,
    )

    if record_payment:
        await db.add_payment(
            user_id=user_id,
            tariff_id=tariff.id if tariff else None,
            key_id=key_id,
            amount=amount,
            currency=config.currency,
            status="paid",
        )

    text = (
        f"✅ <b>Ваш VPN ключ готов!</b>\n\n"
        f"Сервер: {html.escape(server.name)} ({html.escape(protocol)})\n"
        f"Срок действия: {days} дн.\n\n"
        f"<pre>{html.escape(config_text)}</pre>"
    )
    await bot.send_message(chat_id, text)

    # Provide importable files for protocols that use them.
    filename = None
    if protocol.lower() == "wireguard":
        filename = f"wg-{key_id}.conf"
    elif protocol.lower() == "openvpn":
        filename = f"client-{key_id}.ovpn"
    if filename:
        await bot.send_document(
            chat_id,
            BufferedInputFile(config_text.encode(), filename=filename),
            caption="Импортируйте этот файл в приложение VPN.",
        )
    return True


# -------------------------------------------------------------- user flow
@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    if user is None:
        return
    await db.upsert_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 Привет, {html.escape(user.full_name)}!\n\n"
        "Это бот для покупки доступа к VPN. Выберите действие:",
        reply_markup=kb.main_menu(),
    )


@router.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery) -> None:
    await _safe_edit(call, "Главное меню. Выберите действие:", kb.main_menu())
    await call.answer()


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery) -> None:
    text = (
        "ℹ️ <b>Помощь</b>\n\n"
        "• «Купить VPN» — выберите тариф и оплатите, бот пришлёт ключ.\n"
        "• «Мои ключи» — список ваших активных ключей и их срок.\n\n"
        "Для WireGuard/OpenVPN импортируйте присланный файл в приложение.\n"
        "Для V2Ray/VLESS скопируйте ссылку в клиент (v2rayNG, Nekoray и т.п.)."
    )
    await _safe_edit(call, text, kb.back_main())
    await call.answer()


@router.callback_query(F.data == "buy")
async def cb_buy(call: CallbackQuery, db: Database, config: Config) -> None:
    tariffs = await db.list_tariffs(active_only=True)
    if not tariffs:
        await _safe_edit(
            call,
            "😔 Пока нет доступных тарифов. Загляните позже.",
            kb.back_main(),
        )
        await call.answer()
        return
    await _safe_edit(
        call,
        "Выберите тариф:",
        kb.tariffs_menu(tariffs, config.currency),
    )
    await call.answer()


@router.callback_query(F.data.startswith("buy_tariff:"))
async def cb_buy_tariff(call: CallbackQuery, db: Database, config: Config) -> None:
    tariff_id = int(call.data.split(":", 1)[1])
    tariff = await db.get_tariff(tariff_id)
    if tariff is None or not tariff.is_active:
        await call.answer("Тариф недоступен", show_alert=True)
        return
    text = (
        f"{_tariff_label(tariff, config.currency)}\n\n"
        "Нажмите «Оплатить» для продолжения."
    )
    await _safe_edit(call, text, kb.confirm_purchase(tariff.id))
    await call.answer()


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(call: CallbackQuery, db: Database, config: Config, bot: Bot) -> None:
    tariff_id = int(call.data.split(":", 1)[1])
    tariff = await db.get_tariff(tariff_id)
    if tariff is None or not tariff.is_active:
        await call.answer("Тариф недоступен", show_alert=True)
        return
    user = call.from_user

    if config.demo_payments:
        await call.answer("Демо-оплата прошла успешно ✅")
        await _deliver_key(
            bot,
            user.id,
            db,
            config,
            user_id=user.id,
            tariff=tariff,
            server=None,
            days=tariff.days,
            record_payment=True,
            amount=tariff.price,
        )
        if call.message:
            await call.message.answer("Главное меню:", reply_markup=kb.main_menu())
        return

    # Real Telegram Payments: amount is in the smallest currency unit.
    await bot.send_invoice(
        chat_id=user.id,
        title=tariff.name,
        description=tariff.description or f"VPN доступ на {tariff.days} дн.",
        payload=f"tariff:{tariff.id}",
        provider_token=config.payment_provider_token,
        currency=config.currency,
        prices=[LabeledPrice(label=tariff.name, amount=tariff.price * 100)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, db: Database, config: Config, bot: Bot) -> None:
    payload = message.successful_payment.invoice_payload
    user = message.from_user
    if not payload.startswith("tariff:") or user is None:
        return
    tariff = await db.get_tariff(int(payload.split(":", 1)[1]))
    if tariff is None:
        return
    await _deliver_key(
        bot,
        message.chat.id,
        db,
        config,
        user_id=user.id,
        tariff=tariff,
        server=None,
        days=tariff.days,
        record_payment=True,
        amount=tariff.price,
    )
    await message.answer("Главное меню:", reply_markup=kb.main_menu())


@router.callback_query(F.data == "my_keys")
async def cb_my_keys(call: CallbackQuery, db: Database) -> None:
    keys = await db.list_user_keys(call.from_user.id, active_only=True)
    keys = [k for k in keys if not k.is_expired]
    if not keys:
        await _safe_edit(call, "У вас пока нет активных ключей.", kb.back_main())
        await call.answer()
        return
    lines = ["🔑 <b>Ваши ключи:</b>\n"]
    for k in keys:
        lines.append(
            f"#{k.id} • {html.escape(k.server_name or '-')} • "
            f"{html.escape(k.protocol)} • осталось {k.days_left} дн."
        )
    lines.append("\nКонфигурации были отправлены при покупке.")
    await _safe_edit(call, "\n".join(lines), kb.back_main())
    await call.answer()


# -------------------------------------------------------------- admin panel
@router.message(Command("admin"))
async def cmd_admin(message: Message, config: Config) -> None:
    if not _admin_only(config, message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🛠️ <b>Админ-панель</b>", reply_markup=kb.admin_menu())


@router.callback_query(F.data == "adm_back")
async def cb_adm_back(call: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    await _safe_edit(call, "🛠️ <b>Админ-панель</b>", kb.admin_menu())
    await call.answer()


@router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: CallbackQuery, db: Database, config: Config) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    users = await db.count_users()
    active_keys = await db.count_active_keys()
    revenue = await db.total_revenue()
    servers = await db.list_servers(active_only=True)
    tariffs = await db.list_tariffs(active_only=True)
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {users}\n"
        f"🔑 Активных ключей: {active_keys}\n"
        f"💰 Выручка: {revenue} {config.currency}\n"
        f"🖥️ Активных серверов: {len(servers)}\n"
        f"💳 Активных тарифов: {len(tariffs)}"
    )
    await _safe_edit(call, text, kb.admin_back())
    await call.answer()


# ---- server management
@router.callback_query(F.data == "adm_servers")
async def cb_adm_servers(call: CallbackQuery, db: Database, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    servers = await db.list_servers()
    await _safe_edit(call, "🖥️ <b>Серверы</b>", kb.servers_menu(servers))
    await call.answer()


@router.callback_query(F.data.startswith("adm_server:"))
async def cb_adm_server(call: CallbackQuery, db: Database, config: Config) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    server = await db.get_server(int(call.data.split(":", 1)[1]))
    if server is None:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await _safe_edit(call, _server_label(server), kb.server_actions(server.id))
    await call.answer()


@router.callback_query(F.data.startswith("adm_delserver:"))
async def cb_adm_delserver(call: CallbackQuery, db: Database, config: Config) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await db.deactivate_server(int(call.data.split(":", 1)[1]))
    servers = await db.list_servers()
    await _safe_edit(call, "✅ Сервер отключён.", kb.servers_menu(servers))
    await call.answer()


@router.callback_query(F.data.startswith("adm_setlimit:"))
async def cb_adm_setlimit(call: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(SetLimit.value)
    await state.update_data(server_id=int(call.data.split(":", 1)[1]))
    await _safe_edit(call, "Введите новый лимит подключений (число):", kb.cancel_kb())
    await call.answer()


@router.message(SetLimit.value)
async def st_setlimit(message: Message, db: Database, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите положительное число.")
        return
    data = await state.get_data()
    await db.update_server_limit(data["server_id"], int(message.text.strip()))
    await state.clear()
    await message.answer("✅ Лимит обновлён.", reply_markup=kb.admin_menu())


@router.callback_query(F.data == "adm_addserver")
async def cb_adm_addserver(call: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AddServer.name)
    await _safe_edit(call, "Шаг 1/6. Введите название сервера:", kb.cancel_kb())
    await call.answer()


@router.message(AddServer.name)
async def st_server_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AddServer.host)
    await message.answer("Шаг 2/6. Введите адрес сервера (IP или домен):")


@router.message(AddServer.host)
async def st_server_host(message: Message, state: FSMContext) -> None:
    await state.update_data(host=message.text.strip())
    await state.set_state(AddServer.port)
    await message.answer("Шаг 3/6. Введите порт (число):")


@router.message(AddServer.port)
async def st_server_port(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Порт должен быть числом. Повторите:")
        return
    await state.update_data(port=int(message.text.strip()))
    await state.set_state(AddServer.protocol)
    await message.answer(
        "Шаг 4/6. Выберите протокол:",
        reply_markup=kb.protocol_choice("addsrv_proto"),
    )


@router.callback_query(AddServer.protocol, F.data.startswith("addsrv_proto:"))
async def st_server_protocol(call: CallbackQuery, state: FSMContext) -> None:
    proto = call.data.split(":", 1)[1]
    await state.update_data(protocol=proto)
    await state.set_state(AddServer.public_key)
    await _safe_edit(
        call,
        f"Протокол: {proto}\n\nШаг 5/6. Введите публичный ключ сервера "
        "(для WireGuard/V2Ray) или отправьте «-», если не требуется:",
    )
    await call.answer()


@router.message(AddServer.public_key)
async def st_server_pubkey(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    public_key = None if text in ("-", "—", "") else text
    await state.update_data(public_key=public_key)
    await state.set_state(AddServer.max_connections)
    await message.answer("Шаг 6/6. Введите максимальное число подключений (число):")


@router.message(AddServer.max_connections)
async def st_server_maxconn(message: Message, db: Database, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите положительное число.")
        return
    data = await state.get_data()
    server_id = await db.add_server(
        name=data["name"],
        host=data["host"],
        port=data["port"],
        protocol=data["protocol"],
        public_key=data.get("public_key"),
        max_connections=int(message.text.strip()),
    )
    await state.clear()
    await message.answer(
        f"✅ Сервер добавлен (ID {server_id}).",
        reply_markup=kb.admin_menu(),
    )


# ---- 3X-UI panel management
@router.callback_query(F.data == "adm_addpanel")
async def cb_adm_addpanel(call: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AddPanel.name)
    await _safe_edit(
        call,
        "Добавление 3X-UI панели.\n\nШаг 1/7. Введите название (для админки):",
        kb.cancel_kb(),
    )
    await call.answer()


@router.message(AddPanel.name)
async def st_panel_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AddPanel.panel_url)
    await message.answer(
        "Шаг 2/7. Введите URL панели вместе с портом и путём, например:\n"
        "<code>http://1.2.3.4:54321</code> или <code>https://panel.site/secret</code>"
    )


@router.message(AddPanel.panel_url)
async def st_panel_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip().rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        await message.answer("URL должен начинаться с http:// или https://. Повторите:")
        return
    await state.update_data(panel_url=url)
    await state.set_state(AddPanel.username)
    await message.answer("Шаг 3/7. Введите логин админа панели:")


@router.message(AddPanel.username)
async def st_panel_user(message: Message, state: FSMContext) -> None:
    await state.update_data(panel_user=message.text.strip())
    await state.set_state(AddPanel.password)
    await message.answer("Шаг 4/7. Введите пароль админа панели:")


@router.message(AddPanel.password)
async def st_panel_pass(message: Message, state: FSMContext) -> None:
    await state.update_data(panel_pass=message.text)
    await state.set_state(AddPanel.inbound_id)
    await message.answer(
        "Шаг 5/7. Введите ID inbound, в который добавлять клиентов (число "
        "из списка inbounds в панели):"
    )


@router.message(AddPanel.inbound_id)
async def st_panel_inbound(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите числовой ID inbound.")
        return
    await state.update_data(inbound_id=int(message.text.strip()))
    await state.set_state(AddPanel.public_host)
    await message.answer(
        "Шаг 6/7. Введите адрес (IP или домен), который увидят клиенты в ссылке, "
        "или «-», чтобы взять хост из URL панели:"
    )


@router.message(AddPanel.public_host)
async def st_panel_host(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    public_host = "" if text in ("-", "—", "") else text
    await state.update_data(public_host=public_host)
    await state.set_state(AddPanel.max_connections)
    await message.answer("Шаг 7/7. Введите максимальное число подключений (число):")


@router.message(AddPanel.max_connections)
async def st_panel_maxconn(message: Message, db: Database, config: Config, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите положительное число.")
        return
    data = await state.get_data()
    public_host = data.get("public_host") or urlsplit(data["panel_url"]).hostname or ""
    server_id = await db.add_server(
        name=data["name"],
        host=public_host,
        port=0,
        protocol="3x-ui",
        public_key=None,
        max_connections=int(message.text.strip()),
        panel_url=data["panel_url"],
        panel_user=data["panel_user"],
        panel_pass=data["panel_pass"],
        inbound_id=data["inbound_id"],
    )
    await state.clear()

    # Validate credentials/inbound by issuing a quick test login + inbound fetch.
    server = await db.get_server(server_id)
    note = ""
    if server is not None:
        panel = XUIPanel(
            base_url=server.panel_url or "",
            username=server.panel_user or "",
            password=server.panel_pass or "",
            inbound_id=server.inbound_id or 0,
            public_host=server.host or "",
            verify_ssl=config.xui_verify_ssl,
        )
        try:
            await XUIProvisioner(panel).check()
            note = "\n🔌 Подключение к панели успешно."
        except XUIError as exc:
            note = f"\n⚠️ Не удалось подключиться к панели: {html.escape(str(exc))}"

    await message.answer(
        f"✅ Панель 3X-UI добавлена (ID {server_id}).{note}",
        reply_markup=kb.admin_menu(),
    )


# ---- tariff management
@router.callback_query(F.data == "adm_tariffs")
async def cb_adm_tariffs(call: CallbackQuery, db: Database, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.clear()
    tariffs = await db.list_tariffs()
    await _safe_edit(call, "💰 <b>Тарифы</b>", kb.tariffs_admin_menu(tariffs, config.currency))
    await call.answer()


@router.callback_query(F.data.startswith("adm_tariff:"))
async def cb_adm_tariff(call: CallbackQuery, db: Database, config: Config) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    tariff = await db.get_tariff(int(call.data.split(":", 1)[1]))
    if tariff is None:
        await call.answer("Тариф не найден", show_alert=True)
        return
    await _safe_edit(call, _tariff_label(tariff, config.currency), kb.tariff_actions(tariff.id))
    await call.answer()


@router.callback_query(F.data.startswith("adm_deltariff:"))
async def cb_adm_deltariff(call: CallbackQuery, db: Database, config: Config) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await db.deactivate_tariff(int(call.data.split(":", 1)[1]))
    tariffs = await db.list_tariffs()
    await _safe_edit(call, "✅ Тариф отключён.", kb.tariffs_admin_menu(tariffs, config.currency))
    await call.answer()


@router.callback_query(F.data == "adm_addtariff")
async def cb_adm_addtariff(call: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AddTariff.name)
    await _safe_edit(call, "Шаг 1/4. Введите название тарифа:", kb.cancel_kb())
    await call.answer()


@router.message(AddTariff.name)
async def st_tariff_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AddTariff.days)
    await message.answer("Шаг 2/4. Введите количество дней (число):")


@router.message(AddTariff.days)
async def st_tariff_days(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите число дней.")
        return
    await state.update_data(days=int(message.text.strip()))
    await state.set_state(AddTariff.price)
    await message.answer("Шаг 3/4. Введите цену (целое число):")


@router.message(AddTariff.price)
async def st_tariff_price(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите цену числом.")
        return
    await state.update_data(price=int(message.text.strip()))
    await state.set_state(AddTariff.description)
    await message.answer("Шаг 4/4. Введите описание тарифа (или «-» чтобы пропустить):")


@router.message(AddTariff.description)
async def st_tariff_description(message: Message, db: Database, state: FSMContext) -> None:
    text = message.text.strip()
    description = None if text in ("-", "—", "") else text
    data = await state.get_data()
    tariff_id = await db.add_tariff(
        name=data["name"],
        days=data["days"],
        price=data["price"],
        description=description,
    )
    await state.clear()
    await message.answer(f"✅ Тариф добавлен (ID {tariff_id}).", reply_markup=kb.admin_menu())


# ---- manual key creation
@router.callback_query(F.data == "adm_createkey")
async def cb_adm_createkey(call: CallbackQuery, config: Config, state: FSMContext) -> None:
    if not _admin_only(config, call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(CreateKey.user_id)
    await _safe_edit(
        call,
        "Введите Telegram ID пользователя, которому создать ключ:",
        kb.cancel_kb(),
    )
    await call.answer()


@router.message(CreateKey.user_id)
async def st_ck_user(message: Message, db: Database, state: FSMContext) -> None:
    if not message.text or not message.text.strip().lstrip("-").isdigit():
        await message.answer("Введите числовой Telegram ID.")
        return
    await state.update_data(user_id=int(message.text.strip()))
    servers = await db.list_servers(active_only=True)
    if not servers:
        await state.clear()
        await message.answer("Нет активных серверов. Сначала добавьте сервер.",
                             reply_markup=kb.admin_menu())
        return
    await state.set_state(CreateKey.server)
    await message.answer(
        "Выберите сервер:",
        reply_markup=kb.pick_from_list(servers, "ck_server", "adm_back"),
    )


@router.callback_query(CreateKey.server, F.data.startswith("ck_server:"))
async def st_ck_server(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.update_data(server_id=int(call.data.split(":", 1)[1]))
    tariffs = await db.list_tariffs(active_only=True)
    if not tariffs:
        await state.clear()
        await _safe_edit(call, "Нет активных тарифов. Сначала добавьте тариф.", kb.admin_menu())
        await call.answer()
        return
    await state.set_state(CreateKey.tariff)
    await _safe_edit(
        call,
        "Выберите тариф (определяет срок ключа):",
        kb.pick_from_list(tariffs, "ck_tariff", "adm_back"),
    )
    await call.answer()


@router.callback_query(CreateKey.tariff, F.data.startswith("ck_tariff:"))
async def st_ck_tariff(call: CallbackQuery, db: Database, config: Config, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    tariff = await db.get_tariff(int(call.data.split(":", 1)[1]))
    server = await db.get_server(int(data["server_id"]))
    target_user = int(data["user_id"])
    await state.clear()
    if tariff is None or server is None:
        await _safe_edit(call, "Ошибка: сервер или тариф не найден.", kb.admin_menu())
        await call.answer()
        return

    ok = await _deliver_key(
        bot,
        target_user,
        db,
        config,
        user_id=target_user,
        tariff=tariff,
        server=server,
        days=tariff.days,
        record_payment=False,
        amount=0,
    )
    if ok:
        await _safe_edit(
            call,
            f"✅ Ключ создан и отправлен пользователю {target_user}.",
            kb.admin_menu(),
        )
    else:
        await _safe_edit(
            call,
            f"⚠️ Не удалось отправить ключ пользователю {target_user} "
            "(возможно, он не запускал бота).",
            kb.admin_menu(),
        )
    await call.answer()


# ------------------------------------------------------------------- runner
async def main() -> None:
    config = load_config()
    db = Database(config.database_path)
    await db.connect()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Inject shared dependencies into every handler.
    dp["db"] = db
    dp["config"] = config

    logger.info("Bot started. Admins: %s | demo payments: %s", config.admin_ids, config.demo_payments)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
