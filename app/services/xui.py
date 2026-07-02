"""3X-UI panel API client — create/delete VLESS clients, build share links."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit

import aiohttp

from app.config.settings import settings


class XUIError(RuntimeError):
    """Raised when the panel rejects a request or is unreachable."""


@dataclass
class XUIClientResult:
    access_link: str
    client_uuid: str
    email: str


def _expiry_ms(days: int) -> int:
    if days <= 0:
        return 0
    return int((time.time() + days * 86400) * 1000)


class XUIService:
    """Manage VLESS clients on a single 3X-UI panel."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        inbound_id: int,
        domain: str = "",
        verify_ssl: bool | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.inbound_id = inbound_id
        self.domain = domain or urlsplit(self.base_url).hostname or ""
        self.verify_ssl = verify_ssl if verify_ssl is not None else settings.xui_verify_ssl
        self._timeout = aiohttp.ClientTimeout(total=20)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _get_csrf_token(self, session: aiohttp.ClientSession, base: str) -> str:
        """Fetch CSRF token from 3X-UI panel (required for v2.4+/v3.x)."""
        url = f"{base}/csrf-token"
        try:
            async with session.get(
                url, headers={"X-Requested-With": "XMLHttpRequest"}
            ) as resp:
                if resp.status == 200:
                    body = await resp.json(content_type=None)
                    if body.get("success") and body.get("obj"):
                        return str(body["obj"])
        except (aiohttp.ClientError, Exception):
            pass
        return ""

    async def _login(self, session: aiohttp.ClientSession) -> None:
        """Login to 3X-UI panel with CSRF token support (v3.x compatible)."""
        base = self.base_url
        # Step 1: establish session (get session cookie)
        try:
            async with session.get(f"{base}/") as resp:
                if resp.status == 404:
                    raise XUIError(
                        f"HTTP 404 — панель не найдена по адресу {base}. "
                        "Проверьте секретный путь (URI Path)."
                    )
        except aiohttp.ClientError as exc:
            raise XUIError(f"Не удалось подключиться к {base}: {exc}") from exc

        # Step 2: get CSRF token (required for 3X-UI v2.4+/v3.x)
        csrf_token = await self._get_csrf_token(session, base)

        # Step 3: login with CSRF token
        headers: dict[str, str] = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token

        login_url = f"{base}/login"
        try:
            async with session.post(
                login_url,
                data=f"username={self.username}&password={self.password}",
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    body = await resp.json(content_type=None)
                    if body.get("success"):
                        return
                    raise XUIError(
                        f"Неверный логин или пароль: {body.get('msg', '')}"
                    )
                elif resp.status == 403:
                    # Might be old version without CSRF — try without token
                    pass
                else:
                    raise XUIError(f"login HTTP {resp.status}")
        except aiohttp.ClientError as exc:
            raise XUIError(f"login error: {exc}") from exc

        # Fallback: try without CSRF (older 3X-UI versions)
        try:
            async with session.post(
                login_url,
                data={"username": self.username, "password": self.password},
            ) as resp:
                if resp.status == 200:
                    body = await resp.json(content_type=None)
                    if body.get("success"):
                        return
                    raise XUIError(
                        f"Неверный логин или пароль: {body.get('msg', '')}"
                    )
                raise XUIError(f"login failed: HTTP {resp.status}")
        except aiohttp.ClientError as exc:
            raise XUIError(f"login error: {exc}") from exc

    async def _api(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
    ) -> dict:
        headers: dict[str, str] = {"X-Requested-With": "XMLHttpRequest"}
        # For non-GET requests, include CSRF token
        if method.upper() != "GET":
            csrf = await self._get_csrf_token(session, self.base_url)
            if csrf:
                headers["X-CSRF-Token"] = csrf
        async with session.request(
            method, self._url(path), json=json_body, headers=headers
        ) as resp:
            text = await resp.text()
            if resp.status == 403:
                raise XUIError(f"{path} — доступ запрещён (403). Попробуйте переподключить сервер.")
            if resp.status != 200:
                raise XUIError(f"{path} HTTP {resp.status}: {text[:200]}")
            body = json.loads(text)
        if not body.get("success"):
            raise XUIError(f"{path} failed: {body.get('msg', 'unknown')}")
        return body

    async def _get_inbound(self, session: aiohttp.ClientSession) -> dict:
        body = await self._api(session, "GET", f"panel/api/inbounds/get/{self.inbound_id}")
        obj = body.get("obj")
        if not isinstance(obj, dict):
            raise XUIError(f"inbound {self.inbound_id} not found")
        return obj

    async def _list_inbounds(self, session: aiohttp.ClientSession) -> list[dict]:
        body = await self._api(session, "GET", "panel/api/inbounds/list")
        obj = body.get("obj")
        if not isinstance(obj, list):
            return []
        return obj

    # ---------------------------------------------------------------- public
    async def check(self) -> dict:
        """Verify credentials and inbound existence. Returns first inbound info."""
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout, connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            await self._login(session)
            # Try to get the specific inbound first
            try:
                return await self._get_inbound(session)
            except XUIError:
                pass
            # Fall back to listing all inbounds
            inbounds = await self._list_inbounds(session)
            if inbounds:
                return inbounds[0]
            raise XUIError("No inbounds found on this panel")

    async def list_inbounds(self) -> list[dict]:
        """List all inbounds on the panel."""
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout, connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            await self._login(session)
            return await self._list_inbounds(session)

    async def add_client(
        self, *, email: str, days: int, total_gb: int = 0, devices: int = 1
    ) -> XUIClientResult:
        """Create a VLESS client and return the share link."""
        flow = settings.xui_flow
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout, connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            await self._login(session)
            inbound = await self._get_inbound(session)

            security = self._inbound_security(inbound)
            if security != "reality":
                flow = ""

            # 3X-UI v3.x API: POST /panel/api/clients/add
            client_body: dict = {
                "email": email,
                "totalGB": max(0, total_gb) * 1024**3,
                "expiryTime": _expiry_ms(days),
                "limitIp": devices,
                "enable": True,
                "flow": flow,
            }
            await self._api(
                session,
                "POST",
                "panel/api/clients/add",
                json_body={"client": client_body, "inboundIds": [self.inbound_id]},
            )

            # Fetch the created client to get server-generated UUID
            client_data = await self._api(
                session, "GET", f"panel/api/clients/get/{email}"
            )
            obj = client_data.get("obj", {})
            client_info = obj.get("client", {}) if isinstance(obj, dict) else {}
            client_uuid = client_info.get("uuid", "")
            if not client_uuid:
                raise XUIError("Клиент создан, но не удалось получить UUID")

            link = self._build_vless_link(inbound, client_uuid, email, flow)
            return XUIClientResult(access_link=link, client_uuid=client_uuid, email=email)

    async def remove_client(self, client_email: str) -> None:
        """Delete a client by email (3X-UI v3.x API)."""
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout, connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            await self._login(session)
            await self._api(
                session, "POST", f"panel/api/clients/del/{client_email}"
            )

    async def get_client_count(self) -> int:
        """Get number of clients on the inbound."""
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout, connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            await self._login(session)
            inbound = await self._get_inbound(session)
            raw = inbound.get("settings", "{}")
            s = json.loads(raw) if isinstance(raw, str) else raw
            clients = s.get("clients", [])
            return len(clients)

    # --------------------------------------------------------- link building
    @staticmethod
    def _stream_settings(inbound: dict) -> dict:
        raw = inbound.get("streamSettings") or "{}"
        return json.loads(raw) if isinstance(raw, str) else raw

    @classmethod
    def _inbound_security(cls, inbound: dict) -> str:
        return cls._stream_settings(inbound).get("security", "none")

    def _build_vless_link(
        self, inbound: dict, client_uuid: str, email: str, flow: str
    ) -> str:
        address = self.domain
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
