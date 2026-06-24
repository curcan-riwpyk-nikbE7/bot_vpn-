#!/usr/bin/env bash
#
# WireGuard VPN server installer for the VPN Telegram Bot.
#
# Installs and configures a WireGuard server on Ubuntu/Debian. The script is
# idempotent: running it again will not regenerate server keys or duplicate
# firewall rules. After it finishes it prints the values you need to add the
# server through the bot admin panel (public key, host, port).
#
# Usage (run as root on the VPN server):
#   sudo bash install_vpn.sh
#
# Configurable via environment variables:
#   WG_IF      WireGuard interface name        (default: wg0)
#   WG_PORT    UDP listen port                 (default: 51820)
#   WG_ADDR    server tunnel address + mask    (default: 10.66.66.1/24)
#   WG_DNS     DNS pushed to clients           (default: 1.1.1.1)
#
set -euo pipefail

WG_IF="${WG_IF:-wg0}"
WG_PORT="${WG_PORT:-51820}"
WG_ADDR="${WG_ADDR:-10.66.66.1/24}"
WG_DNS="${WG_DNS:-1.1.1.1}"
WG_DIR="/etc/wireguard"
CONF="${WG_DIR}/${WG_IF}.conf"

log() { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }

if [[ "${EUID}" -ne 0 ]]; then
    err "This script must be run as root (use sudo)."
    exit 1
fi

# ----------------------------------------------------------------- packages
log "Installing packages (wireguard, iptables, qrencode)..."
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq wireguard wireguard-tools iptables iproute2 qrencode >/dev/null
else
    err "Unsupported distro: this installer targets Debian/Ubuntu (apt)."
    exit 1
fi

# --------------------------------------------------------------- ip forward
log "Enabling IPv4 forwarding..."
SYSCTL_FILE="/etc/sysctl.d/99-wireguard.conf"
echo "net.ipv4.ip_forward = 1" > "${SYSCTL_FILE}"
sysctl -q -p "${SYSCTL_FILE}" || true

# ------------------------------------------------------------- server keys
umask 077
mkdir -p "${WG_DIR}"
if [[ ! -f "${WG_DIR}/server_private.key" ]]; then
    log "Generating server keypair..."
    wg genkey | tee "${WG_DIR}/server_private.key" | wg pubkey > "${WG_DIR}/server_public.key"
else
    log "Server keypair already exists, reusing it."
fi
SERVER_PRIV="$(cat "${WG_DIR}/server_private.key")"
SERVER_PUB="$(cat "${WG_DIR}/server_public.key")"

# ------------------------------------------------- outbound interface (NAT)
NIC="$(ip -4 route show default | awk '/default/ {print $5; exit}')"
if [[ -z "${NIC}" ]]; then
    err "Could not detect the default network interface; defaulting to eth0."
    NIC="eth0"
fi
log "Using outbound interface: ${NIC}"

# ------------------------------------------------------------- server conf
if [[ ! -f "${CONF}" ]]; then
    log "Writing ${CONF}..."
    cat > "${CONF}" <<EOF
# Managed by install_vpn.sh — peers are appended automatically by the bot.
[Interface]
Address = ${WG_ADDR}
ListenPort = ${WG_PORT}
PrivateKey = ${SERVER_PRIV}
PostUp = iptables -A FORWARD -i ${WG_IF} -j ACCEPT; iptables -A FORWARD -o ${WG_IF} -j ACCEPT; iptables -t nat -A POSTROUTING -o ${NIC} -j MASQUERADE
PostDown = iptables -D FORWARD -i ${WG_IF} -j ACCEPT; iptables -D FORWARD -o ${WG_IF} -j ACCEPT; iptables -t nat -D POSTROUTING -o ${NIC} -j MASQUERADE
EOF
    chmod 600 "${CONF}"
else
    log "${CONF} already exists, keeping existing peers."
fi

# ----------------------------------------------------------------- service
log "Enabling and starting wg-quick@${WG_IF}..."
systemctl enable "wg-quick@${WG_IF}" >/dev/null 2>&1 || true
# Restart to apply config; bring up if not running.
if systemctl is-active --quiet "wg-quick@${WG_IF}"; then
    systemctl restart "wg-quick@${WG_IF}"
else
    systemctl start "wg-quick@${WG_IF}"
fi

# --------------------------------------------------------- public endpoint
PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
if [[ -z "${PUBLIC_IP}" ]]; then
    PUBLIC_IP="$(ip -4 addr show "${NIC}" | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)"
fi

cat <<EOF

============================================================
 WireGuard server is ready.
============================================================
 Add this server in the bot admin panel (/admin -> Серверы):

   Протокол:        WireGuard
   Адрес (host):    ${PUBLIC_IP}
   Порт (port):     ${WG_PORT}
   Публичный ключ:  ${SERVER_PUB}
   DNS для клиентов:${WG_DNS}

 For automatic key provisioning by the bot over SSH, give the bot
 SSH access to this server (root or a sudo user).

 Useful commands:
   wg show ${WG_IF}            # show peers / handshakes
   systemctl status wg-quick@${WG_IF}
============================================================
EOF
