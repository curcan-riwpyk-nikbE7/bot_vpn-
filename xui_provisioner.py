"""3X-UI panel provisioning.

Turns the bot's "issue a key" action into a real client on a `3X-UI
<https://github.com/MHSanaei/3x-ui>`_ panel: it logs in to the panel, creates a
client on a chosen inbound through the panel HTTP API and builds a ready-to-use
``vless://`` share link from the inbound's stream settings.

Only the standard library plus :mod:`aiohttp` (already pulled in by aiogram) are
required, so no extra dependency is added.

The most common inbound shapes are supported when building the share link:
TCP/WS/gRPC/HTTP transports with ``reality``, ``tls`` or no security. If a panel
uses an exotic configuration the client is still created on the panel; only the
auto-built link may need manual tweaking.
"""

from __future__ import annotations

import json
import time
import uuid as uuid_lib
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit

import aiohttp


class XUIError(RuntimeError):
    """Raised when the 3X-UI panel cannot be reached or rejects a request."""


@dataclass
class XUIPanel:
    """Connection details for a single 3X-UI panel."""

    base_url: str
    username: str
    password: str
    inbound_id: int
    #: Address shown to clients in the share link. Falls back to the panel host.
    public_host: str = ""
    verify_ssl: bool = False

    @property
    def normalized_base(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def host(self) -> str:
        return urlsplit(self.normalized_base).hostname or ""


@dataclass
class XUIClientResult:
    access_link: str
    client_uuid: str
    email: str


def _expiry_ms(days: int) -> int:
    """Absolute expiry time in epoch milliseconds, 0 == unlimited."""
    if days <= 0:
        return 0
    return int((time.time() + days * 86400) * 1000)


class XUIProvisioner:
    """Create/remove clients on a 3X-UI panel and build their share links."""

    def __init__(self, panel: XUIPanel, *, timeout: float = 20.0) -> None:
        self.panel = panel
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    # --------------------------------------------------------------- helpers
    def _url(self, path: str) -> str:
        return f"{self.panel.normalized_base}/{path.lstrip('/')}"

    async def _login(self, session: aiohttp.ClientSession) -> None:
        async with session.post(
            self._url("login"),
            data={"username": self.panel.username, "password": self.panel.password},
        ) as resp:
            if resp.status != 200:
                raise XUIError(f"login HTTP {resp.status}")
            try:
                body = await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001
                raise XUIError(f"login returned non-JSON response: {exc}") from exc
        if not body.get("success"):
            raise XUIError(f"login failed: {body.get('msg', 'unknown error')}")

    async def _api(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
    ) -> dict:
        async with session.request(method, self._url(path), json=json_body) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise XUIError(f"{path} HTTP {resp.status}: {text[:200]}")
            try:
                body = json.loads(text)
            except json.JSONDecodeError as exc:
                raise XUIError(f"{path} returned non-JSON: {text[:200]}") from exc
        if not body.get("success"):
            raise XUIError(f"{path} failed: {body.get('msg', 'unknown error')}")
        return body

    async def _get_inbound(self, session: aiohttp.ClientSession) -> dict:
        body = await self._api(
            session, "GET", f"panel/api/inbounds/get/{self.panel.inbound_id}"
        )
        obj = body.get("obj")
        if not isinstance(obj, dict):
            raise XUIError(f"inbound {self.panel.inbound_id} not found")
        return obj

    # ---------------------------------------------------------------- public
    async def check(self) -> dict:
        """Verify credentials and that the inbound exists; return the inbound."""
        connector = aiohttp.TCPConnector(ssl=self.panel.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout,
            connector=connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        ) as session:
            await self._login(session)
            return await self._get_inbound(session)

    async def add_client(
        self,
        *,
        email: str,
        days: int,
        total_gb: int = 0,
        flow: str = "xtls-rprx-vision",
    ) -> XUIClientResult:
        """Create a vless client on the inbound and return its share link.

        ``flow`` is only applied to ``reality`` inbounds (where XTLS vision is the
        norm); for ws/grpc/tls inbounds the flow is forced empty so the produced
        link stays valid.
        """
        connector = aiohttp.TCPConnector(ssl=self.panel.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout,
            connector=connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        ) as session:
            await self._login(session)
            inbound = await self._get_inbound(session)
            flow = flow if self._inbound_security(inbound) == "reality" else ""

            client_uuid = str(uuid_lib.uuid4())
            sub_id = uuid_lib.uuid4().hex[:16]
            settings = {
                "clients": [
                    {
                        "id": client_uuid,
                        "email": email,
                        "flow": flow,
                        "limitIp": 0,
                        "totalGB": max(0, total_gb) * 1024 ** 3,
                        "expiryTime": _expiry_ms(days),
                        "enable": True,
                        "tgId": "",
                        "subId": sub_id,
                        "reset": 0,
                    }
                ]
            }
            await self._api(
                session,
                "POST",
                "panel/api/inbounds/addClient",
                json_body={
                    "id": self.panel.inbound_id,
                    "settings": json.dumps(settings),
                },
            )

            link = self._build_vless_link(inbound, client_uuid, email, flow)
            return XUIClientResult(access_link=link, client_uuid=client_uuid, email=email)

    async def remove_client(self, client_uuid: str) -> None:
        connector = aiohttp.TCPConnector(ssl=self.panel.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout,
            connector=connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        ) as session:
            await self._login(session)
            await self._api(
                session,
                "POST",
                f"panel/api/inbounds/{self.panel.inbound_id}/delClient/{client_uuid}",
            )

    # --------------------------------------------------------- link building
    @staticmethod
    def _stream_settings(inbound: dict) -> dict:
        raw = inbound.get("streamSettings") or "{}"
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return {}

    @classmethod
    def _inbound_security(cls, inbound: dict) -> str:
        return cls._stream_settings(inbound).get("security", "none")

    def _build_vless_link(
        self, inbound: dict, client_uuid: str, email: str, flow: str
    ) -> str:
        address = self.panel.public_host or self.panel.host
        port = int(inbound.get("port", 0))
        remark = inbound.get("remark") or "VPN"

        stream = self._stream_settings(inbound)
        network = stream.get("network", "tcp")
        security = stream.get("security", "none")
        params: dict[str, str] = {"type": network, "security": security}
        if flow:
            params["flow"] = flow

        if security == "reality":
            reality = stream.get("realitySettings", {})
            inner = reality.get("settings", {})
            server_names = reality.get("serverNames") or [""]
            short_ids = reality.get("shortIds") or [""]
            params.update(
                {
                    "pbk": inner.get("publicKey", ""),
                    "fp": inner.get("fingerprint", "chrome"),
                    "sni": server_names[0],
                    "sid": short_ids[0],
                    "spx": inner.get("spiderX", "/"),
                }
            )
        elif security == "tls":
            tls = stream.get("tlsSettings", {})
            tls_inner = tls.get("settings", {})
            params["sni"] = tls.get("serverName", "")
            params["fp"] = tls_inner.get("fingerprint", "")
            alpn = tls.get("alpn")
            if alpn:
                params["alpn"] = ",".join(alpn)

        self._apply_network_params(params, network, stream)

        query = urlencode({k: v for k, v in params.items() if v != ""})
        fragment = quote(f"{remark}-{email}")
        return f"vless://{client_uuid}@{address}:{port}?{query}#{fragment}"

    @staticmethod
    def _apply_network_params(params: dict[str, str], network: str, stream: dict) -> None:
        if network == "ws":
            ws = stream.get("wsSettings", {})
            params["path"] = ws.get("path", "/")
            host = (ws.get("headers") or {}).get("Host", "")
            if host:
                params["host"] = host
        elif network == "grpc":
            grpc = stream.get("grpcSettings", {})
            params["serviceName"] = grpc.get("serviceName", "")
            if grpc.get("multiMode"):
                params["mode"] = "multi"
        elif network in ("tcp", "http"):
            tcp = stream.get("tcpSettings", {})
            header = tcp.get("header", {})
            if header.get("type") == "http":
                request = header.get("request", {})
                paths = request.get("path") or ["/"]
                params["path"] = paths[0]
                headers = request.get("headers", {})
                host = headers.get("Host")
                if isinstance(host, list) and host:
                    params["host"] = host[0]
                elif isinstance(host, str) and host:
                    params["host"] = host
                params["headerType"] = "http"
