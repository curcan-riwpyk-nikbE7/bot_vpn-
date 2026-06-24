import time
import datetime
import json
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import ADMIN_IDS
from bot.database import db
from bot.keyboards.admin_kb import (
    admin_main_kb,
    admin_servers_kb,
    admin_server_detail_kb,
    admin_settings_kb,
    admin_tariffs_kb,
    admin_tariff_detail_kb,
    admin_promos_kb,
    admin_payment_detail_kb,
    cancel_kb,
    back_cancel_kb,
)
from bot.services.vpn_service import check_server_status

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class AddServerState(StatesGroup):
    waiting_name = State()
    waiting_url = State()
    waiting_login = State()
    waiting_password = State()


class BroadcastState(StatesGroup):
    waiting_message = State()


class EditTariffPriceState(StatesGroup):
    waiting_price = State()


class EditTariffDiscountState(StatesGroup):
    waiting_discount = State()


class AddTariffState(StatesGroup):
    waiting_months = State()
    waiting_price = State()
    waiting_discount = State()


class AddPromoState(StatesGroup):
    waiting_code = State()
    waiting_discount = State()
    waiting_days = State()
    waiting_max_uses = State()


class EditSettingState(StatesGroup):
    waiting_value = State()


# ==================== SERVERS ====================

@router.callback_query(F.data == "admin_servers")
async def admin_servers(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430", show_alert=True)
        return

    servers = await db.get_servers()
    if not servers:
        text = "\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442."
    else:
        text = f"\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u0430 ({len(servers)}):"
    await callback.message.edit_text(text, reply_markup=admin_servers_kb(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_server_"))
async def admin_server_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    server_id = int(callback.data.split("_")[2])
    server = await db.get_server(server_id)
    if not server:
        await callback.answer("\u0421\u0435\u0440\u0432\u0435\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    status = "\u2705 \u0410\u043a\u0442\u0438\u0432\u0435\u043d" if server["is_active"] else "\u274c \u0412\u044b\u043a\u043b\u044e\u0447\u0435\u043d"
    text = (
        f"\U0001f5a5 {server['flag']} {server['name']}\n\n"
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}\n"
        f"URL: {server['panel_url']}\n"
        f"\u041b\u043e\u0433\u0438\u043d: {server['login']}"
    )
    await callback.message.edit_text(text, reply_markup=admin_server_detail_kb(server_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_check_server_"))
async def admin_check_server(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    server_id = int(callback.data.split("_")[3])
    await callback.answer("\u23f3 \u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430...")

    is_online = await check_server_status(server_id)
    if is_online:
        await callback.answer("\u2705 \u0421\u0435\u0440\u0432\u0435\u0440 \u043e\u043d\u043b\u0430\u0439\u043d!", show_alert=True)
    else:
        await callback.answer("\u274c \u0421\u0435\u0440\u0432\u0435\u0440 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d", show_alert=True)


@router.callback_query(F.data.startswith("admin_toggle_server_"))
async def admin_toggle_server(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    server_id = int(callback.data.split("_")[3])
    await db.toggle_server(server_id)
    server = await db.get_server(server_id)
    status = "\u2705 \u0410\u043a\u0442\u0438\u0432\u0435\u043d" if server["is_active"] else "\u274c \u0412\u044b\u043a\u043b\u044e\u0447\u0435\u043d"
    await callback.answer(f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}", show_alert=True)

    text = (
        f"\U0001f5a5 {server['flag']} {server['name']}\n\n"
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}\n"
        f"URL: {server['panel_url']}\n"
        f"\u041b\u043e\u0433\u0438\u043d: {server['login']}"
    )
    await callback.message.edit_text(text, reply_markup=admin_server_detail_kb(server_id))


@router.callback_query(F.data.startswith("admin_delete_server_"))
async def admin_delete_server(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    server_id = int(callback.data.split("_")[3])
    await db.delete_server(server_id)
    await callback.answer("\u2705 \u0421\u0435\u0440\u0432\u0435\u0440 \u0443\u0434\u0430\u043b\u0435\u043d", show_alert=True)

    servers = await db.get_servers()
    text = f"\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u0430 ({len(servers)}):" if servers else "\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442."
    await callback.message.edit_text(text, reply_markup=admin_servers_kb(servers))


# --- Add Server (step-by-step) ---
@router.callback_query(F.data == "admin_add_server")
async def admin_add_server_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "\U0001f527 \u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 (1/4)\n\n"
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435:\n"
        "_(\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: Server-DE, \u0413\u0435\u0440\u043c\u0430\u043d\u0438\u044f-1)_",
        reply_markup=cancel_kb(),
        parse_mode="Markdown",
    )
    await state.set_state(AddServerState.waiting_name)
    await callback.answer()


@router.message(AddServerState.waiting_name)
async def add_server_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    name = message.text.strip()
    flag = ""
    for ch in name:
        if ord(ch) > 127:
            flag = ch
            break

    await state.update_data(name=name, flag=flag)
    await message.answer(
        f"\U0001f527 \u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 (2/4)\n\n"
        f"\u2705 \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435: {name}\n\n"
        f"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 url \u043f\u0430\u043d\u0435\u043b\u0438:\n"
        f"_(\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: https://192.168.1.1:2053/secretpath/ \u0438\u043b\u0438 \u043f\u0440\u043e\u0441\u0442\u043e 192.168.1.1:2053)_",
        reply_markup=back_cancel_kb("admin_servers"),
        parse_mode="Markdown",
    )
    await state.set_state(AddServerState.waiting_url)


@router.message(AddServerState.waiting_url)
async def add_server_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    url = message.text.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    await state.update_data(panel_url=url)
    data = await state.get_data()
    await message.answer(
        f"\U0001f527 \u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 (3/4)\n\n"
        f"\u2705 \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435: {data['name']}\n"
        f"\u2705 URL \u043f\u0430\u043d\u0435\u043b\u0438: {url}\n\n"
        f"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043b\u043e\u0433\u0438\u043d:\n"
        f"_(\u043b\u043e\u0433\u0438\u043d \u0434\u043b\u044f \u0432\u0445\u043e\u0434\u0430 \u0432 \u043f\u0430\u043d\u0435\u043b\u044c)_",
        reply_markup=back_cancel_kb("admin_servers"),
        parse_mode="Markdown",
    )
    await state.set_state(AddServerState.waiting_login)


@router.message(AddServerState.waiting_login)
async def add_server_login(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.update_data(login=message.text.strip())
    data = await state.get_data()
    await message.answer(
        f"\U0001f527 \u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u0435\u0440\u0432\u0435\u0440\u0430 (4/4)\n\n"
        f"\u2705 \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435: {data['name']}\n"
        f"\u2705 URL \u043f\u0430\u043d\u0435\u043b\u0438: {data['panel_url']}\n"
        f"\u2705 \u041b\u043e\u0433\u0438\u043d: {data['login']}\n\n"
        f"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u0430\u0440\u043e\u043b\u044c:\n"
        f"_(\u043f\u0430\u0440\u043e\u043b\u044c \u0434\u043b\u044f \u0432\u0445\u043e\u0434\u0430 \u0432 \u043f\u0430\u043d\u0435\u043b\u044c)_",
        reply_markup=back_cancel_kb("admin_servers"),
        parse_mode="Markdown",
    )
    await state.set_state(AddServerState.waiting_password)


@router.message(AddServerState.waiting_password)
async def add_server_password(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    await db.add_server(
        name=data["name"],
        flag=data.get("flag", ""),
        panel_url=data["panel_url"],
        login=data["login"],
        password=message.text.strip(),
    )

    await message.answer(
        f"\u2705 \u0421\u0435\u0440\u0432\u0435\u0440 \u00ab{data['name']}\u00bb \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!",
        reply_markup=admin_main_kb(),
    )
    await state.clear()


# --- Cancel ---
@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "\u274c \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e", reply_markup=admin_main_kb()
    )
    await callback.answer()


# ==================== SETTINGS ====================

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u043e\u0442\u0430",
        reply_markup=admin_settings_kb(),
    )
    await callback.answer()


# --- Tariffs ---
@router.callback_query(F.data == "admin_tariffs")
async def admin_tariffs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    tariffs = await db.get_tariffs()
    await callback.message.edit_text(
        "\U0001f4b0 \u0422\u0430\u0440\u0438\u0444\u044b:", reply_markup=admin_tariffs_kb(tariffs)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_tariff_"))
async def admin_tariff_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    tariff_id = int(callback.data.split("_")[2])
    tariff = await db.get_tariff(tariff_id)
    if not tariff:
        await callback.answer("\u0422\u0430\u0440\u0438\u0444 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    text = (
        f"\U0001f4b0 \u0422\u0430\u0440\u0438\u0444: {tariff['months']} \u043c\u0435\u0441.\n\n"
        f"\u0426\u0435\u043d\u0430: {tariff['price']:.0f} \u20bd\n"
        f"\u0421\u043a\u0438\u0434\u043a\u0430: {tariff['discount']}%\n"
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {'\u2705' if tariff['is_active'] else '\u274c'}"
    )
    await callback.message.edit_text(text, reply_markup=admin_tariff_detail_kb(tariff_id))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_edit_tariff_price_"))
async def admin_edit_tariff_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    tariff_id = int(callback.data.split("_")[4])
    await state.update_data(tariff_id=tariff_id)
    await callback.message.edit_text(
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u043e\u0432\u0443\u044e \u0446\u0435\u043d\u0443 (\u0432 \u0440\u0443\u0431\u043b\u044f\u0445):",
        reply_markup=cancel_kb(),
    )
    await state.set_state(EditTariffPriceState.waiting_price)
    await callback.answer()


@router.message(EditTariffPriceState.waiting_price)
async def process_edit_tariff_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return

    data = await state.get_data()
    tariff = await db.get_tariff(data["tariff_id"])
    await db.update_tariff(data["tariff_id"], price, tariff["discount"])
    await message.answer(f"\u2705 \u0426\u0435\u043d\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430: {price:.0f} \u20bd", reply_markup=admin_main_kb())
    await state.clear()


@router.callback_query(F.data.startswith("admin_edit_tariff_discount_"))
async def admin_edit_tariff_discount(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    tariff_id = int(callback.data.split("_")[4])
    await state.update_data(tariff_id=tariff_id)
    await callback.message.edit_text(
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0441\u043a\u0438\u0434\u043a\u0443 (%):",
        reply_markup=cancel_kb(),
    )
    await state.set_state(EditTariffDiscountState.waiting_discount)
    await callback.answer()


@router.message(EditTariffDiscountState.waiting_discount)
async def process_edit_tariff_discount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        discount = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return

    data = await state.get_data()
    tariff = await db.get_tariff(data["tariff_id"])
    await db.update_tariff(data["tariff_id"], tariff["price"], discount)
    await message.answer(f"\u2705 \u0421\u043a\u0438\u0434\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430: {discount}%", reply_markup=admin_main_kb())
    await state.clear()


@router.callback_query(F.data.startswith("admin_delete_tariff_"))
async def admin_delete_tariff(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    tariff_id = int(callback.data.split("_")[3])
    await db.delete_tariff(tariff_id)
    await callback.answer("\u2705 \u0422\u0430\u0440\u0438\u0444 \u0443\u0434\u0430\u043b\u0435\u043d", show_alert=True)
    tariffs = await db.get_tariffs()
    await callback.message.edit_text("\U0001f4b0 \u0422\u0430\u0440\u0438\u0444\u044b:", reply_markup=admin_tariffs_kb(tariffs))


@router.callback_query(F.data == "admin_add_tariff")
async def admin_add_tariff_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u043c\u0435\u0441\u044f\u0446\u0435\u0432:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(AddTariffState.waiting_months)
    await callback.answer()


@router.message(AddTariffState.waiting_months)
async def add_tariff_months(message: Message, state: FSMContext):
    try:
        months = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return
    await state.update_data(months=months)
    await message.answer("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0446\u0435\u043d\u0443 (\u20bd):", reply_markup=cancel_kb())
    await state.set_state(AddTariffState.waiting_price)


@router.message(AddTariffState.waiting_price)
async def add_tariff_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return
    await state.update_data(price=price)
    await message.answer("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0441\u043a\u0438\u0434\u043a\u0443 (%) \u0438\u043b\u0438 0:", reply_markup=cancel_kb())
    await state.set_state(AddTariffState.waiting_discount)


@router.message(AddTariffState.waiting_discount)
async def add_tariff_discount(message: Message, state: FSMContext):
    try:
        discount = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return
    data = await state.get_data()
    await db.add_tariff(data["months"], data["price"], discount)
    await message.answer(
        f"\u2705 \u0422\u0430\u0440\u0438\u0444 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d: {data['months']} \u043c\u0435\u0441. / {data['price']:.0f}\u20bd / {discount}%",
        reply_markup=admin_main_kb(),
    )
    await state.clear()


# ==================== PAYMENTS ====================

@router.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    payments = await db.get_pending_payments()
    if not payments:
        await callback.answer("\u041d\u0435\u0442 \u043e\u0436\u0438\u0434\u0430\u044e\u0449\u0438\u0445 \u043e\u043f\u043b\u0430\u0442", show_alert=True)
        return

    for p in payments[:10]:
        created = datetime.datetime.fromtimestamp(p["created_at"])
        text = (
            f"\U0001f4b0 \u041e\u043f\u043b\u0430\u0442\u0430 #{p['id']}\n\n"
            f"\U0001f464 {p['full_name']} (@{p['username']})\n"
            f"\u0421\u0443\u043c\u043c\u0430: {p['amount']:.0f} \u20bd\n"
            f"\u0422\u0438\u043f: {p['payment_type']}\n"
            f"\u0414\u0430\u0442\u0430: {created.strftime('%d.%m.%Y %H:%M')}"
        )
        await callback.message.answer(text, reply_markup=admin_payment_detail_kb(p["id"]))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[3])
    payment = await db.get_payment(payment_id)
    if not payment:
        await callback.answer("\u041e\u043f\u043b\u0430\u0442\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430", show_alert=True)
        return

    if payment["status"] != "pending":
        await callback.answer("\u041e\u043f\u043b\u0430\u0442\u0430 \u0443\u0436\u0435 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u0430", show_alert=True)
        return

    await db.confirm_payment(payment_id)
    await db.update_balance(payment["user_id"], payment["amount"])

    try:
        await callback.bot.send_message(
            payment["user_id"],
            f"\u2705 \u0412\u0430\u0448 \u043f\u043b\u0430\u0442\u0435\u0436 \u043d\u0430 {payment['amount']:.0f} \u20bd \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d!\n"
            f"\u0411\u0430\u043b\u0430\u043d\u0441 \u043f\u043e\u043f\u043e\u043b\u043d\u0435\u043d.",
        )
    except Exception:
        pass

    await callback.message.edit_text(
        f"\u2705 \u041e\u043f\u043b\u0430\u0442\u0430 #{payment_id} \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430 ({payment['amount']:.0f} \u20bd)"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[3])
    payment = await db.get_payment(payment_id)
    if not payment:
        await callback.answer("\u041e\u043f\u043b\u0430\u0442\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430", show_alert=True)
        return

    await db.reject_payment(payment_id)

    try:
        await callback.bot.send_message(
            payment["user_id"],
            f"\u274c \u0412\u0430\u0448 \u043f\u043b\u0430\u0442\u0435\u0436 \u043d\u0430 {payment['amount']:.0f} \u20bd \u043e\u0442\u043a\u043b\u043e\u043d\u0435\u043d.\n"
            f"\u041e\u0431\u0440\u0430\u0442\u0438\u0442\u0435\u0441\u044c \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443.",
        )
    except Exception:
        pass

    await callback.message.edit_text(f"\u274c \u041e\u043f\u043b\u0430\u0442\u0430 #{payment_id} \u043e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0430")
    await callback.answer()


# ==================== USERS ====================

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    users = await db.get_all_users()
    total = len(users)
    active_subs = await db.get_active_subscriptions_count()

    text = (
        f"\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438\n\n"
        f"\u0412\u0441\u0435\u0433\u043e: {total}\n"
        f"\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a: {active_subs}\n\n"
    )

    recent = users[:20]
    for u in recent:
        reg_date = datetime.datetime.fromtimestamp(u["created_at"])
        text += f"\u2022 {u['full_name']} (@{u['username']}) \u2014 {reg_date.strftime('%d.%m.%Y')}\n"

    if total > 20:
        text += f"\n... \u0438 \u0435\u0449\u0435 {total - 20}"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ==================== BROADCAST ====================

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "\U0001f4e8 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430\n\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0434\u043b\u044f \u0440\u0430\u0441\u0441\u044b\u043b\u043a\u0438:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(BroadcastState.waiting_message)
    await callback.answer()


@router.message(BroadcastState.waiting_message)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    users = await db.get_all_users()
    sent = 0
    failed = 0

    status_msg = await message.answer(f"\u23f3 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430... 0/{len(users)}")

    for u in users:
        try:
            await message.bot.send_message(u["user_id"], message.text)
            sent += 1
        except Exception:
            failed += 1

        if (sent + failed) % 50 == 0:
            try:
                await status_msg.edit_text(f"\u23f3 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430... {sent + failed}/{len(users)}")
            except Exception:
                pass

    await status_msg.edit_text(
        f"\u2705 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430\n\n"
        f"\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e: {sent}\n"
        f"\u041e\u0448\u0438\u0431\u043e\u043a: {failed}",
        reply_markup=admin_main_kb(),
    )
    await state.clear()


# ==================== PROMOS ====================

@router.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    promos = await db.get_all_promos()
    await callback.message.edit_text("\U0001f3ab \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434\u044b:", reply_markup=admin_promos_kb(promos))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo_"))
async def admin_promo_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    promo_id = int(callback.data.split("_")[2])
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c", callback_data=f"admin_delete_promo_{promo_id}")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_promos")],
    ])
    await callback.message.edit_text("\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043f\u0440\u043e\u043c\u043e\u043a\u043e\u0434?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_promo_"))
async def admin_delete_promo(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    promo_id = int(callback.data.split("_")[3])
    await db.delete_promo(promo_id)
    await callback.answer("\u2705 \u0423\u0434\u0430\u043b\u0435\u043d\u043e", show_alert=True)
    promos = await db.get_all_promos()
    await callback.message.edit_text("\U0001f3ab \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434\u044b:", reply_markup=admin_promos_kb(promos))


@router.callback_query(F.data == "admin_add_promo")
async def admin_add_promo_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u0434 \u043f\u0440\u043e\u043c\u043e\u043a\u043e\u0434\u0430:", reply_markup=cancel_kb()
    )
    await state.set_state(AddPromoState.waiting_code)
    await callback.answer()


@router.message(AddPromoState.waiting_code)
async def add_promo_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("\u0421\u043a\u0438\u0434\u043a\u0430 (%) \u0438\u043b\u0438 0:", reply_markup=cancel_kb())
    await state.set_state(AddPromoState.waiting_discount)


@router.message(AddPromoState.waiting_discount)
async def add_promo_discount(message: Message, state: FSMContext):
    try:
        discount = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return
    await state.update_data(discount=discount)
    await message.answer("\u0411\u043e\u043d\u0443\u0441\u043d\u044b\u0445 \u0434\u043d\u0435\u0439 \u0438\u043b\u0438 0:", reply_markup=cancel_kb())
    await state.set_state(AddPromoState.waiting_days)


@router.message(AddPromoState.waiting_days)
async def add_promo_days(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return
    await state.update_data(days=days)
    await message.answer("\u041c\u0430\u043a\u0441. \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0439 (0 = \u0431\u0435\u0437 \u043b\u0438\u043c\u0438\u0442\u0430):", reply_markup=cancel_kb())
    await state.set_state(AddPromoState.waiting_max_uses)


@router.message(AddPromoState.waiting_max_uses)
async def add_promo_max_uses(message: Message, state: FSMContext):
    try:
        max_uses = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e")
        return
    data = await state.get_data()
    await db.add_promo(data["code"], data["discount"], data["days"], max_uses)
    await message.answer(
        f"\u2705 \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434 {data['code'].upper()} \u0441\u043e\u0437\u0434\u0430\u043d!",
        reply_markup=admin_main_kb(),
    )
    await state.clear()


# ==================== PAYMENT SETTINGS ====================

@router.callback_query(F.data == "admin_payment_settings")
async def admin_payment_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    phone = await db.get_setting("sbp_phone")
    bank = await db.get_setting("sbp_bank")
    instructions = await db.get_setting("payment_instructions")

    text = (
        f"\U0001f4b3 \u0420\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u044b \u043e\u043f\u043b\u0430\u0442\u044b\n\n"
        f"\u0422\u0435\u043b\u0435\u0444\u043e\u043d: {phone or '\u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d'}\n"
        f"\u0411\u0430\u043d\u043a: {bank or '\u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d'}\n"
        f"\u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f: {instructions or '\u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430'}"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4f1 \u0422\u0435\u043b\u0435\u0444\u043e\u043d \u0421\u0411\u041f", callback_data="admin_set_sbp_phone")],
        [InlineKeyboardButton(text="\U0001f3e6 \u0411\u0430\u043d\u043a", callback_data="admin_set_sbp_bank")],
        [InlineKeyboardButton(text="\U0001f4dd \u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f", callback_data="admin_set_payment_instructions")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_"))
async def admin_set_setting(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    setting_map = {
        "admin_set_sbp_phone": ("sbp_phone", "\u0442\u0435\u043b\u0435\u0444\u043e\u043d \u0421\u0411\u041f"),
        "admin_set_sbp_bank": ("sbp_bank", "\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0431\u0430\u043d\u043a\u0430"),
        "admin_set_payment_instructions": ("payment_instructions", "\u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044e \u043e\u043f\u043b\u0430\u0442\u044b"),
    }

    if callback.data not in setting_map:
        return

    key, label = setting_map[callback.data]
    await state.update_data(setting_key=key)
    await callback.message.edit_text(f"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 {label}:", reply_markup=cancel_kb())
    await state.set_state(EditSettingState.waiting_value)
    await callback.answer()


@router.message(EditSettingState.waiting_value)
async def process_edit_setting(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await db.set_setting(data["setting_key"], message.text.strip())
    await message.answer("\u2705 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430!", reply_markup=admin_main_kb())
    await state.clear()


# ==================== TEST SETTINGS ====================

@router.callback_query(F.data == "admin_test_settings")
async def admin_test_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    hours = await db.get_setting("test_period_hours", "24")
    devices = await db.get_setting("test_devices", "1")

    text = (
        f"\u23f0 \u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434\n\n"
        f"\u0412\u0440\u0435\u043c\u044f: {hours} \u0447.\n"
        f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {devices}"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u23f0 \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0432\u0440\u0435\u043c\u044f", callback_data="admin_set_test_hours")],
        [InlineKeyboardButton(text="\U0001f4f1 \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430", callback_data="admin_set_test_devices")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "admin_set_test_hours")
async def admin_set_test_hours(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.update_data(setting_key="test_period_hours")
    await callback.message.edit_text("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0447\u0430\u0441\u043e\u0432:", reply_markup=cancel_kb())
    await state.set_state(EditSettingState.waiting_value)
    await callback.answer()


@router.callback_query(F.data == "admin_set_test_devices")
async def admin_set_test_devices(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.update_data(setting_key="test_devices")
    await callback.message.edit_text("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432:", reply_markup=cancel_kb())
    await state.set_state(EditSettingState.waiting_value)
    await callback.answer()


# ==================== REFERRAL SETTINGS ====================

@router.callback_query(F.data == "admin_referral_settings")
async def admin_referral_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    percent = await db.get_setting("referral_percent", "10")
    text = f"\U0001f91d \u0420\u0435\u0444\u0435\u0440\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430\n\n\u041f\u0440\u043e\u0446\u0435\u043d\u0442: {percent}%"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u270f\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u043f\u0440\u043e\u0446\u0435\u043d\u0442", callback_data="admin_set_referral_percent")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "admin_set_referral_percent")
async def admin_set_referral_percent(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.update_data(setting_key="referral_percent")
    await callback.message.edit_text("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u0440\u043e\u0446\u0435\u043d\u0442 \u0440\u0435\u0444\u0435\u0440\u0430\u043b\u044c\u043d\u043e\u0439 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u044b:", reply_markup=cancel_kb())
    await state.set_state(EditSettingState.waiting_value)
    await callback.answer()


# ==================== LOGS ====================

@router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    users = await db.get_all_users()
    revenue = await db.get_total_revenue()
    active_subs = await db.get_active_subscriptions_count()

    text = (
        f"\U0001f4cb \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430\n\n"
        f"\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: {len(users)}\n"
        f"\U0001f4b0 \u0414\u043e\u0445\u043e\u0434: {revenue:.0f} \u20bd\n"
        f"\U0001f4cb \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a: {active_subs}"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
