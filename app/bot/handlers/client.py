"""Client-facing handlers: /start, buy, my vpn, extend, referral, support, trial."""

from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import admin_kb, client_kb
from app.config.settings import settings
from app.database.database import async_session
from app.database.models import Payment, Setting, Subscription, Tariff, User
from app.services import payments as pay_svc
from app.database.models import PromoCode
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


async def _safe_edit_or_send(call: CallbackQuery, text: str, reply_markup=None) -> None:
    """Edit message or resend with logo. Logo always accompanies messages."""
    async with async_session() as session:
        logo_file_id = await _get_setting(session, "logo_file_id", "")

    msg = call.message  # type: ignore[union-attr]

    if logo_file_id:
        # Always show logo: try editing caption, else delete+send photo
        if msg.photo:
            try:
                await msg.edit_caption(caption=text, reply_markup=reply_markup)
                return
            except Exception:
                pass
        # Delete old message and send new photo
        try:
            await msg.delete()
        except Exception:
            pass
        await call.bot.send_photo(  # type: ignore[union-attr]
            call.from_user.id,  # type: ignore[union-attr]
            photo=logo_file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    else:
        # No logo — plain text
        try:
            await msg.edit_text(text, reply_markup=reply_markup)
        except Exception:
            try:
                await msg.delete()
            except Exception:
                pass
            await call.bot.send_message(  # type: ignore[union-attr]
                call.from_user.id, text, reply_markup=reply_markup  # type: ignore[union-attr]
            )


async def _can_use_trial(session: AsyncSession, user: User) -> bool:
    """Check if user never used trial before."""
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.tariff_id.is_(None),  # trial subscriptions have no tariff
        )
    )
    return result.scalar_one_or_none() is None


# ----------------------------------------------------------------- /start
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
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
        service_name = await _get_setting(session, "service_name", settings.service_name)
        logo_file_id = await _get_setting(session, "logo_file_id", "")
        trial_enabled = await _get_setting(session, "trial_enabled", "true")
        can_trial = trial_enabled == "true" and await _can_use_trial(session, user)
        channel_url = await _get_setting(session, "channel_url", "")

    text = greeting or f"🔥 <b>{html.escape(service_name)}</b>\n\nДобро пожаловать! Выберите действие:"
    kb = client_kb.main_menu_with_channel(has_trial=can_trial, channel_url=channel_url)

    if logo_file_id:
        await bot.send_photo(
            message.chat.id,
            photo=logo_file_id,
            caption=text,
            reply_markup=kb,
        )
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        service_name = await _get_setting(session, "service_name", settings.service_name)
        channel_url = await _get_setting(session, "channel_url", "")
        trial_enabled = await _get_setting(session, "trial_enabled", "true")
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        can_trial = (
            trial_enabled == "true" and user is not None and await _can_use_trial(session, user)
        )
    text = f"🔥 <b>{html.escape(service_name)}</b>\n\nВыберите действие:"
    kb = client_kb.main_menu_with_channel(has_trial=can_trial, channel_url=channel_url)
    await _safe_edit_or_send(call, text, reply_markup=kb)
    await call.answer()


# ----------------------------------------------------------------- Trial
@router.callback_query(F.data == "trial")
async def cb_trial(call: CallbackQuery, bot: Bot) -> None:
    async with async_session() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        if not user:
            await call.answer("Ошибка.", show_alert=True)
            return

        if not await _can_use_trial(session, user):
            await call.answer("Вы уже использовали пробный период.", show_alert=True)
            return

        trial_days_str = await _get_setting(session, "trial_days", "3")
        trial_days = int(trial_days_str) if trial_days_str.isdigit() else 3

        server = await select_best_server(session)
        if not server:
            await call.answer("Нет доступных серверов.", show_alert=True)
            return

        # Create a mock tariff-like object for VPN generation
        class TrialTariff:
            id = None  # None = no FK constraint (trial has no real tariff)
            name = "Пробный"
            days = trial_days
            devices = 1

        try:
            sub = await generate_vpn_key(session, user, TrialTariff(), server)  # type: ignore[arg-type]
            sub.tariff_id = None  # Mark as trial
            await session.commit()
        except Exception as exc:
            logger.error("Trial VPN generation failed: %s", exc)
            await call.answer("Ошибка создания ключа.", show_alert=True)
            return

    text = (
        f"🎁 <b>Пробный период активирован!</b>\n\n"
        f"Срок: {trial_days} дней\n"
        f"Устройств: 1\n\n"
        f"Ваш ключ:\n<code>{html.escape(sub.vless_link)}</code>"
    )
    try:
        await call.message.delete()  # type: ignore[union-attr]
    except Exception:
        pass
    await bot.send_message(
        call.from_user.id,  # type: ignore[union-attr]
        text,
        reply_markup=client_kb.back_main_kb(),
    )
    qr_buf = generate_qr(sub.vless_link)
    await bot.send_photo(
        call.from_user.id,  # type: ignore[union-attr]
        BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
        caption="📱 QR-код для подключения",
    )
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
    await _safe_edit_or_send(
        call, "🌍 <b>Выберите тариф:</b>", reply_markup=client_kb.tariffs_menu(tariffs)
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

        pay_method = await _get_setting(session, "payment_method", "both")
        has_yookassa = bool(settings.yookassa_shop_id)
        has_phone = bool(await _get_setting(session, "sbp_phone", ""))

    # Show payment method selection
    if pay_method == "both" and has_yookassa and has_phone:
        await _safe_edit_or_send(
            call,
            f"💳 <b>Выберите способ оплаты:</b>\n\n"
            f"Тариф: {html.escape(tariff.name)} — {int(tariff.price)}₽",
            reply_markup=client_kb.payment_method_select(tariff.id, has_yookassa, has_phone),
        )
    elif pay_method == "transfer" and has_phone:
        # Go directly to SBP transfer
        await _process_sbp_transfer(call, tariff)
    elif has_yookassa:
        # Go directly to card payment
        await _process_card_payment(call, tariff)
    elif has_phone:
        await _process_sbp_transfer(call, tariff)
    else:
        await call.answer("Способ оплаты не настроен. Обратитесь в поддержку.", show_alert=True)
        return
    await call.answer()


@router.callback_query(F.data.startswith("pay_card:"))
async def cb_pay_card(call: CallbackQuery) -> None:
    tariff_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        tariff = await session.get(Tariff, tariff_id)
        if not tariff:
            await call.answer("Не найден.", show_alert=True)
            return
    await _process_card_payment(call, tariff)
    await call.answer()


@router.callback_query(F.data.startswith("pay_sbp:"))
async def cb_pay_sbp(call: CallbackQuery) -> None:
    tariff_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        tariff = await session.get(Tariff, tariff_id)
        if not tariff:
            await call.answer("Не найден.", show_alert=True)
            return
    await _process_sbp_transfer(call, tariff)
    await call.answer()


async def _process_card_payment(call: CallbackQuery, tariff: Tariff) -> None:
    """Create ЮKassa payment and show pay button."""
    async with async_session() as session:
        try:
            meta = {"user_id": str(call.from_user.id), "tariff_id": str(tariff.id)}  # type: ignore[union-attr]
            result = await pay_svc.create_payment(
                amount=float(tariff.price),
                description=f"VPN: {tariff.name} ({tariff.days} дн.)",
                metadata=meta,
            )
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

            await _safe_edit_or_send(
                call,
                f"💳 <b>Оплата картой</b>\n\n"
                f"Тариф: {html.escape(tariff.name)}\n"
                f"Сумма: {int(tariff.price)}₽\n\n"
                f"Нажмите «Оплатить», затем «Проверить оплату».",
                reply_markup=client_kb.payment_kb(result.get("confirmation_url", ""), result["id"]),
            )
        except Exception as exc:
            logger.error("Card payment creation failed: %s", exc)
            await call.answer("Ошибка создания платежа.", show_alert=True)


async def _process_sbp_transfer(call: CallbackQuery, tariff: Tariff) -> None:
    """Show phone number for manual SBP transfer."""
    async with async_session() as session:
        phone = await _get_setting(session, "sbp_phone", "")
        if not phone:
            await call.answer("Номер для оплаты не настроен.", show_alert=True)
            return

        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        if not user:
            return

        pmt = Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            amount=float(tariff.price),
            status="pending",
            payment_id=f"sbp_{user.telegram_id}_{tariff.id}",
            provider="sbp_transfer",
        )
        session.add(pmt)
        await session.commit()
        await session.refresh(pmt)

    text = (
        f"📱 <b>Оплата переводом по СБП</b>\n\n"
        f"Тариф: {html.escape(tariff.name)}\n"
        f"Сумма: <b>{int(tariff.price)}₽</b>\n\n"
        f"Переведите на номер:\n"
        f"<code>{html.escape(phone)}</code>\n\n"
        f"После перевода нажмите «Я оплатил»."
    )
    await _safe_edit_or_send(call, text, reply_markup=client_kb.sbp_transfer_kb(pmt.id))


@router.callback_query(F.data.startswith("sbp_paid:"))
async def cb_sbp_paid(call: CallbackQuery, bot: Bot) -> None:
    """Client pressed 'I paid' — notify admin."""
    pmt_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    async with async_session() as session:
        pmt = await session.get(Payment, pmt_id)
        if not pmt:
            await call.answer("Платёж не найден.", show_alert=True)
            return
        if pmt.status == "paid":
            await call.answer("Уже подтверждён!", show_alert=True)
            return
        pmt.status = "awaiting_confirmation"
        user = await session.get(User, pmt.user_id)
        tariff = await session.get(Tariff, pmt.tariff_id) if pmt.tariff_id else None
        await session.commit()

    # Notify admins
    username = f"@{user.username}" if user and user.username else f"ID:{user.telegram_id}" if user else "?"
    tariff_name = tariff.name if tariff else "?"
    amount = int(pmt.amount)

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Новый перевод по СБП!</b>\n\n"
                f"Пользователь: {html.escape(username)}\n"
                f"Тариф: {html.escape(tariff_name)}\n"
                f"Сумма: {amount}₽\n\n"
                f"Подтвердить оплату?",
                reply_markup=admin_kb.sbp_confirm_kb(pmt.id),
            )
        except Exception:
            pass

    await _safe_edit_or_send(
        call,
        "⏳ <b>Ожидание подтверждения</b>\n\n"
        "Ваш перевод отправлен на проверку. "
        "Как только администратор подтвердит — вы получите VPN-ключ.",
        reply_markup=client_kb.back_main_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("check_pay:"))
async def cb_check_payment(call: CallbackQuery, bot: Bot) -> None:
    payment_id = call.data.split(":", 1)[1]  # type: ignore[union-attr]
    async with async_session() as session:
        status = await pay_svc.check_payment(payment_id)
        if status != "succeeded":
            await call.answer("⏳ Оплата ещё не подтверждена. Подождите.", show_alert=True)
            return

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

        server = await select_best_server(session)
        if not server:
            await call.answer("Нет доступных серверов.", show_alert=True)
            return

        try:
            sub = await generate_vpn_key(session, user, tariff, server)
        except Exception as exc:
            logger.error("VPN generation failed: %s", exc)
            await call.answer("Ошибка создания ключа.", show_alert=True)
            return

        await session.commit()

        text = (
            f"✅ <b>VPN активирован!</b>\n\n"
            f"Срок: {tariff.days} дней\n"
            f"Устройств: {tariff.devices}\n\n"
            f"Ваш ключ:\n<code>{html.escape(sub.vless_link)}</code>"
        )
        await bot.send_message(
            call.from_user.id, text,  # type: ignore[union-attr]
            reply_markup=client_kb.back_main_kb(),
        )
        qr_buf = generate_qr(sub.vless_link)
        await bot.send_photo(
            call.from_user.id,  # type: ignore[union-attr]
            BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
            caption="📱 QR-код для подключения",
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

    await _safe_edit_or_send(call, text, reply_markup=client_kb.back_main_kb())
    await call.answer()


# ----------------------------------------------------------------- Extend
@router.callback_query(F.data == "extend_vpn")
async def cb_extend_vpn(call: CallbackQuery) -> None:
    async with async_session() as session:
        # Ищем активные подписки пользователя
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        if not user:
            await call.answer("Ошибка.", show_alert=True)
            return

        subs_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.is_active.is_(True),
                Subscription.tariff_id.isnot(None),
            )
        )
        active_subs = list(subs_res.scalars().all())

        if not active_subs:
            await _safe_edit_or_send(
                call,
                "💳 <b>Продление VPN</b>\n\n"
                "У вас нет активных платных подписок для продления.\n"
                "Нажмите «Купить VPN» чтобы приобрести подписку.",
                reply_markup=client_kb.buy_or_back_kb(),
            )
            await call.answer()
            return

        # Собираем тарифы активных подписок
        tariff_ids = list({s.tariff_id for s in active_subs if s.tariff_id})
        tariffs_res = await session.execute(
            select(Tariff).where(Tariff.id.in_(tariff_ids), Tariff.is_active.is_(True))
        )
        active_tariffs = list(tariffs_res.scalars().all())

        # Также все доступные тарифы для выбора другого
        all_tariffs_res = await session.execute(
            select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort_order)
        )
        all_tariffs = list(all_tariffs_res.scalars().all())

        # Формируем текст с активными подписками
        lines = ["💳 <b>Продление VPN</b>\n\n<b>Ваши активные подписки:</b>"]
        for sub in active_subs:
            tariff = next((t for t in active_tariffs if t.id == sub.tariff_id), None)
            tariff_name = tariff.name if tariff else "Неизвестный тариф"
            expire_str = sub.expire_date.strftime("%d.%m.%Y")
            lines.append(f"🔑 {tariff_name} — до {expire_str}")

        lines.append("\n<b>Выберите тариф для продления:</b>")
        text = "\n".join(lines)

    await _safe_edit_or_send(
        call,
        text,
        reply_markup=client_kb.tariffs_menu_extend(all_tariffs),
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
    await _safe_edit_or_send(call, text, reply_markup=client_kb.back_main_kb())
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

    text = (
        f"⭐ <b>Бонусы</b>\n\n"
        f"Накоплено бонусных дней: <b>{bonus}</b>\n\n"
    )
    if bonus > 0:
        text += "Нажмите «Активировать» чтобы получить VPN-ключ бесплатно!"
    else:
        text += "Приглашайте друзей чтобы получить бонусные дни!"
    await _safe_edit_or_send(call, text, reply_markup=client_kb.bonuses_kb(bonus))
    await call.answer()


@router.callback_query(F.data == "activate_bonus")
async def cb_activate_bonus(call: CallbackQuery, bot: Bot) -> None:
    """Activate bonus days — generate VPN key for free."""
    async with async_session() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        if not user or user.bonus_days <= 0:
            await call.answer("Нет доступных бонусных дней.", show_alert=True)
            return

        server = await select_best_server(session)
        if not server:
            await call.answer("Нет доступных серверов.", show_alert=True)
            return

        bonus_days = user.bonus_days

        class BonusTariff:
            id = None
            name = "Бонус"
            days = bonus_days
            devices = 1

        try:
            sub = await generate_vpn_key(session, user, BonusTariff(), server)  # type: ignore[arg-type]
            sub.tariff_id = None
            user.bonus_days = 0  # Reset bonus after activation
            await session.commit()
        except Exception as exc:
            logger.error("Bonus VPN generation failed: %s", exc)
            await call.answer("Ошибка создания ключа.", show_alert=True)
            return

    text = (
        f"🎁 <b>Бонус активирован!</b>\n\n"
        f"Срок: {bonus_days} дней\n"
        f"Устройств: 1\n\n"
        f"Ваш ключ:\n<code>{html.escape(sub.vless_link)}</code>"
    )
    try:
        await call.message.delete()  # type: ignore[union-attr]
    except Exception:
        pass
    await bot.send_message(
        call.from_user.id,  # type: ignore[union-attr]
        text,
        reply_markup=client_kb.back_main_kb(),
    )
    qr_buf = generate_qr(sub.vless_link)
    await bot.send_photo(
        call.from_user.id,  # type: ignore[union-attr]
        BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
        caption="📱 QR-код для подключения",
    )
    await call.answer()


# ----------------------------------------------------------------- Промокод
@router.callback_query(F.data == "enter_promo")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext) -> None:
    from aiogram.fsm.state import State, StatesGroup

    class PromoState(StatesGroup):
        waiting = State()

    await state.set_state("promo_waiting")
    await _safe_edit_or_send(
        call,
        "🏷 <b>Введите промокод:</b>",
        reply_markup=client_kb.back_main_kb(),
    )
    await call.answer()


@router.message(F.text)
async def handle_promo_input(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current != "promo_waiting":
        return
    await state.clear()

    code = message.text.strip().upper() if message.text else ""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True))
        )
        promo = result.scalar_one_or_none()

        if not promo:
            await message.answer(
                "❌ Промокод не найден или уже не действует.",
                reply_markup=client_kb.back_main_kb(),
            )
            return

        if promo.used_count >= promo.max_uses:
            await message.answer(
                "❌ Промокод исчерпан.",
                reply_markup=client_kb.back_main_kb(),
            )
            return

        # Применяем промокод
        user_res = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)  # type: ignore
        )
        user = user_res.scalar_one_or_none()
        if not user:
            await message.answer("Ошибка.")
            return

        promo.used_count += 1
        if promo.used_count >= promo.max_uses:
            promo.is_active = False

        has_bonus = False
        lines = ["✅ <b>Промокод активирован!</b>\n"]
        if promo.discount_percent:
            lines.append(f"💳 Скидка {promo.discount_percent}% на следующую покупку")
            # Сохраняем скидку в настройках пользователя
            await _get_setting(session, f"promo_discount_{user.telegram_id}", "")
            from app.database.models import Setting
            disc_key = f"promo_discount_{user.telegram_id}"
            disc_res = await session.execute(select(Setting).where(Setting.key == disc_key))
            disc_row = disc_res.scalar_one_or_none()
            if disc_row:
                disc_row.value = str(promo.discount_percent)
            else:
                session.add(Setting(key=disc_key, value=str(promo.discount_percent)))

        if promo.bonus_days:
            user.bonus_days += promo.bonus_days
            lines.append(f"⭐ +{promo.bonus_days} бонусных дней")
            has_bonus = True

        await session.commit()

    await message.answer(
        "\n".join(lines),
        reply_markup=client_kb.promo_result_kb(has_bonus=has_bonus),
    )


# ----------------------------------------------------------------- Инструкция
@router.callback_query(F.data == "instruction")
async def cb_instruction_client(call: CallbackQuery) -> None:
    async with async_session() as session:
        text = await _get_setting(session, "connect_instruction", "")

    if not text:
        text = (
            "📝 <b>Инструкция по подключению</b>\n\n"
            "1️⃣ Скачайте приложение:\n"
            "   • iOS: <b>FoXray</b> или <b>Streisand</b>\n"
            "   • Android: <b>v2rayNG</b> или <b>NekoBox</b>\n"
            "   • Windows/Mac: <b>Hiddify</b>\n\n"
            "2️⃣ Скопируйте ваш VLESS-ключ из раздела «Мой VPN»\n\n"
            "3️⃣ Вставьте ключ в приложение и подключитесь\n\n"
            "❓ Если возникли проблемы — обратитесь в поддержку"
        )

    await _safe_edit_or_send(call, text, reply_markup=client_kb.back_main_kb())
    await call.answer()


# ----------------------------------------------------------------- Profile (Личный кабинет)
@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery) -> None:
    async with async_session() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == call.from_user.id)  # type: ignore[union-attr]
        )
        user = user_res.scalar_one_or_none()
        if not user:
            await call.answer("Ошибка.", show_alert=True)
            return

        # Активные подписки
        subs_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user.id, Subscription.is_active.is_(True)
            )
        )
        active_subs = list(subs_res.scalars().all())

        # Все подписки (для истории)
        all_subs_res = await session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        all_subs = list(all_subs_res.scalars().all())

        # Рефералы
        ref_count = await get_referral_count(session, user)

        # Пробный период использован?
        trial_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.tariff_id.is_(None),
            )
        )
        used_trial = trial_res.scalar_one_or_none() is not None

    username_str = f"@{user.username}" if user.username else "—"
    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"

    # Ближайшая дата истечения
    if active_subs:
        nearest_expire = min(s.expire_date for s in active_subs)
        expire_str = nearest_expire.strftime("%d.%m.%Y")
    else:
        expire_str = "нет активных"

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🆔 Ваш ID: <code>{user.telegram_id}</code>\n"
        f"👤 Имя: {html.escape(user.full_name or '—')}\n"
        f"📱 Username: {html.escape(username_str)}\n"
        f"📅 Дата регистрации: {reg_date}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Активных подписок: <b>{len(active_subs)}</b>\n"
        f"📦 Всего подписок: <b>{len(all_subs)}</b>\n"
        f"📆 Ближайшее истечение: <b>{expire_str}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Приглашено друзей: <b>{ref_count}</b>\n"
        f"⭐ Бонусных дней: <b>{user.bonus_days}</b>\n"
        f"🎁 Пробный период: {'✅ использован' if used_trial else '❌ не использован'}\n"
    )

    await _safe_edit_or_send(call, text, reply_markup=client_kb.back_main_kb())
    await call.answer()


# ----------------------------------------------------------------- Support
@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery) -> None:
    async with async_session() as session:
        support = await _get_setting(session, "support_username", settings.support_username)
    text = f"🆘 <b>Поддержка</b>\n\nНапишите: {html.escape(support)}"
    await _safe_edit_or_send(call, text, reply_markup=client_kb.back_main_kb())
    await call.answer()
