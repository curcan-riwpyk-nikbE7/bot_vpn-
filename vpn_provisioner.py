"""Remote (and local) WireGuard peer provisioning.

This module turns the bot's "issue a key" action into a real configuration
change on a WireGuard server: it allocates a free tunnel IP, registers the
client's public key as a peer (``wg set`` + ``wg-quick save``), and returns a
ready-to-use client ``.conf``.

Two execution backends are supported:

* ``local``  — run the ``wg`` commands on this machine (used when the bot runs
  on the VPN server itself, and for the test suite).
* ``ssh``    — run the commands on a remote server over SSH (requires paramiko).

If provisioning fails for any reason the caller can fall back to offline config
generation so the bot never hard-fails.
"""

from __future__ import annotations

import ipaddress
import shlex
import subprocess
from dataclasses import dataclass

import vpn_generator


class ProvisionError(RuntimeError):
    """Raised when a peer could not be added/removed on the server."""


@dataclass
class SSHTarget:
    host: str
    user: str = "root"
    port: int = 22
    key_path: str | None = None
    password: str | None = None


@dataclass
class ProvisionResult:
    client_config: str
    client_public_key: str
    client_address: str


class WireGuardProvisioner:
    """Add/remove WireGuard peers on a server, locally or over SSH."""

    def __init__(
        self,
        *,
        ssh: SSHTarget | None = None,
        interface: str = "wg0",
        subnet: str = "10.66.66.0/24",
        use_sudo: bool = True,
    ) -> None:
        self.ssh = ssh
        self.interface = interface
        self.subnet = ipaddress.ip_network(subnet, strict=False)
        self.use_sudo = use_sudo

    # ------------------------------------------------------------------ exec
    def _run(self, command: str) -> str:
        """Run a shell command on the target, returning stdout."""
        if self.ssh is None:
            return self._run_local(command)
        return self._run_ssh(command)

    def _run_local(self, command: str) -> str:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ProvisionError(
                f"local command failed ({proc.returncode}): {command}\n{proc.stderr.strip()}"
            )
        return proc.stdout

    def _run_ssh(self, command: str) -> str:
        try:
            import paramiko  # imported lazily so the dep is optional
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProvisionError(
                "paramiko is required for SSH provisioning (pip install paramiko)"
            ) from exc

        assert self.ssh is not None
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.ssh.host,
                port=self.ssh.port,
                username=self.ssh.user,
                password=self.ssh.password,
                key_filename=self.ssh.key_path,
                timeout=15,
                allow_agent=False,
                look_for_keys=self.ssh.key_path is None and self.ssh.password is None,
            )
            _stdin, stdout, stderr = client.exec_command(command, timeout=30)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode()
            err = stderr.read().decode()
            if exit_status != 0:
                raise ProvisionError(
                    f"ssh command failed ({exit_status}): {command}\n{err.strip()}"
                )
            return out
        except ProvisionError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface any ssh error uniformly
            raise ProvisionError(f"ssh error: {exc}") from exc
        finally:
            client.close()

    def _wg(self, args: str) -> str:
        prefix = "sudo " if self.use_sudo else ""
        return self._run(f"{prefix}{args}")

    # ----------------------------------------------------------- ip handling
    def _used_addresses(self) -> set[str]:
        """Return the set of /32 client addresses already configured."""
        used: set[str] = set()
        out = self._wg(f"wg show {shlex.quote(self.interface)} allowed-ips")
        for line in out.splitlines():
            parts = line.split()
            for token in parts[1:]:
                if "/" in token:
                    addr = token.split("/")[0]
                    try:
                        used.add(str(ipaddress.ip_address(addr)))
                    except ValueError:
                        continue
        return used

    def _allocate_ip(self) -> str:
        used = self._used_addresses()
        hosts = self.subnet.hosts()
        server_ip = next(hosts)  # .1 is the server itself
        used.add(str(server_ip))
        for candidate in hosts:
            if str(candidate) not in used:
                return str(candidate)
        raise ProvisionError(f"no free addresses left in {self.subnet}")

    # -------------------------------------------------------------- actions
    def add_peer(
        self,
        *,
        server_public_key: str,
        endpoint_host: str,
        endpoint_port: int,
        dns: str = "1.1.1.1, 8.8.8.8",
        label: str = "VPN",
    ) -> ProvisionResult:
        """Create a client keypair, register it on the server, return its config."""
        client_priv, client_pub = vpn_generator.wireguard_keypair()
        address = self._allocate_ip()

        self._wg(
            f"wg set {shlex.quote(self.interface)} peer {shlex.quote(client_pub)} "
            f"allowed-ips {address}/32"
        )
        # Persist so the peer survives a service restart.
        self._wg(f"wg-quick save {shlex.quote(self.interface)}")

        config = vpn_generator.wireguard_client_config(
            client_private_key=client_priv,
            client_address=f"{address}/32",
            server_public_key=server_public_key,
            endpoint=f"{endpoint_host}:{endpoint_port}",
            dns=dns,
            label=label,
        )
        return ProvisionResult(
            client_config=config,
            client_public_key=client_pub,
            client_address=f"{address}/32",
        )

    def remove_peer(self, client_public_key: str) -> None:
        self._wg(
            f"wg set {shlex.quote(self.interface)} peer "
            f"{shlex.quote(client_public_key)} remove"
        )
        self._wg(f"wg-quick save {shlex.quote(self.interface)}")
