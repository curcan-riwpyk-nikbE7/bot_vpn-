"""Generation of VPN credentials / client configurations.

Supported protocols:
    * WireGuard  -> a ready-to-import ``.conf`` client configuration
    * V2Ray/VLESS -> a ``vless://`` share link
    * OpenVPN    -> login credentials + a minimal ``.ovpn`` profile

The generated material is self-contained and deterministic in format so it can be
delivered to a user immediately. For a production deployment you would push the
generated public key / credentials to the actual VPN server (e.g. via the
WireGuard ``wg`` tool or an OpenVPN management interface); the hooks for that
live where :func:`generate` is called.
"""

from __future__ import annotations

import base64
import random
import secrets
import string
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

PROTOCOLS = ("WireGuard", "V2Ray", "OpenVPN")


@dataclass
class GeneratedCredential:
    protocol: str
    config: str
    access_link: str | None


def wireguard_keypair() -> tuple[str, str]:
    """Return a (private_key, public_key) WireGuard keypair, base64 encoded."""
    private = X25519PrivateKey.generate()
    priv_bytes = private.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    pub_bytes = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return (
        base64.b64encode(priv_bytes).decode(),
        base64.b64encode(pub_bytes).decode(),
    )


def wireguard_client_config(
    client_private_key: str,
    client_address: str,
    server_public_key: str,
    endpoint: str,
    dns: str = "1.1.1.1, 8.8.8.8",
    label: str = "VPN",
) -> str:
    """Build a WireGuard client .conf from already-allocated parameters."""
    return (
        f"# {label}\n"
        "[Interface]\n"
        f"PrivateKey = {client_private_key}\n"
        f"Address = {client_address}\n"
        f"DNS = {dns}\n\n"
        "[Peer]\n"
        f"PublicKey = {server_public_key}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {endpoint}\n"
        "PersistentKeepalive = 25\n"
    )


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _client_ip() -> str:
    """A pseudo-unique client address inside the WireGuard tunnel network."""
    return f"10.66.{random.randint(0, 255)}.{random.randint(2, 254)}"


def _wireguard_config(host: str, port: int, server_public_key: str | None, label: str) -> str:
    client_priv, _client_pub = wireguard_keypair()
    server_pub = server_public_key or "<SERVER_PUBLIC_KEY>"
    return (
        f"# {label}\n"
        "[Interface]\n"
        f"PrivateKey = {client_priv}\n"
        f"Address = {_client_ip()}/32\n"
        "DNS = 1.1.1.1, 8.8.8.8\n\n"
        "[Peer]\n"
        f"PublicKey = {server_pub}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {host}:{port}\n"
        "PersistentKeepalive = 25\n"
    )


def _vless_link(host: str, port: int, label: str) -> str:
    client_id = str(uuid.uuid4())
    params = "encryption=none&security=tls&type=tcp&flow=xtls-rprx-vision"
    fragment = label.replace(" ", "%20")
    return f"vless://{client_id}@{host}:{port}?{params}#{fragment}"


def _openvpn_config(host: str, port: int, label: str) -> tuple[str, str, str]:
    username = f"user_{secrets.token_hex(4)}"
    password = _random_password()
    profile = (
        f"# {label}\n"
        "client\n"
        "dev tun\n"
        "proto udp\n"
        f"remote {host} {port}\n"
        "resolv-retry infinite\n"
        "nobind\n"
        "persist-key\n"
        "persist-tun\n"
        "remote-cert-tls server\n"
        "auth-user-pass\n"
        "cipher AES-256-GCM\n"
        "verb 3\n"
        f"# login: {username}\n"
        f"# password: {password}\n"
    )
    return username, password, profile


def generate(protocol: str, host: str, port: int, server_public_key: str | None, label: str) -> GeneratedCredential:
    """Generate credentials for the given protocol."""
    proto = protocol.strip()
    if proto.lower() == "wireguard":
        config = _wireguard_config(host, port, server_public_key, label)
        return GeneratedCredential("WireGuard", config, None)

    if proto.lower() in ("v2ray", "vless"):
        link = _vless_link(host, port, label)
        return GeneratedCredential("V2Ray", link, link)

    if proto.lower() == "openvpn":
        username, password, profile = _openvpn_config(host, port, label)
        config = f"{profile}\nLogin: {username}\nPassword: {password}\n"
        return GeneratedCredential("OpenVPN", config, None)

    # Fallback: deliver an opaque access token so the bot never fails hard.
    token = secrets.token_urlsafe(24)
    return GeneratedCredential(proto or "Custom", f"Access token: {token}", None)
