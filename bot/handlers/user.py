import time
import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database import db
from bot.keyboards.user_kb import (
    main_menu_kb,
    tariff_kb,
    devices_kb,
    server_select_kb,
    payment_confirm_kb,
    back_main_kb,
    cabinet_kb,
    topup_amounts_kb,
)
from bot.services.vpn_service import create_vpn_key, create_test_key

router = Router()


class TopupState(StatesGroup):
    waiting_amount = State()


class PromoState(StatesGroup):
    waiting_code = State()


class SupportState(StatesGroup):
    waiting_message = State()


# --- Cabinet ---
@router.callback_query(F.data == "cabinet")
async def cabinet(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    subs = await db.get_user_subscriptions(callback.from_user.id, active_only=True)

    sub_text = ""
    if subs:
        for s in subs:
            exp = datetime.datetime.fromtimestamp(s["expires_at"])
            sub_text += (
                f"\n{s['server_flag']} {s['server_name']} \u2014 "
                f"\u0434\u043e {exp.strftime('%d.%m.%Y')} "
                f"({s['devices']} \u0443\u0441\u0442\u0440.)"
            )

    text = (
        f"\U0001f464 \u041b\u0438\u0447\u043d\u044b\u0439 \u043a\u0430\u0431\u0438\u043d\u0435\u0442\n\n"
        f"\U0001f4b0 \u0411\u0430\u043b\u0430\u043d\u0441: {user['balance']:.0f} \u20bd\n"
        f"\U0001f4cb \u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0438: {len(subs)}"
    )
    if sub_text:
        text += f"\n{sub_text}"

    await callback.message.edit_text(text, reply_markup=cabinet_kb(has_subs=bool(subs)))
    await callback.answer()


@router.callback_query(F.data == "my_subscriptions")
async def my_subscriptions(callback: CallbackQuery):
    subs = await db.get_user_subscriptions(callback.from_user.id, active_only=True)
    if not subs:
        await callback.answer("\u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a", show_alert=True)
        return

    text = "\U0001f511 \u0412\u0430\u0448\u0438 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438:\n\n"
    for s in subs:
        exp = datetime.datetime.fromtimestamp(s["expires_at"])
        days_left = max(0, int((s["expires_at"] - time.time()) / 86400))
        text += (
            f"{s['server_flag']} {s['server_name']}\n"
            f"\u0414\u043e: {exp.strftime('%d.%m.%Y')} ({days_left} \u0434\u043d.)\n"
            f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {s['devices']}\n"
            f"\u041a\u043b\u044e\u0447:\n<code>{s['vpn_key']}</code>\n\n"
        )

    await callback.message.edit_text(text, reply_markup=back_main_kb(), parse_mode="HTML")
    await callback.answer()


# --- Buy Subscription ---
@router.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: CallbackQuery):
    tariffs = await db.get_tariffs(active_only=True)
    if not tariffs:
        await callback.answer("\u0422\u0430\u0440\u0438\u0444\u044b \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u044b", show_alert=True)
        return

    subscription_image = await db.get_setting("subscription_image")
    text = "\U0001f4b3 \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u0430\u0440\u0438\u0444\u043d\u044b\u0439 \u043f\u043b\u0430\u043d:"

    if subscription_image:
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=subscription_image,
                caption=text,
                reply_markup=tariff_kb(tariffs),
            )
        except Exception:
            await callback.message.edit_text(text, reply_markup=tariff_kb(tariffs))
    else:
        try:
            await callback.message.edit_text(text, reply_markup=tariff_kb(tariffs))
        except Exception:
            await callback.message.answer(text, reply_markup=tariff_kb(tariffs))
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def select_tariff(callback: CallbackQuery):
    tariff_id = int(callback.data.split("_")[1])
    tariff = await db.get_tariff(tariff_id)
    if not tariff:
        await callback.answer("\u0422\u0430\u0440\u0438\u0444 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    text = (
        f"\U0001f527 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u0442\u0430\u0440\u0438\u0444\u0430\n"
        f"\u0411\u0430\u0437\u043e\u0432\u043e: 1 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e\n"
        f"\U0001f4b0 \u041a \u043e\u043f\u043b\u0430\u0442\u0435: {tariff['price']:.0f} \u20bd"
    )
    try:
        await callback.message.edit_text(text, reply_markup=devices_kb(tariff_id, tariff["price"]))
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=devices_kb(tariff_id, tariff["price"]))
    await callback.answer()


@router.callback_query(F.data.startswith("devices_"))
async def select_devices(callback: CallbackQuery):
    parts = callback.data.split("_")
    tariff_id = int(parts[1])
    devices = int(parts[2])

    tariff = await db.get_tariff(tariff_id)
    if not tariff:
        await callback.answer("\u0422\u0430\u0440\u0438\u0444 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    multiplier = float(await db.get_setting("device_price_multiplier", "1.0"))
    total_price = tariff["price"] * (1 + (devices - 1) * multiplier * 0.3)

    servers = await db.get_servers(active_only=True)
    if not servers:
        await callback.answer("\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432", show_alert=True)
        return

    if len(servers) == 1:
        server_id = servers[0]["id"]
        text = (
            f"\U0001f4cb \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u0435:\n\n"
            f"\u0422\u0430\u0440\u0438\u0444: {tariff['months']} \u043c\u0435\u0441.\n"
            f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {devices}\n"
            f"\u0421\u0435\u0440\u0432\u0435\u0440: {servers[0]['flag']} {servers[0]['name']}\n"
            f"\U0001f4b0 \u0418\u0442\u043e\u0433\u043e: {total_price:.0f} \u20bd"
        )
        await callback.message.edit_text(
            text,
            reply_markup=payment_confirm_kb(total_price, tariff_id, devices, server_id),
        )
    else:
        text = (
            f"\U0001f4cb \u0422\u0430\u0440\u0438\u0444: {tariff['months']} \u043c\u0435\u0441. | "
            f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {devices} | "
            f"\U0001f4b0 {total_price:.0f} \u20bd\n\n"
            f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440:"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        buttons = []
        for s in servers:
            flag = s["flag"] if s["flag"] else ""
            buttons.append([
                InlineKeyboardButton(
                    text=f"\U0001f7e2 {flag} {s['name']}",
                    callback_data=f"srv_{tariff_id}_{devices}_{s['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data=f"tariff_{tariff_id}")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("srv_"))
async def select_server_for_buy(callback: CallbackQuery):
    parts = callback.data.split("_")
    tariff_id = int(parts[1])
    devices = int(parts[2])
    server_id = int(parts[3])

    tariff = await db.get_tariff(tariff_id)
    server = await db.get_server(server_id)
    if not tariff or not server:
        await callback.answer("\u041e\u0448\u0438\u0431\u043a\u0430", show_alert=True)
        return

    multiplier = float(await db.get_setting("device_price_multiplier", "1.0"))
    total_price = tariff["price"] * (1 + (devices - 1) * multiplier * 0.3)

    text = (
        f"\U0001f4cb \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u0435:\n\n"
        f"\u0422\u0430\u0440\u0438\u0444: {tariff['months']} \u043c\u0435\u0441.\n"
        f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {devices}\n"
        f"\u0421\u0435\u0440\u0432\u0435\u0440: {server['flag']} {server['name']}\n"
        f"\U0001f4b0 \u0418\u0442\u043e\u0433\u043e: {total_price:.0f} \u20bd"
    )
    await callback.message.edit_text(
        text,
        reply_markup=payment_confirm_kb(total_price, tariff_id, devices, server_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_"))
async def pay_shortcut(callback: CallbackQuery):
    parts = callback.data.split("_")
    tariff_id = int(parts[1])
    devices = int(parts[2])

    tariff = await db.get_tariff(tariff_id)
    if not tariff:
        await callback.answer("\u0422\u0430\u0440\u0438\u0444 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    servers = await db.get_servers(active_only=True)
    if not servers:
        await callback.answer("\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432", show_alert=True)
        return

    server_id = servers[0]["id"]
    multiplier = float(await db.get_setting("device_price_multiplier", "1.0"))
    total_price = tariff["price"] * (1 + (devices - 1) * multiplier * 0.3)

    text = (
        f"\U0001f4cb \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u0435:\n\n"
        f"\u0422\u0430\u0440\u0438\u0444: {tariff['months']} \u043c\u0435\u0441.\n"
        f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {devices}\n"
        f"\u0421\u0435\u0440\u0432\u0435\u0440: {servers[0]['flag']} {servers[0]['name']}\n"
        f"\U0001f4b0 \u0418\u0442\u043e\u0433\u043e: {total_price:.0f} \u20bd"
    )
    await callback.message.edit_text(
        text,
        reply_markup=payment_confirm_kb(total_price, tariff_id, devices, server_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(callback: CallbackQuery):
    parts = callback.data.split("_")
    tariff_id = int(parts[2])
    devices = int(parts[3])
    server_id = int(parts[4])

    tariff = await db.get_tariff(tariff_id)
    user = await db.get_user(callback.from_user.id)
    if not tariff or not user:
        await callback.answer("\u041e\u0448\u0438\u0431\u043a\u0430", show_alert=True)
        return

    multiplier = float(await db.get_setting("device_price_multiplier", "1.0"))
    total_price = tariff["price"] * (1 + (devices - 1) * multiplier * 0.3)

    if user["balance"] < total_price:
        await callback.answer(
            f"\u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0441\u0440\u0435\u0434\u0441\u0442\u0432. \u0411\u0430\u043b\u0430\u043d\u0441: {user['balance']:.0f}\u20bd, \u043d\u0443\u0436\u043d\u043e: {total_price:.0f}\u20bd",
            show_alert=True,
        )
        return

    await callback.message.edit_text("\u23f3 \u0421\u043e\u0437\u0434\u0430\u0435\u043c VPN \u043a\u043b\u044e\u0447...")

    try:
        key = await create_vpn_key(
            user_id=callback.from_user.id,
            server_id=server_id,
            tariff_id=tariff_id,
            devices=devices,
            months=tariff["months"],
        )

        await db.update_balance(callback.from_user.id, -total_price)
        await db.add_payment(callback.from_user.id, total_price, "subscription")

        # Referral bonus
        if user["referrer_id"] and user["referrer_id"] != 0:
            ref_percent = float(await db.get_setting("referral_percent", "10"))
            ref_bonus = total_price * ref_percent / 100
            await db.add_referral_earnings(user["referrer_id"], ref_bonus)

        text = (
            f"\u2705 \u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d\u0430!\n\n"
            f"\u0422\u0430\u0440\u0438\u0444: {tariff['months']} \u043c\u0435\u0441.\n"
            f"\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432: {devices}\n"
            f"\u0421\u043f\u0438\u0441\u0430\u043d\u043e: {total_price:.0f} \u20bd\n\n"
            f"\U0001f511 \u0412\u0430\u0448 VPN \u043a\u043b\u044e\u0447:\n<code>{key}</code>\n\n"
            f"\u0421\u043a\u043e\u043f\u0438\u0440\u0443\u0439\u0442\u0435 \u043a\u043b\u044e\u0447 \u0438 \u0432\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0432 VPN-\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435."
        )
        await callback.message.edit_text(text, reply_markup=back_main_kb(), parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(
            f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u0441\u043e\u0437\u0434\u0430\u043d\u0438\u0438 \u043a\u043b\u044e\u0447\u0430: {e}\n\n"
            f"\u041e\u0431\u0440\u0430\u0442\u0438\u0442\u0435\u0441\u044c \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443.",
            reply_markup=back_main_kb(),
        )
    await callback.answer()


# --- Test Period ---
@router.callback_query(F.data == "test_period")
async def test_period(callback: CallbackQuery):
    user_id = callback.from_user.id
    has_used = await db.has_used_test(user_id)
    if has_used:
        await callback.answer(
            "\u0412\u044b \u0443\u0436\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043b\u0438 \u0442\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434", show_alert=True
        )
        return

    servers = await db.get_servers(active_only=True)
    if not servers:
        await callback.answer("\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432", show_alert=True)
        return

    test_hours = await db.get_setting("test_period_hours", "24")
    text = (
        f"\U0001f3af \u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434: {test_hours} \u0447.\n\n"
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440:"
    )
    await callback.message.edit_text(
        text, reply_markup=server_select_kb(servers, prefix="test_server")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("test_server_"))
async def test_server_select(callback: CallbackQuery):
    server_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    has_used = await db.has_used_test(user_id)
    if has_used:
        await callback.answer("\u0422\u0435\u0441\u0442 \u0443\u0436\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d", show_alert=True)
        return

    await callback.message.edit_text("\u23f3 \u0421\u043e\u0437\u0434\u0430\u0435\u043c \u0442\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u043a\u043b\u044e\u0447...")

    try:
        key = await create_test_key(user_id, server_id)
        test_hours = await db.get_setting("test_period_hours", "24")
        text = (
            f"\u2705 \u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u043a\u043b\u044e\u0447 \u0441\u043e\u0437\u0434\u0430\u043d!\n"
            f"\u0421\u0440\u043e\u043a: {test_hours} \u0447.\n\n"
            f"\U0001f511 \u041a\u043b\u044e\u0447:\n<code>{key}</code>\n\n"
            f"\u0421\u043a\u043e\u043f\u0438\u0440\u0443\u0439\u0442\u0435 \u043a\u043b\u044e\u0447 \u0438 \u0432\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0432 VPN-\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435."
        )
        await callback.message.edit_text(text, reply_markup=back_main_kb(), parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(
            f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}",
            reply_markup=back_main_kb(),
        )
    await callback.answer()


# --- Top up ---
@router.callback_query(F.data == "topup_balance")
async def topup_balance(callback: CallbackQuery):
    sbp_phone = await db.get_setting("sbp_phone")
    sbp_bank = await db.get_setting("sbp_bank")
    instructions = await db.get_setting("payment_instructions")

    text = "\U0001f4b3 \u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435 \u0431\u0430\u043b\u0430\u043d\u0441\u0430\n\n"
    if sbp_phone:
        text += f"\U0001f4f1 \u0422\u0435\u043b\u0435\u0444\u043e\u043d: {sbp_phone}\n"
    if sbp_bank:
        text += f"\U0001f3e6 \u0411\u0430\u043d\u043a: {sbp_bank}\n"
    if instructions:
        text += f"\n{instructions}\n"
    text += "\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0443\u043c\u043c\u0443:"

    await callback.message.edit_text(text, reply_markup=topup_amounts_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("topup_"))
async def topup_amount(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    payment_id = await db.add_payment(user_id, amount, "topup")

    from bot.config import ADMIN_IDS
    from bot.keyboards.admin_kb import admin_payment_detail_kb

    user = await db.get_user(user_id)
    admin_text = (
        f"\U0001f4b0 \u041d\u043e\u0432\u0430\u044f \u0437\u0430\u044f\u0432\u043a\u0430 \u043d\u0430 \u043f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435 #{payment_id}\n\n"
        f"\U0001f464 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c: {user['full_name']} (@{user['username']})\n"
        f"\U0001f4b0 \u0421\u0443\u043c\u043c\u0430: {amount} \u20bd"
    )

    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                admin_id, admin_text, reply_markup=admin_payment_detail_kb(payment_id)
            )
        except Exception:
            pass

    text = (
        f"\u2705 \u0417\u0430\u044f\u0432\u043a\u0430 #{payment_id} \u0441\u043e\u0437\u0434\u0430\u043d\u0430!\n\n"
        f"\u0421\u0443\u043c\u043c\u0430: {amount} \u20bd\n\n"
        f"\u041f\u0435\u0440\u0435\u0432\u0435\u0434\u0438\u0442\u0435 \u0441\u0443\u043c\u043c\u0443 \u043f\u043e \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u0430\u043c \u0432\u044b\u0448\u0435.\n"
        f"\u0411\u0430\u043b\u0430\u043d\u0441 \u0431\u0443\u0434\u0435\u0442 \u043f\u043e\u043f\u043e\u043b\u043d\u0435\u043d \u043f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u043e\u043c."
    )
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()


# --- Promo Code ---
@router.callback_query(F.data == "promo_code")
async def promo_code(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "\U0001f3ab \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u0440\u043e\u043c\u043e\u043a\u043e\u0434:",
        reply_markup=back_main_kb(),
    )
    await state.set_state(PromoState.waiting_code)
    await callback.answer()


@router.message(PromoState.waiting_code)
async def process_promo(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = await db.get_promo_by_code(code)

    if not promo:
        await message.answer(
            "\u274c \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d",
            reply_markup=back_main_kb(),
        )
        await state.clear()
        return

    if promo["max_uses"] > 0 and promo["used_count"] >= promo["max_uses"]:
        await message.answer(
            "\u274c \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442",
            reply_markup=back_main_kb(),
        )
        await state.clear()
        return

    has_used = await db.has_used_promo(message.from_user.id, promo["id"])
    if has_used:
        await message.answer(
            "\u274c \u0412\u044b \u0443\u0436\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043b\u0438 \u044d\u0442\u043e\u0442 \u043f\u0440\u043e\u043c\u043e\u043a\u043e\u0434",
            reply_markup=back_main_kb(),
        )
        await state.clear()
        return

    await db.use_promo(message.from_user.id, promo["id"])

    text = f"\u2705 \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434 {code} \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d!\n\n"
    if promo["discount_percent"] > 0:
        text += f"\U0001f389 \u0421\u043a\u0438\u0434\u043a\u0430 {promo['discount_percent']}% \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0443\u044e \u043f\u043e\u043a\u0443\u043f\u043a\u0443!\n"
    if promo["bonus_days"] > 0:
        text += f"\U0001f381 +{promo['bonus_days']} \u0434\u043d\u0435\u0439 \u043a \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0435!\n"

    await message.answer(text, reply_markup=back_main_kb())
    await state.clear()


# --- Partner Program ---
@router.callback_query(F.data == "partner")
async def partner(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    ref_count = await db.get_referrals_count(callback.from_user.id)
    ref_percent = await db.get_setting("referral_percent", "10")
    bot_info = await callback.bot.get_me()

    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"

    text = (
        f"\U0001f91d \u041f\u0430\u0440\u0442\u043d\u0435\u0440\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430\n\n"
        f"\u041f\u0440\u0438\u0433\u043b\u0430\u0448\u0430\u0439\u0442\u0435 \u0434\u0440\u0443\u0437\u0435\u0439 \u0438 \u043f\u043e\u043b\u0443\u0447\u0430\u0439\u0442\u0435 {ref_percent}% \u0441 \u043a\u0430\u0436\u0434\u043e\u0439 \u0438\u0445 \u043f\u043e\u043a\u0443\u043f\u043a\u0438!\n\n"
        f"\U0001f517 \u0412\u0430\u0448\u0430 \u0441\u0441\u044b\u043b\u043a\u0430:\n<code>{ref_link}</code>\n\n"
        f"\U0001f465 \u041f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u043e: {ref_count}\n"
        f"\U0001f4b0 \u0417\u0430\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043e: {user['referral_earnings']:.0f} \u20bd"
    )
    await callback.message.edit_text(text, reply_markup=back_main_kb(), parse_mode="HTML")
    await callback.answer()


# --- Contests ---
@router.callback_query(F.data == "contests")
async def contests(callback: CallbackQuery):
    text = (
        "\U0001f3c6 \u041a\u043e\u043d\u043a\u0443\u0440\u0441\u044b\n\n"
        "\u041d\u0430 \u0434\u0430\u043d\u043d\u044b\u0439 \u043c\u043e\u043c\u0435\u043d\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043a\u043e\u043d\u043a\u0443\u0440\u0441\u043e\u0432 \u043d\u0435\u0442.\n"
        "\u0421\u043b\u0435\u0434\u0438\u0442\u0435 \u0437\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f\u043c\u0438!"
    )
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()


# --- Support ---
@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery, state: FSMContext):
    support_url = await db.get_setting("support_url")
    if support_url:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4ac \u041d\u0430\u043f\u0438\u0441\u0430\u0442\u044c \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443", url=support_url)],
            [InlineKeyboardButton(text="\u270d\ufe0f \u041e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435", callback_data="support_message")],
            [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_main")],
        ])
        await callback.message.edit_text(
            "\U0001f527 \u0422\u0435\u0445\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430",
            reply_markup=kb,
        )
    else:
        await callback.message.edit_text(
            "\U0001f527 \u0422\u0435\u0445\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430\n\n"
            "\u041e\u043f\u0438\u0448\u0438\u0442\u0435 \u0432\u0430\u0448\u0443 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0443:",
            reply_markup=back_main_kb(),
        )
        await state.set_state(SupportState.waiting_message)
    await callback.answer()


@router.callback_query(F.data == "support_message")
async def support_message_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "\U0001f527 \u041e\u043f\u0438\u0448\u0438\u0442\u0435 \u0432\u0430\u0448\u0443 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0443:",
        reply_markup=back_main_kb(),
    )
    await state.set_state(SupportState.waiting_message)
    await callback.answer()


@router.message(SupportState.waiting_message)
async def process_support(message: Message, state: FSMContext):
    await db.add_ticket(message.from_user.id, message.text)

    from bot.config import ADMIN_IDS
    user = await db.get_user(message.from_user.id)
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"\U0001f4e9 \u041d\u043e\u0432\u043e\u0435 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435 \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443\n\n"
                f"\U0001f464 {user['full_name']} (@{user['username']})\n"
                f"\U0001f4ac {message.text}",
            )
        except Exception:
            pass

    await message.answer(
        "\u2705 \u0412\u0430\u0448\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443!",
        reply_markup=back_main_kb(),
    )
    await state.clear()


# --- Info ---
@router.callback_query(F.data == "info")
async def info(callback: CallbackQuery):
    bot_name = await db.get_setting("bot_name", "VPN Bot")
    text = (
        f"\u2139\ufe0f {bot_name}\n\n"
        f"\u0421\u0435\u0440\u0432\u0438\u0441 \u0431\u044b\u0441\u0442\u0440\u043e\u0433\u043e \u0438 \u043d\u0430\u0434\u0435\u0436\u043d\u043e\u0433\u043e VPN.\n\n"
        f"\U0001f511 \u041f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0435 \u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b\u044b: VLESS, VMess\n"
        f"\U0001f4f1 \u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f: V2RayNG (Android), Streisand (iOS), V2RayN (Windows)\n\n"
        f"\u041f\u043e \u0432\u043e\u043f\u0440\u043e\u0441\u0430\u043c \u043e\u0431\u0440\u0430\u0449\u0430\u0439\u0442\u0435\u0441\u044c \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443."
    )
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()
