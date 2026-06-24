import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from bot.database import db
from bot.config import ADMIN_IDS
from bot.keyboards.user_kb import main_menu_kb
from bot.keyboards.admin_kb import admin_main_kb

router = Router()


async def _welcome_text(user_id: int) -> str:
    user = await db.get_user(user_id)
    has_sub = False
    subs = await db.get_user_subscriptions(user_id, active_only=True)
    if subs:
        has_sub = True

    sub_status = "\u2705 \u0410\u043a\u0442\u0438\u0432\u043d\u0430" if has_sub else "\u274c \u041d\u0435\u0442"
    balance = user["balance"] if user else 0

    text = (
        f"\U0001f464 \u041b\u0438\u0447\u043d\u044b\u0439 \u043a\u0430\u0431\u0438\u043d\u0435\u0442\n"
        f"\U0001f4cb \u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430: {sub_status}\n"
        f"\U0001f4b0 \u0411\u0430\u043b\u0430\u043d\u0441: {balance:.0f} \u20bd\n\n"
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435:"
    )
    return text


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    referrer_id = 0
    if message.text and len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = 0
        except ValueError:
            pass

    await db.add_user(user_id, username, full_name, referrer_id)

    welcome_image = await db.get_setting("welcome_image")
    text = await _welcome_text(user_id)

    if welcome_image:
        await message.answer_photo(
            photo=welcome_image,
            caption=text,
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(text, reply_markup=main_menu_kb())


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    text = await _welcome_text(callback.from_user.id)
    welcome_image = await db.get_setting("welcome_image")

    if welcome_image:
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=welcome_image,
                caption=text,
                reply_markup=main_menu_kb(),
            )
        except Exception:
            await callback.message.edit_text(text, reply_markup=main_menu_kb())
    else:
        try:
            await callback.message.edit_text(text, reply_markup=main_menu_kb())
        except Exception:
            await callback.message.answer(text, reply_markup=main_menu_kb())
    await callback.answer()


@router.message(F.text == "/admin")
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    users_count = await db.get_users_count()
    active_subs = await db.get_active_subscriptions_count()
    servers = await db.get_servers()
    revenue = await db.get_total_revenue()

    text = (
        f"\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c\n\n"
        f"\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: {users_count}\n"
        f"\U0001f4cb \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a: {active_subs}\n"
        f"\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u043e\u0432: {len(servers)}\n"
        f"\U0001f4b0 \u0414\u043e\u0445\u043e\u0434: {revenue:.0f} \u20bd"
    )
    await message.answer(text, reply_markup=admin_main_kb())


@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430", show_alert=True)
        return

    users_count = await db.get_users_count()
    active_subs = await db.get_active_subscriptions_count()
    servers = await db.get_servers()
    revenue = await db.get_total_revenue()

    text = (
        f"\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c\n\n"
        f"\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: {users_count}\n"
        f"\U0001f4cb \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a: {active_subs}\n"
        f"\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u043e\u0432: {len(servers)}\n"
        f"\U0001f4b0 \u0414\u043e\u0445\u043e\u0434: {revenue:.0f} \u20bd"
    )
    await callback.message.edit_text(text, reply_markup=admin_main_kb())
    await callback.answer()
