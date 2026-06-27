"""VPN key generation: create client on 3X-UI panel, return vless link + QR."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Server, Subscription, Tariff, User
from app.services.xui import XUIError, XUIService


class VPNGeneratorError(RuntimeError):
    pass


async def generate_vpn_key(
    session: AsyncSession,
    user: User,
    tariff: Tariff,
    server: Server,
) -> Subscription:
    """Create VPN key on selected server and persist subscription."""
    email = f"tg{user.telegram_id}-{tariff.id}"

    xui = XUIService(
        base_url=server.url,
        username=server.login,
        password=server.password,
        inbound_id=server.inbound_id,
        domain=server.domain,
    )

    try:
        result = await xui.add_client(
            email=email, days=tariff.days, devices=tariff.devices
        )
    except XUIError as exc:
        raise VPNGeneratorError(f"Не удалось создать ключ: {exc}") from exc

    expire = datetime.now(timezone.utc) + timedelta(days=tariff.days)
    sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        client_uuid=result.client_uuid,
        client_email=result.email,
        vless_link=result.access_link,
        devices_limit=tariff.devices,
        expire_date=expire,
        is_active=True,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def revoke_vpn_key(session: AsyncSession, sub: Subscription, server: Server) -> None:
    """Remove client from 3X-UI panel and deactivate subscription."""
    xui = XUIService(
        base_url=server.url,
        username=server.login,
        password=server.password,
        inbound_id=server.inbound_id,
        domain=server.domain,
    )
    try:
        await xui.remove_client(sub.client_uuid)
    except XUIError:
        pass  # best-effort cleanup

    sub.is_active = False
    await session.commit()


def generate_qr(vless_link: str) -> io.BytesIO:
    """Generate QR code image as bytes buffer."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(vless_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def select_best_server(session: AsyncSession) -> Server | None:
    """Pick the least-loaded active server."""
    stmt = select(Server).where(Server.is_active.is_(True))
    result = await session.execute(stmt)
    servers = list(result.scalars().all())
    if not servers:
        return None

    best: Server | None = None
    best_load = float("inf")
    for server in servers:
        count_stmt = select(Subscription).where(
            Subscription.server_id == server.id, Subscription.is_active.is_(True)
        )
        count_res = await session.execute(count_stmt)
        load = len(list(count_res.scalars().all()))
        if load < server.max_clients and load < best_load:
            best_load = load
            best = server
    return best
