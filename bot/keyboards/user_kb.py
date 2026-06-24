from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2b07 \u0422\u0435\u0441\u0442\u043e\u0432\u0430\u044f", callback_data="test_period"),
            InlineKeyboardButton(text="\U0001f48e \u041a\u0443\u043f\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443", callback_data="buy_subscription"),
        ],
        [
            InlineKeyboardButton(text="\U0001f4b3 \u041f\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u044c (\u0421\u0411\u041f)", callback_data="topup_balance"),
            InlineKeyboardButton(text="\U0001f3ab \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434", callback_data="promo_code"),
        ],
        [
            InlineKeyboardButton(text="\U0001f91d \u041f\u0430\u0440\u0442\u043d\u0435\u0440\u043a\u0430", callback_data="partner"),
            InlineKeyboardButton(text="\U0001f3c6 \u041a\u043e\u043d\u043a\u0443\u0440\u0441\u044b", callback_data="contests"),
        ],
        [
            InlineKeyboardButton(text="\U0001f527 \u0422\u0435\u0445\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430", callback_data="support"),
            InlineKeyboardButton(text="\u2139\ufe0f \u0418\u043d\u0444\u043e", callback_data="info"),
        ],
        [
            InlineKeyboardButton(text="\U0001f464 \u041b\u0438\u0447\u043d\u044b\u0439 \u043a\u0430\u0431\u0438\u043d\u0435\u0442", callback_data="cabinet"),
        ],
    ])


def tariff_kb(tariffs: list) -> InlineKeyboardMarkup:
    buttons = []
    icons = {1: "", 3: "", 6: "\u26a1", 12: "\U0001f525"}
    for t in tariffs:
        months = t["months"]
        discount = t["discount"]
        icon = icons.get(months, "")
        if discount > 0:
            label = f"{icon} {months} \u043c\u0435\u0441\u044f\u0446\u0435\u0432 \u2022 -{discount}%".strip()
        else:
            label = f"{months} \u043c\u0435\u0441\u044f\u0446"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"tariff_{t['id']}")])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def devices_kb(tariff_id: int, base_price: float) -> InlineKeyboardMarkup:
    buttons = []
    for i in range(1, 11, 2):
        row = []
        for j in (i, i + 1):
            if j <= 10:
                row.append(
                    InlineKeyboardButton(
                        text=f"{j} \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432",
                        callback_data=f"devices_{tariff_id}_{j}",
                    )
                )
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text=f"\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c {base_price:.0f} \u20bd",
            callback_data=f"pay_{tariff_id}_1",
        )
    ])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="buy_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def server_select_kb(servers: list, prefix: str = "select_server") -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        flag = s["flag"] if s["flag"] else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"\U0001f7e2 {flag} {s['name']}",
                callback_data=f"{prefix}_{s['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_confirm_kb(amount: float, tariff_id: int, devices: int, server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"\u2705 \u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c {amount:.0f} \u20bd \u0441 \u0431\u0430\u043b\u0430\u043d\u0441\u0430",
            callback_data=f"confirm_pay_{tariff_id}_{devices}_{server_id}",
        )],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="buy_subscription")],
    ])


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_main")],
    ])


def cabinet_kb(has_subs: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if has_subs:
        buttons.append([InlineKeyboardButton(text="\U0001f511 \u041c\u043e\u0438 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438", callback_data="my_subscriptions")])
    buttons.append([InlineKeyboardButton(text="\U0001f4b3 \u041f\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0431\u0430\u043b\u0430\u043d\u0441", callback_data="topup_balance")])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topup_amounts_kb() -> InlineKeyboardMarkup:
    amounts = [100, 200, 500, 1000, 2000, 5000]
    buttons = []
    for i in range(0, len(amounts), 2):
        row = []
        for j in range(i, min(i + 2, len(amounts))):
            row.append(
                InlineKeyboardButton(
                    text=f"{amounts[j]} \u20bd",
                    callback_data=f"topup_{amounts[j]}",
                )
            )
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
