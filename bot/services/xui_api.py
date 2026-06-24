import aiohttp
import json
import uuid
import time
import ssl


class XUIClient:
    """Client for 3X-UI panel API."""

    def __init__(self, panel_url: str, login: str, password: str):
        self.panel_url = panel_url.rstrip("/")
        self.login = login
        self.password = password
        self._session = None
        self._cookie = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def authenticate(self) -> bool:
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.panel_url}/login",
                json={"username": self.login, "password": self.password},
            ) as resp:
                data = await resp.json()
                if data.get("success"):
                    self._cookie = resp.cookies
                    session.cookie_jar.update_cookies(resp.cookies)
                    return True
                return False
        except Exception:
            return False

    async def _ensure_auth(self):
        if self._cookie is None:
            if not await self.authenticate():
                raise ConnectionError("Failed to authenticate with 3X-UI panel")

    async def get_inbounds(self) -> list:
        await self._ensure_auth()
        session = await self._get_session()
        async with session.get(f"{self.panel_url}/panel/api/inbounds/list") as resp:
            data = await resp.json()
            if data.get("success"):
                return data.get("obj", [])
            return []

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        total_gb: int = 0,
        expire_time: int = 0,
        limit_ip: int = 1,
    ) -> bool:
        await self._ensure_auth()
        session = await self._get_session()

        client_uuid = str(uuid.uuid4())
        client_config = {
            "id": client_uuid,
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb * 1024 * 1024 * 1024 if total_gb > 0 else 0,
            "expiryTime": int(expire_time * 1000) if expire_time > 0 else 0,
            "enable": True,
            "tgId": "",
            "subId": str(uuid.uuid4())[:8],
            "reset": 0,
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_config]}),
        }

        async with session.post(
            f"{self.panel_url}/panel/api/inbounds/addClient",
            json=payload,
        ) as resp:
            data = await resp.json()
            if data.get("success"):
                return client_uuid
            return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        await self._ensure_auth()
        session = await self._get_session()
        async with session.post(
            f"{self.panel_url}/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
        ) as resp:
            data = await resp.json()
            return data.get("success", False)

    async def get_client_traffic(self, email: str) -> dict:
        await self._ensure_auth()
        session = await self._get_session()
        async with session.get(
            f"{self.panel_url}/panel/api/inbounds/getClientTraffics/{email}"
        ) as resp:
            data = await resp.json()
            if data.get("success") and data.get("obj"):
                return data["obj"]
            return {}

    async def build_vless_key(
        self, inbound: dict, client_uuid: str, server_address: str
    ) -> str:
        stream = json.loads(inbound.get("streamSettings", "{}"))
        network = stream.get("network", "tcp")
        security = stream.get("security", "none")

        params = [f"type={network}"]

        if security == "reality":
            reality = stream.get("realitySettings", {})
            params.append("security=reality")
            if reality.get("serverNames"):
                params.append(f"sni={reality['serverNames'][0]}")
            if reality.get("settings", {}).get("publicKey"):
                params.append(f"pbk={reality['settings']['publicKey']}")
            if reality.get("shortIds"):
                params.append(f"sid={reality['shortIds'][0]}")
            params.append(f"fp=chrome")
            params.append(f"spx=%2F")
        elif security == "tls":
            tls = stream.get("tlsSettings", {})
            params.append("security=tls")
            if tls.get("serverName"):
                params.append(f"sni={tls['serverName']}")

        if network == "ws":
            ws = stream.get("wsSettings", {})
            if ws.get("path"):
                params.append(f"path={ws['path']}")
            if ws.get("headers", {}).get("Host"):
                params.append(f"host={ws['headers']['Host']}")
        elif network == "grpc":
            grpc = stream.get("grpcSettings", {})
            if grpc.get("serviceName"):
                params.append(f"serviceName={grpc['serviceName']}")
        elif network == "tcp":
            tcp = stream.get("tcpSettings", {})
            header_type = tcp.get("header", {}).get("type", "none")
            if header_type != "none":
                params.append(f"headerType={header_type}")

        port = inbound.get("port", 443)
        remark = inbound.get("remark", "VPN")
        param_str = "&".join(params)

        return f"vless://{client_uuid}@{server_address}:{port}?{param_str}#{remark}"

    async def build_vmess_key(
        self, inbound: dict, client_uuid: str, server_address: str
    ) -> str:
        import base64
        stream = json.loads(inbound.get("streamSettings", "{}"))
        network = stream.get("network", "tcp")
        security = stream.get("security", "none")

        config = {
            "v": "2",
            "ps": inbound.get("remark", "VPN"),
            "add": server_address,
            "port": str(inbound.get("port", 443)),
            "id": client_uuid,
            "aid": "0",
            "scy": "auto",
            "net": network,
            "type": "none",
            "host": "",
            "path": "",
            "tls": security if security in ("tls", "reality") else "",
            "sni": "",
            "alpn": "",
            "fp": "",
        }

        if security == "tls":
            tls = stream.get("tlsSettings", {})
            config["sni"] = tls.get("serverName", "")

        if network == "ws":
            ws = stream.get("wsSettings", {})
            config["path"] = ws.get("path", "")
            config["host"] = ws.get("headers", {}).get("Host", "")

        json_str = json.dumps(config, separators=(",", ":"))
        encoded = base64.urlsafe_b64encode(json_str.encode()).decode()
        return f"vmess://{encoded}"

    async def generate_key(
        self,
        inbound_id: int,
        email: str,
        server_address: str,
        expire_time: float = 0,
        limit_ip: int = 1,
    ) -> str:
        """Generate a VPN key for a client on the given inbound."""
        inbounds = await self.get_inbounds()
        inbound = None
        for ib in inbounds:
            if ib["id"] == inbound_id:
                inbound = ib
                break

        if not inbound:
            raise ValueError(f"Inbound {inbound_id} not found")

        client_uuid = await self.add_client(
            inbound_id, email, total_gb=0, expire_time=expire_time, limit_ip=limit_ip
        )
        if not client_uuid:
            raise RuntimeError("Failed to add client to 3X-UI panel")

        protocol = inbound.get("protocol", "vless")
        if protocol == "vless":
            key = await self.build_vless_key(inbound, client_uuid, server_address)
        elif protocol == "vmess":
            key = await self.build_vmess_key(inbound, client_uuid, server_address)
        else:
            key = f"{protocol}://{client_uuid}@{server_address}:{inbound['port']}"

        return key, client_uuid

    async def check_connection(self) -> bool:
        try:
            return await self.authenticate()
        except Exception:
            return False
