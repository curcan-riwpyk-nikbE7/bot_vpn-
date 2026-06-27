"""3X-UI panel API client — create/delete VLESS clients, build share links."""

from __future__ import annotations

import json
import time
import uuid as uuid_lib
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

    def _alt_base_urls(self) -> list[str]:
        """Generate alternative base URLs to try (http/https swap, with/without path)."""
        urls = [self.base_url]
        # Also try protocol swap
        if self.base_url.startswith("https://"):
            urls.append(self.base_url.replace("https://", "http://", 1))
        elif self.base_url.startswith("http://"):
            urls.append(self.base_url.replace("http://", "https://", 1))
        # Also try root URL (without secret path) in case API is at root
        parts = urlsplit(self.base_url)
        if parts.path and parts.path != "/":
            root = f"{parts.scheme}://{parts.netloc}"
            if root not in urls:
                urls.append(root)
            alt_scheme = "http" if parts.scheme == "https" else "https"
            alt_root = f"{alt_scheme}://{parts.netloc}"
            if alt_root not in urls:
                urls.append(alt_root)
        return urls

    async def _try_login(
        self, session: aiohttp.ClientSession, base: str
    ) -> str | None:
        """Try to login with given base URL. Returns None on success, error string on failure."""
        login_paths = ["login", "panel/login"]
        for path in login_paths:
            url = f"{base}/{path.lstrip('/')}"
            # Try form-data
            try:
                async with session.post(
                    url,
                    data={"username": self.username, "password": self.password},
                ) as resp:
                    if resp.status == 200:
                        body = await resp.json(content_type=None)
                        if body.get("success"):
                            self.base_url = base
                            return None
                    elif resp.status != 404:
                        return f"HTTP {resp.status} at {url}"
            except aiohttp.ClientError:
                pass
            # Try JSON body (some 3X-UI versions)
            try:
                async with session.post(
                    url,
                    json={"username": self.username, "password": self.password},
                ) as resp:
                    if resp.status == 200:
                        body = await resp.json(content_type=None)
                        if body.get("success"):
                            self.base_url = base
                            return None
            except aiohttp.ClientError:
                pass
        return None  # all 404 — not this base

    async def _login(self, session: aiohttp.ClientSession) -> None:
        """Try login across http/https and multiple paths."""
        alt_urls = self._alt_base_urls()
        last_error = ""
        for base in alt_urls:
            login_paths = ["login", "panel/login"]
            for path in login_paths:
                url = f"{base}/{path.lstrip('/')}"
                # Form data (standard)
                try:
                    async with session.post(
                        url,
                        data={"username": self.username, "password": self.password},
                    ) as resp:
                        if resp.status == 200:
                            body = await resp.json(content_type=None)
                            if body.get("success"):
                                self.base_url = base
                                return
                            last_error = f"{body.get('msg', 'wrong credentials')}"
                        elif resp.status == 404:
                            last_error = f"HTTP 404 at {url}"
                        else:
                            last_error = f"HTTP {resp.status}"
                except aiohttp.ClientError as exc:
                    last_error = f"{exc.__class__.__name__}: {exc}"
                    continue
                # JSON body (newer 3X-UI builds)
                try:
                    async with session.post(
                        url,
                        json={"username": self.username, "password": self.password},
                    ) as resp:
                        if resp.status == 200:
                            body = await resp.json(content_type=None)
                            if body.get("success"):
                                self.base_url = base
                                return
                except aiohttp.ClientError:
                    pass
        raise XUIError(f"login failed: {last_error}")

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

            client_uuid = str(uuid_lib.uuid4())
            sub_id = uuid_lib.uuid4().hex[:16]
            client_settings = {
                "clients": [
                    {
                        "id": client_uuid,
                        "email": email,
                        "flow": flow,
                        "limitIp": devices,
                        "totalGB": max(0, total_gb) * 1024**3,
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
                json_body={"id": self.inbound_id, "settings": json.dumps(client_settings)},
            )

            link = self._build_vless_link(inbound, client_uuid, email, flow)
            return XUIClientResult(access_link=link, client_uuid=client_uuid, email=email)

    async def remove_client(self, client_uuid: str) -> None:
        """Delete a client from the inbound."""
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(
            timeout=self._timeout, connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)
        ) as session:
            await self._login(session)
            await self._api(
                session, "POST", f"panel/api/inbounds/{self.inbound_id}/delClient/{client_uuid}"
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
