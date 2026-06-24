import aiosqlite
import os
import time
from bot.config import DB_PATH


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._conn = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def _create_tables(self):
        await self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            full_name TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            referral_earnings REAL DEFAULT 0,
            language TEXT DEFAULT 'ru',
            created_at REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            flag TEXT DEFAULT '',
            panel_url TEXT NOT NULL,
            login TEXT NOT NULL,
            password TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            months INTEGER NOT NULL,
            price REAL NOT NULL,
            discount INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            server_id INTEGER NOT NULL,
            tariff_id INTEGER NOT NULL,
            devices INTEGER DEFAULT 1,
            vpn_key TEXT DEFAULT '',
            client_email TEXT DEFAULT '',
            inbound_id INTEGER DEFAULT 0,
            expires_at REAL DEFAULT 0,
            created_at REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (server_id) REFERENCES servers(id),
            FOREIGN KEY (tariff_id) REFERENCES tariffs(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_type TEXT DEFAULT 'balance',
            status TEXT DEFAULT 'pending',
            created_at REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_percent INTEGER DEFAULT 0,
            bonus_days INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            promo_id INTEGER NOT NULL,
            used_at REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (promo_id) REFERENCES promo_codes(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """)
        await self._conn.commit()
        await self._insert_default_settings()
        await self._insert_default_tariffs()

    async def _insert_default_settings(self):
        defaults = {
            "test_period_hours": "24",
            "test_devices": "1",
            "device_price_multiplier": "1.0",
            "referral_percent": "10",
            "bot_name": "VPN Bot",
            "support_url": "",
            "payment_instructions": "Переведите сумму по СБП и отправьте скриншот",
            "sbp_phone": "",
            "sbp_bank": "",
            "welcome_image": "",
            "subscription_image": "",
        }
        for key, value in defaults.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await self._conn.commit()

    async def _insert_default_tariffs(self):
        cur = await self._conn.execute("SELECT COUNT(*) FROM tariffs")
        row = await cur.fetchone()
        if row[0] == 0:
            tariffs = [
                (1, 159, 0),
                (3, 429, 10),
                (6, 811, 15),
                (12, 1335, 30),
            ]
            for months, price, discount in tariffs:
                await self._conn.execute(
                    "INSERT INTO tariffs (months, price, discount) VALUES (?, ?, ?)",
                    (months, price, discount),
                )
            await self._conn.commit()

    # --- Users ---
    async def add_user(self, user_id: int, username: str, full_name: str, referrer_id: int = 0):
        await self._conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, referrer_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, full_name, referrer_id, time.time()),
        )
        await self._conn.commit()

    async def get_user(self, user_id: int):
        cur = await self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cur.fetchone()

    async def update_balance(self, user_id: int, amount: float):
        await self._conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await self._conn.commit()

    async def set_balance(self, user_id: int, amount: float):
        await self._conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (amount, user_id),
        )
        await self._conn.commit()

    async def get_all_users(self):
        cur = await self._conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        return await cur.fetchall()

    async def get_users_count(self):
        cur = await self._conn.execute("SELECT COUNT(*) FROM users")
        row = await cur.fetchone()
        return row[0]

    async def add_referral_earnings(self, user_id: int, amount: float):
        await self._conn.execute(
            "UPDATE users SET referral_earnings = referral_earnings + ?, balance = balance + ? WHERE user_id = ?",
            (amount, amount, user_id),
        )
        await self._conn.commit()

    async def get_referrals_count(self, user_id: int):
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row[0]

    # --- Servers ---
    async def add_server(self, name: str, flag: str, panel_url: str, login: str, password: str):
        await self._conn.execute(
            "INSERT INTO servers (name, flag, panel_url, login, password, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, flag, panel_url, login, password, time.time()),
        )
        await self._conn.commit()

    async def get_servers(self, active_only: bool = False):
        if active_only:
            cur = await self._conn.execute("SELECT * FROM servers WHERE is_active = 1")
        else:
            cur = await self._conn.execute("SELECT * FROM servers")
        return await cur.fetchall()

    async def get_server(self, server_id: int):
        cur = await self._conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
        return await cur.fetchone()

    async def delete_server(self, server_id: int):
        await self._conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await self._conn.commit()

    async def toggle_server(self, server_id: int):
        await self._conn.execute(
            "UPDATE servers SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (server_id,),
        )
        await self._conn.commit()

    # --- Tariffs ---
    async def get_tariffs(self, active_only: bool = False):
        if active_only:
            cur = await self._conn.execute("SELECT * FROM tariffs WHERE is_active = 1 ORDER BY months")
        else:
            cur = await self._conn.execute("SELECT * FROM tariffs ORDER BY months")
        return await cur.fetchall()

    async def get_tariff(self, tariff_id: int):
        cur = await self._conn.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,))
        return await cur.fetchone()

    async def update_tariff(self, tariff_id: int, price: float, discount: int):
        await self._conn.execute(
            "UPDATE tariffs SET price = ?, discount = ? WHERE id = ?",
            (price, discount, tariff_id),
        )
        await self._conn.commit()

    async def add_tariff(self, months: int, price: float, discount: int):
        await self._conn.execute(
            "INSERT INTO tariffs (months, price, discount) VALUES (?, ?, ?)",
            (months, price, discount),
        )
        await self._conn.commit()

    async def delete_tariff(self, tariff_id: int):
        await self._conn.execute("DELETE FROM tariffs WHERE id = ?", (tariff_id,))
        await self._conn.commit()

    # --- Subscriptions ---
    async def add_subscription(
        self,
        user_id: int,
        server_id: int,
        tariff_id: int,
        devices: int,
        vpn_key: str,
        client_email: str,
        inbound_id: int,
        expires_at: float,
    ):
        await self._conn.execute(
            "INSERT INTO subscriptions "
            "(user_id, server_id, tariff_id, devices, vpn_key, client_email, inbound_id, expires_at, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (user_id, server_id, tariff_id, devices, vpn_key, client_email, inbound_id, expires_at, time.time()),
        )
        await self._conn.commit()

    async def get_user_subscriptions(self, user_id: int, active_only: bool = False):
        if active_only:
            cur = await self._conn.execute(
                "SELECT s.*, srv.name as server_name, srv.flag as server_flag "
                "FROM subscriptions s JOIN servers srv ON s.server_id = srv.id "
                "WHERE s.user_id = ? AND s.is_active = 1 AND s.expires_at > ? "
                "ORDER BY s.created_at DESC",
                (user_id, time.time()),
            )
        else:
            cur = await self._conn.execute(
                "SELECT s.*, srv.name as server_name, srv.flag as server_flag "
                "FROM subscriptions s JOIN servers srv ON s.server_id = srv.id "
                "WHERE s.user_id = ? ORDER BY s.created_at DESC",
                (user_id,),
            )
        return await cur.fetchall()

    async def deactivate_subscription(self, sub_id: int):
        await self._conn.execute(
            "UPDATE subscriptions SET is_active = 0 WHERE id = ?", (sub_id,)
        )
        await self._conn.commit()

    async def get_active_subscriptions_count(self):
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE is_active = 1 AND expires_at > ?",
            (time.time(),),
        )
        row = await cur.fetchone()
        return row[0]

    # --- Payments ---
    async def add_payment(self, user_id: int, amount: float, payment_type: str = "balance"):
        await self._conn.execute(
            "INSERT INTO payments (user_id, amount, payment_type, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (user_id, amount, payment_type, time.time()),
        )
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid()")
        row = await cur.fetchone()
        return row[0]

    async def confirm_payment(self, payment_id: int):
        await self._conn.execute(
            "UPDATE payments SET status = 'confirmed' WHERE id = ?", (payment_id,)
        )
        await self._conn.commit()

    async def get_payment(self, payment_id: int):
        cur = await self._conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
        return await cur.fetchone()

    async def get_pending_payments(self):
        cur = await self._conn.execute(
            "SELECT p.*, u.username, u.full_name FROM payments p "
            "JOIN users u ON p.user_id = u.user_id "
            "WHERE p.status = 'pending' ORDER BY p.created_at DESC"
        )
        return await cur.fetchall()

    async def reject_payment(self, payment_id: int):
        await self._conn.execute(
            "UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,)
        )
        await self._conn.commit()

    async def get_total_revenue(self):
        cur = await self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'confirmed'"
        )
        row = await cur.fetchone()
        return row[0]

    # --- Promo Codes ---
    async def add_promo(self, code: str, discount_percent: int, bonus_days: int, max_uses: int):
        await self._conn.execute(
            "INSERT INTO promo_codes (code, discount_percent, bonus_days, max_uses, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (code.upper(), discount_percent, bonus_days, max_uses, time.time()),
        )
        await self._conn.commit()

    async def get_promo_by_code(self, code: str):
        cur = await self._conn.execute(
            "SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (code.upper(),)
        )
        return await cur.fetchone()

    async def use_promo(self, user_id: int, promo_id: int):
        await self._conn.execute(
            "INSERT INTO promo_uses (user_id, promo_id, used_at) VALUES (?, ?, ?)",
            (user_id, promo_id, time.time()),
        )
        await self._conn.execute(
            "UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", (promo_id,)
        )
        await self._conn.commit()

    async def has_used_promo(self, user_id: int, promo_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM promo_uses WHERE user_id = ? AND promo_id = ?",
            (user_id, promo_id),
        )
        row = await cur.fetchone()
        return row[0] > 0

    async def get_all_promos(self):
        cur = await self._conn.execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
        return await cur.fetchall()

    async def delete_promo(self, promo_id: int):
        await self._conn.execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
        await self._conn.commit()

    # --- Settings ---
    async def get_setting(self, key: str, default: str = "") -> str:
        cur = await self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        await self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await self._conn.commit()

    # --- Support ---
    async def add_ticket(self, user_id: int, message: str):
        await self._conn.execute(
            "INSERT INTO support_tickets (user_id, message, created_at) VALUES (?, ?, ?)",
            (user_id, message, time.time()),
        )
        await self._conn.commit()

    async def get_open_tickets(self):
        cur = await self._conn.execute(
            "SELECT t.*, u.username, u.full_name FROM support_tickets t "
            "JOIN users u ON t.user_id = u.user_id "
            "WHERE t.status = 'open' ORDER BY t.created_at DESC"
        )
        return await cur.fetchall()

    async def close_ticket(self, ticket_id: int):
        await self._conn.execute(
            "UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,)
        )
        await self._conn.commit()

    # --- Test period ---
    async def has_used_test(self, user_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE user_id = ? AND tariff_id = 0",
            (user_id,),
        )
        row = await cur.fetchone()
        return row[0] > 0

    async def add_test_subscription(
        self, user_id: int, server_id: int, vpn_key: str, client_email: str,
        inbound_id: int, expires_at: float
    ):
        await self._conn.execute(
            "INSERT INTO subscriptions "
            "(user_id, server_id, tariff_id, devices, vpn_key, client_email, inbound_id, expires_at, created_at, is_active) "
            "VALUES (?, ?, 0, 1, ?, ?, ?, ?, ?, 1)",
            (user_id, server_id, vpn_key, client_email, inbound_id, expires_at, time.time()),
        )
        await self._conn.commit()
