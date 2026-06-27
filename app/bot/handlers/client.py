"""Client-facing handlers: /start, buy, my vpn, extend, referral, support."""

from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import client_kb
from app.config.settings import settings
from app.database.database import async_session
from app.database.models import Payment, Setting, Subscription, Tariff, User
from app.services import payments as pay_svc
from app.services.referral import get_referral_count, get_referral_link, register_referral
from app.services.vpn_generator import generate_qr, generate_vpn_key, select_best_server

logger = logging.getLogger(__name__)
router = Router(name="client")


async def _get_or_create_user(session: AsyncSession, message: Message) -> User:
    tg_id = message.from_user.id  # type: ignore[union-attr]
    result = await session.execute(select(User).where(User.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            telegram_id=tg_id,
            username=message.from_user.username or "",  # type: ignore[union-attr]
            full_name=message.from_user.full_name or "",  # type: ignore[union-attr]
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def _get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


# ----------------------------------------------------------------- /start
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        user = await _get_or_create_user(session, message)

        # Handle referral
        args = message.text.split() if message.text else []
        if len(args) > 1 and args[1].startswith("ref"):
            try:
                referrer_tg_id = int(args[1][3:])
                if referrer_tg_id != user.telegram_id:
                    await register_referral(session, referrer_tg_id, user.telegram_id)
            except (ValueError, TypeError):
                pass

        greeting = await _get_setting(session, "greeting", "")

    service_name = settings.service_name
    text = greeting or f"🔥 <b>{html.escape(service_name)}</b>\n\nДобро пожаловать! Выберите действие:"
    await message.answer(text, reply_markup=client_kb.main_menu())


@router.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = f"🔥 <b>{html.escape(settings.service_name)}</b>\n\nВыберите действие:"
    await call.message.edit_text(text, reply_markup=client_kb.main_menu())  # type: ignore[union-attr]
    await call.answer()


# ----------------------------------------------------------------- Buy VPN
@router.callback_query(F.data == "buy_vpn")
async def cb_buy_vpn(call: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort_order)
        )
        tariffs = list(result.scalars().all())

    if not tariffs:
        await call.answer("Тарифы ещё не настроены.", show_alert=True)
        return
    await call.message.edit_text(  # type: ignore[union-attr]
        "🌍 <b>Выберите тариф:</b>", reply_markup=client_kb.tariffs_menu(tariffs)
    )
    await call.answer()


@router.callback_query(F.data.startswith("tariff:"))
async def cb_select_tariff(call: CallbackQuery) -> None:
    tariff_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        tariff = await session.get(Tariff, tariff_id)
        if not tariff:
            await call.answer("Тариф не найден.", show_alert=True)
            return

        # Create payment
        try:
            meta = {"user_id": str(call.from_user.id), "tariff_id": str(tariff.id)}  # type: ignore[union-attr]
            result = await pay_svc.create_payment(
                amount=float(tariff.price),
                description=f"VPN: {tariff.name} ({tariff.days} дн.)",
                metadata=meta,
            )
            # Save pending payment
            user_res = await session.execute(
                select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
            )
            user = user_res.scalar_one_or_none()
            if user:
                pmt = Payment(
                    user_id=user.id,
                    tariff_id=tariff.id,
                    amount=float(tariff.price),
                    status="pending",
                    payment_id=result["id"],
                    provider="yookassa",
                )
                session.add(pmt)
                await session.commit()

            await call.message.edit_text(  # type: ignore[union-attr]
                f"💳 <b>Оплата</b>\n\n"
                f"Тариф: {html.escape(tariff.name)}\n"
                f"Сумма: {int(tariff.price)}₽\n\n"
                f"Нажмите «Оплатить», затем «Проверить оплату».",
                reply_markup=client_kb.payment_kb(result["confirmation_url"], result["id"]),
            )
        except Exception as exc:
            logger.error("Payment creation failed: %s", exc)
            await call.answer("Ошибка создания платежа. Попробуйте позже.", show_alert=True)
            return
    await call.answer()


@router.callback_query(F.data.startswith("check_pay:"))
async def cb_check_payment(call: CallbackQuery, bot: Bot) -> None:
    payment_id = call.data.split(":", 1)[1]  # type: ignore[union-attr]
    async with async_session() as session:
        status = await pay_svc.check_payment(payment_id)
        if status != "succeeded":
            await call.answer("⏳ Оплата ещё не подтверждена. Подождите.", show_alert=True)
            return

        # Mark payment as paid
        pmt_res = await session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        pmt = pmt_res.scalar_one_or_none()
        if not pmt or pmt.status == "paid":
            await call.answer("Платёж уже обработан.", show_alert=True)
            return
        pmt.status = "paid"

        user = await session.get(User, pmt.user_id)
        tariff = await session.get(Tariff, pmt.tariff_id) if pmt.tariff_id else None
        if not user or not tariff:
            await call.answer("Ошибка данных.", show_alert=True)
            return

        # Generate VPN key
        server = await select_best_server(session)
        if not server:
            await call.answer("Нет доступных серверов. Обратитесь в поддержку.", show_alert=True)
            return

        try:
            sub = await generate_vpn_key(session, user, tariff, server)
        except Exception as exc:
            logger.error("VPN generation failed: %s", exc)
            await call.answer("Ошибка создания ключа. Обратитесь в поддержку.", show_alert=True)
            return

        await session.commit()

        # Send key + QR
        text = (
            f"✅ <b>VPN активирован!</b>\n\n"
            f"Срок: {tariff.days} дней\n"
            f"Устройств: {tariff.devices}\n\n"
            f"Ваш ключ:\n<code>{html.escape(sub.vless_link)}</code>"
        )
        await call.message.edit_text(text, reply_markup=client_kb.back_main_kb())  # type: ignore[union-attr]

        qr_buf = generate_qr(sub.vless_link)
        await bot.send_photo(
            call.from_user.id,  # type: ignore[union-attr]
            BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
            caption="📱 QR-код для быстрого подключения",
        )
    await call.answer()


# ----------------------------------------------------------------- My VPN
@router.callback_query(F.data == "my_vpn")
async def cb_my_vpn(call: CallbackQuery) -> None:
    async with async_session() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        if not user:
            await call.answer("Нет данных.", show_alert=True)
            return

        subs_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user.id, Subscription.is_active.is_(True)
            )
        )
        subs = list(subs_res.scalars().all())

    if not subs:
        text = "🔑 У вас нет активных VPN подключений."
    else:
        lines = ["🔑 <b>Ваши VPN:</b>\n"]
        for s in subs:
            lines.append(
                f"• До {s.expire_date.strftime('%d.%m.%Y')}\n"
                f"  <code>{html.escape(s.vless_link[:60])}...</code>\n"
            )
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=client_kb.back_main_kb())  # type: ignore[union-attr]
    await call.answer()


# ----------------------------------------------------------------- Extend
@router.callback_query(F.data == "extend_vpn")
async def cb_extend_vpn(call: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort_order)
        )
        tariffs = list(result.scalars().all())

    if not tariffs:
        await call.answer("Тарифы не настроены.", show_alert=True)
        return
    await call.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Продление VPN — выберите тариф:</b>",
        reply_markup=client_kb.tariffs_menu(tariffs),
    )
    await call.answer()


# ----------------------------------------------------------------- Referral
@router.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery, bot: Bot) -> None:
    bot_info = await bot.get_me()
    link = await get_referral_link(bot_info.username or "", call.from_user.id)  # type: ignore[union-attr]

    async with async_session() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        count = await get_referral_count(session, user) if user else 0

    text = (
        f"🎁 <b>Пригласить друга</b>\n\n"
        f"Ваша ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено: {count}\n\n"
        f"🎯 3 друга = 7 дней VPN бесплатно\n"
        f"🎯 10 друзей = 30 дней VPN бесплатно"
    )
    await call.message.edit_text(text, reply_markup=client_kb.back_main_kb())  # type: ignore[union-attr]
    await call.answer()


# ----------------------------------------------------------------- Bonuses
@router.callback_query(F.data == "bonuses")
async def cb_bonuses(call: CallbackQuery) -> None:
    async with async_session() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        bonus = user.bonus_days if user else 0

    text = f"⭐ <b>Бонусы</b>\n\nНакоплено бонусных дней: {bonus}"
    await call.message.edit_text(text, reply_markup=client_kb.back_main_kb())  # type: ignore[union-attr]
    await call.answer()


# ----------------------------------------------------------------- Support
@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery) -> None:
    async with async_session() as session:
        support = await _get_setting(session, "support_username", settings.support_username)
    text = f"🆘 <b>Поддержка</b>\n\nНапишите: {html.escape(support)}"
    await call.message.edit_text(text, reply_markup=client_kb.back_main_kb())  # type: ignore[union-attr]
    await call.answer()
