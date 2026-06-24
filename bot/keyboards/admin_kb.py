from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\U0001f5a5 \u0421\u0435\u0440\u0432\u0435\u0440\u0430", callback_data="admin_servers"),
            InlineKeyboardButton(text="\U0001f4b0 \u041e\u043f\u043b\u0430\u0442\u044b", callback_data="admin_payments"),
        ],
        [
            InlineKeyboardButton(text="\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438", callback_data="admin_users"),
            InlineKeyboardButton(text="\U0001f4e8 \u0420\u0430\u0441\u0441\u044b\u043b\u043a\u0430", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u043e\u0442\u0430", callback_data="admin_settings"),
            InlineKeyboardButton(text="\U0001f4cb \u0421\u043a\u0430\u0447\u0430\u0442\u044c \u043b\u043e\u0433\u0438", callback_data="admin_logs"),
        ],
        [
            InlineKeyboardButton(text="\U0001f3e0 \u041d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e", callback_data="back_main"),
        ],
    ])


def admin_servers_kb(servers: list) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        status = "\U0001f7e2" if s["is_active"] else "\U0001f534"
        flag = s["flag"] if s["flag"] else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {flag} {s['name']}",
                callback_data=f"admin_server_{s['id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="\U0001f504 \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c", callback_data="admin_servers"),
    ])
    buttons.append([
        InlineKeyboardButton(text="+ \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440", callback_data="admin_add_server"),
    ])
    buttons.append([
        InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_panel"),
        InlineKeyboardButton(text="\U0001f3e0 \u041d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e", callback_data="back_main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_server_detail_kb(server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\U0001f50c \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435", callback_data=f"admin_check_server_{server_id}"),
        ],
        [
            InlineKeyboardButton(text="\u23f8 \u0412\u043a\u043b/\u0412\u044b\u043a\u043b", callback_data=f"admin_toggle_server_{server_id}"),
            InlineKeyboardButton(text="\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c", callback_data=f"admin_delete_server_{server_id}"),
        ],
        [
            InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_servers"),
        ],
    ])


def admin_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4b0 \u0422\u0430\u0440\u0438\u0444\u044b", callback_data="admin_tariffs")],
        [InlineKeyboardButton(text="\u23f0 \u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434", callback_data="admin_test_settings")],
        [InlineKeyboardButton(text="\U0001f4b3 \u0420\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u044b \u043e\u043f\u043b\u0430\u0442\u044b", callback_data="admin_payment_settings")],
        [InlineKeyboardButton(text="\U0001f91d \u0420\u0435\u0444\u0435\u0440\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430", callback_data="admin_referral_settings")],
        [InlineKeyboardButton(text="\U0001f3ab \u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434\u044b", callback_data="admin_promos")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_panel")],
    ])


def admin_tariffs_kb(tariffs: list) -> InlineKeyboardMarkup:
    buttons = []
    for t in tariffs:
        status = "\u2705" if t["is_active"] else "\u274c"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {t['months']} \u043c\u0435\u0441. \u2014 {t['price']:.0f}\u20bd ({t['discount']}%)",
                callback_data=f"admin_tariff_{t['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="+ \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u0430\u0440\u0438\u0444", callback_data="admin_add_tariff")])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_settings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_tariff_detail_kb(tariff_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u270f\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0446\u0435\u043d\u0443", callback_data=f"admin_edit_tariff_price_{tariff_id}")],
        [InlineKeyboardButton(text="\U0001f4ca \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u043a\u0438\u0434\u043a\u0443", callback_data=f"admin_edit_tariff_discount_{tariff_id}")],
        [InlineKeyboardButton(text="\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c", callback_data=f"admin_delete_tariff_{tariff_id}")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_tariffs")],
    ])


def admin_promos_kb(promos: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in promos:
        status = "\u2705" if p["is_active"] else "\u274c"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {p['code']} ({p['used_count']}/{p['max_uses']})",
                callback_data=f"admin_promo_{p['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="+ \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043f\u0440\u043e\u043c\u043e\u043a\u043e\u0434", callback_data="admin_add_promo")])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="admin_settings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_payment_detail_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2705 \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c", callback_data=f"admin_confirm_payment_{payment_id}"),
            InlineKeyboardButton(text="\u274c \u041e\u0442\u043a\u043b\u043e\u043d\u0438\u0442\u044c", callback_data=f"admin_reject_payment_{payment_id}"),
        ],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="admin_cancel")],
    ])


def back_cancel_kb(back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data=back_callback),
            InlineKeyboardButton(text="\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="admin_cancel"),
        ],
    ])
