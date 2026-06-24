import time
import re
from urllib.parse import urlparse

from bot.database import db
from bot.services.xui_api import XUIClient


def extract_server_address(panel_url: str) -> str:
    parsed = urlparse(panel_url)
    return parsed.hostname or ""


async def get_xui_client(server_id: int) -> XUIClient:
    server = await db.get_server(server_id)
    if not server:
        raise ValueError("Server not found")
    return XUIClient(server["panel_url"], server["login"], server["password"])


async def create_vpn_key(
    user_id: int,
    server_id: int,
    tariff_id: int,
    devices: int,
    months: int = 0,
    expire_time: float = 0,
) -> str:
    server = await db.get_server(server_id)
    if not server:
        raise ValueError("Server not found")

    xui = XUIClient(server["panel_url"], server["login"], server["password"])
    try:
        inbounds = await xui.get_inbounds()
        if not inbounds:
            raise RuntimeError("No inbounds configured on server")

        inbound = inbounds[0]
        inbound_id = inbound["id"]

        email = f"user_{user_id}_{int(time.time())}"
        server_address = extract_server_address(server["panel_url"])

        if expire_time == 0 and months > 0:
            expire_time = time.time() + months * 30 * 24 * 3600

        key, client_uuid = await xui.generate_key(
            inbound_id=inbound_id,
            email=email,
            server_address=server_address,
            expire_time=expire_time,
            limit_ip=devices,
        )

        await db.add_subscription(
            user_id=user_id,
            server_id=server_id,
            tariff_id=tariff_id,
            devices=devices,
            vpn_key=key,
            client_email=email,
            inbound_id=inbound_id,
            expires_at=expire_time,
        )

        return key
    finally:
        await xui.close()


async def create_test_key(user_id: int, server_id: int) -> str:
    server = await db.get_server(server_id)
    if not server:
        raise ValueError("Server not found")

    test_hours = int(await db.get_setting("test_period_hours", "24"))
    test_devices = int(await db.get_setting("test_devices", "1"))

    xui = XUIClient(server["panel_url"], server["login"], server["password"])
    try:
        inbounds = await xui.get_inbounds()
        if not inbounds:
            raise RuntimeError("No inbounds configured on server")

        inbound = inbounds[0]
        inbound_id = inbound["id"]

        email = f"test_{user_id}_{int(time.time())}"
        server_address = extract_server_address(server["panel_url"])
        expire_time = time.time() + test_hours * 3600

        key, client_uuid = await xui.generate_key(
            inbound_id=inbound_id,
            email=email,
            server_address=server_address,
            expire_time=expire_time,
            limit_ip=test_devices,
        )

        await db.add_test_subscription(
            user_id=user_id,
            server_id=server_id,
            vpn_key=key,
            client_email=email,
            inbound_id=inbound_id,
            expires_at=expire_time,
        )

        return key
    finally:
        await xui.close()


async def check_server_status(server_id: int) -> bool:
    try:
        xui = await get_xui_client(server_id)
        result = await xui.check_connection()
        await xui.close()
        return result
    except Exception:
        return False
