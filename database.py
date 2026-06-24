"""Async SQLite data access layer for the VPN Telegram bot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS servers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    host            TEXT NOT NULL,
    port            INTEGER NOT NULL,
    protocol        TEXT NOT NULL,
    public_key      TEXT,
    max_connections INTEGER NOT NULL DEFAULT 100,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    panel_url       TEXT,
    panel_user      TEXT,
    panel_pass      TEXT,
    inbound_id      INTEGER
);

CREATE TABLE IF NOT EXISTS tariffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    days        INTEGER NOT NULL,
    price       INTEGER NOT NULL,
    description TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vpn_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    server_id   INTEGER NOT NULL,
    tariff_id   INTEGER,
    protocol    TEXT NOT NULL,
    config      TEXT NOT NULL,
    access_link TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    peer_public_key TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (server_id) REFERENCES servers (id),
    FOREIGN KEY (tariff_id) REFERENCES tariffs (id)
);

CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    tariff_id   INTEGER,
    key_id      INTEGER,
    amount      INTEGER NOT NULL,
    currency    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'paid',
    created_at  TEXT NOT NULL
);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass
class Server:
    id: int
    name: str
    host: str
    port: int
    protocol: str
    public_key: Optional[str]
    max_connections: int
    is_active: bool
    created_at: str
    load: int = 0
    panel_url: Optional[str] = None
    panel_user: Optional[str] = None
    panel_pass: Optional[str] = None
    inbound_id: Optional[int] = None

    @property
    def is_panel(self) -> bool:
        """True for 3X-UI panel servers provisioned via the panel API."""
        return bool(self.panel_url)

    @property
    def load_percent(self) -> int:
        if self.max_connections <= 0:
            return 100
        return min(100, round(self.load / self.max_connections * 100))

    @property
    def has_capacity(self) -> bool:
        return self.load < self.max_connections


@dataclass
class Tariff:
    id: int
    name: str
    days: int
    price: int
    description: Optional[str]
    is_active: bool
    created_at: str


@dataclass
class VpnKey:
    id: int
    user_id: int
    server_id: int
    tariff_id: Optional[int]
    protocol: str
    config: str
    access_link: Optional[str]
    created_at: str
    expires_at: str
    is_active: bool
    peer_public_key: Optional[str] = None
    server_name: Optional[str] = None

    @property
    def expires_dt(self) -> datetime:
        return datetime.fromisoformat(self.expires_at)

    @property
    def is_expired(self) -> bool:
        return self.expires_dt <= _utcnow()

    @property
    def days_left(self) -> int:
        delta = self.expires_dt - _utcnow()
        return max(0, delta.days + (1 if delta.seconds else 0))


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._migrate()
        await self._db.commit()

    async def _migrate(self) -> None:
        """Apply lightweight, additive migrations to pre-existing databases."""
        async with self.db.execute("PRAGMA table_info(vpn_keys)") as cur:
            cols = {row["name"] for row in await cur.fetchall()}
        if "peer_public_key" not in cols:
            await self.db.execute("ALTER TABLE vpn_keys ADD COLUMN peer_public_key TEXT")

        async with self.db.execute("PRAGMA table_info(servers)") as cur:
            server_cols = {row["name"] for row in await cur.fetchall()}
        for column, ddl in (
            ("panel_url", "ALTER TABLE servers ADD COLUMN panel_url TEXT"),
            ("panel_user", "ALTER TABLE servers ADD COLUMN panel_user TEXT"),
            ("panel_pass", "ALTER TABLE servers ADD COLUMN panel_pass TEXT"),
            ("inbound_id", "ALTER TABLE servers ADD COLUMN inbound_id INTEGER"),
        ):
            if column not in server_cols:
                await self.db.execute(ddl)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._db

    # ----------------------------------------------------------------- users
    async def upsert_user(self, user_id: int, username: str | None, full_name: str | None) -> None:
        await self.db.execute(
            """
            INSERT INTO users (id, username, full_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username = excluded.username,
                                          full_name = excluded.full_name
            """,
            (user_id, username, full_name, _iso(_utcnow())),
        )
        await self.db.commit()

    async def count_users(self) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # --------------------------------------------------------------- servers
    async def add_server(
        self,
        name: str,
        host: str,
        port: int,
        protocol: str,
        public_key: str | None,
        max_connections: int,
        panel_url: str | None = None,
        panel_user: str | None = None,
        panel_pass: str | None = None,
        inbound_id: int | None = None,
    ) -> int:
        cur = await self.db.execute(
            """
            INSERT INTO servers
                (name, host, port, protocol, public_key, max_connections, created_at,
                 panel_url, panel_user, panel_pass, inbound_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                host,
                port,
                protocol,
                public_key,
                max_connections,
                _iso(_utcnow()),
                panel_url,
                panel_user,
                panel_pass,
                inbound_id,
            ),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    async def _server_from_row(self, row: aiosqlite.Row) -> Server:
        return Server(
            id=row["id"],
            name=row["name"],
            host=row["host"],
            port=row["port"],
            protocol=row["protocol"],
            public_key=row["public_key"],
            max_connections=row["max_connections"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            load=await self.server_load(row["id"]),
            panel_url=row["panel_url"] if "panel_url" in row.keys() else None,
            panel_user=row["panel_user"] if "panel_user" in row.keys() else None,
            panel_pass=row["panel_pass"] if "panel_pass" in row.keys() else None,
            inbound_id=row["inbound_id"] if "inbound_id" in row.keys() else None,
        )

    async def get_server(self, server_id: int) -> Optional[Server]:
        async with self.db.execute("SELECT * FROM servers WHERE id = ?", (server_id,)) as cur:
            row = await cur.fetchone()
        return await self._server_from_row(row) if row else None

    async def list_servers(self, active_only: bool = False) -> list[Server]:
        query = "SELECT * FROM servers"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY id"
        async with self.db.execute(query) as cur:
            rows = await cur.fetchall()
        return [await self._server_from_row(row) for row in rows]

    async def server_load(self, server_id: int) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM vpn_keys WHERE server_id = ? AND is_active = 1 AND expires_at > ?",
            (server_id, _iso(_utcnow())),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def update_server_limit(self, server_id: int, max_connections: int) -> None:
        await self.db.execute(
            "UPDATE servers SET max_connections = ? WHERE id = ?",
            (max_connections, server_id),
        )
        await self.db.commit()

    async def deactivate_server(self, server_id: int) -> None:
        await self.db.execute("UPDATE servers SET is_active = 0 WHERE id = ?", (server_id,))
        await self.db.commit()

    async def pick_best_server(self) -> Optional[Server]:
        """Return the active server with the lowest load that still has capacity."""
        candidates = [s for s in await self.list_servers(active_only=True) if s.has_capacity]
        if not candidates:
            return None
        return min(candidates, key=lambda s: s.load_percent)

    # --------------------------------------------------------------- tariffs
    async def add_tariff(self, name: str, days: int, price: int, description: str | None) -> int:
        cur = await self.db.execute(
            """
            INSERT INTO tariffs (name, days, price, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, days, price, description, _iso(_utcnow())),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    @staticmethod
    def _tariff_from_row(row: aiosqlite.Row) -> Tariff:
        return Tariff(
            id=row["id"],
            name=row["name"],
            days=row["days"],
            price=row["price"],
            description=row["description"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )

    async def get_tariff(self, tariff_id: int) -> Optional[Tariff]:
        async with self.db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            row = await cur.fetchone()
        return self._tariff_from_row(row) if row else None

    async def list_tariffs(self, active_only: bool = False) -> list[Tariff]:
        query = "SELECT * FROM tariffs"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY price"
        async with self.db.execute(query) as cur:
            rows = await cur.fetchall()
        return [self._tariff_from_row(row) for row in rows]

    async def deactivate_tariff(self, tariff_id: int) -> None:
        await self.db.execute("UPDATE tariffs SET is_active = 0 WHERE id = ?", (tariff_id,))
        await self.db.commit()

    # ------------------------------------------------------------------ keys
    async def add_key(
        self,
        user_id: int,
        server_id: int,
        tariff_id: int | None,
        protocol: str,
        config: str,
        access_link: str | None,
        days: int,
        peer_public_key: str | None = None,
    ) -> int:
        now = _utcnow()
        expires = now + timedelta(days=days)
        cur = await self.db.execute(
            """
            INSERT INTO vpn_keys
                (user_id, server_id, tariff_id, protocol, config, access_link,
                 created_at, expires_at, peer_public_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                server_id,
                tariff_id,
                protocol,
                config,
                access_link,
                _iso(now),
                _iso(expires),
                peer_public_key,
            ),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    @staticmethod
    def _key_from_row(row: aiosqlite.Row) -> VpnKey:
        return VpnKey(
            id=row["id"],
            user_id=row["user_id"],
            server_id=row["server_id"],
            tariff_id=row["tariff_id"],
            protocol=row["protocol"],
            config=row["config"],
            access_link=row["access_link"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            is_active=bool(row["is_active"]),
            peer_public_key=row["peer_public_key"] if "peer_public_key" in row.keys() else None,
            server_name=row["server_name"] if "server_name" in row.keys() else None,
        )

    async def get_key(self, key_id: int) -> Optional[VpnKey]:
        async with self.db.execute(
            """
            SELECT k.*, s.name AS server_name
            FROM vpn_keys k LEFT JOIN servers s ON s.id = k.server_id
            WHERE k.id = ?
            """,
            (key_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._key_from_row(row) if row else None

    async def list_user_keys(self, user_id: int, active_only: bool = True) -> list[VpnKey]:
        query = (
            "SELECT k.*, s.name AS server_name "
            "FROM vpn_keys k LEFT JOIN servers s ON s.id = k.server_id "
            "WHERE k.user_id = ?"
        )
        if active_only:
            query += " AND k.is_active = 1"
        query += " ORDER BY k.created_at DESC"
        async with self.db.execute(query, (user_id,)) as cur:
            rows = await cur.fetchall()
        return [self._key_from_row(row) for row in rows]

    async def count_active_keys(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM vpn_keys WHERE is_active = 1 AND expires_at > ?",
            (_iso(_utcnow()),),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def deactivate_key(self, key_id: int) -> None:
        await self.db.execute("UPDATE vpn_keys SET is_active = 0 WHERE id = ?", (key_id,))
        await self.db.commit()

    # -------------------------------------------------------------- payments
    async def add_payment(
        self,
        user_id: int,
        tariff_id: int | None,
        key_id: int | None,
        amount: int,
        currency: str,
        status: str = "paid",
    ) -> int:
        cur = await self.db.execute(
            """
            INSERT INTO payments (user_id, tariff_id, key_id, amount, currency, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, tariff_id, key_id, amount, currency, status, _iso(_utcnow())),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    async def total_revenue(self) -> int:
        async with self.db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'"
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0
