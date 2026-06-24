#!/usr/bin/env bash
#
# install_bot.sh — one-command installer for the VPN Telegram bot.
#
# Installs system dependencies, clones (or updates) the repository, creates a
# Python virtual environment, writes the .env file and registers a systemd
# service so the bot runs in the background and restarts automatically.
#
# Usage (run as root):
#   sudo bash install_bot.sh
#
# Non-interactive usage (skip the prompts):
#   sudo BOT_TOKEN=123:ABC ADMIN_ID=123456 bash install_bot.sh
#
# Optional environment overrides:
#   REPO_URL    git URL to clone (default: this project's GitHub repo)
#   BRANCH      branch to check out (default: main)
#   INSTALL_DIR where to install (default: /opt/vpn-bot)
#   SERVICE     systemd service name (default: vpn-bot)
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/curcan-riwpyk-nikbE7/bot_vpn-.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/vpn-bot}"
SERVICE="${SERVICE:-vpn-bot}"

log()  { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Запустите скрипт от root: sudo bash install_bot.sh"

# --------------------------------------------------------------- dependencies
log "Установка системных зависимостей (python3, venv, pip, git)..."
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip git
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip git
elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip git
else
    die "Не найден поддерживаемый пакетный менеджер (apt/dnf/yum). Установите python3, pip и git вручную."
fi

# --------------------------------------------------------------- get the code
if [ -d "$INSTALL_DIR/.git" ]; then
    log "Обновление существующей копии в $INSTALL_DIR..."
    git -C "$INSTALL_DIR" fetch --all --prune
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH" || warn "Не удалось обновить (продолжаю с текущей версией)."
elif [ -f "$(dirname "$0")/bot.py" ]; then
    # Script is run from inside an already-downloaded copy.
    SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [ "$SRC_DIR" != "$INSTALL_DIR" ]; then
        log "Копирование проекта в $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        cp -a "$SRC_DIR/." "$INSTALL_DIR/"
    fi
else
    log "Клонирование репозитория в $INSTALL_DIR..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --------------------------------------------------------------- python venv
log "Создание виртуального окружения и установка зависимостей..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# --------------------------------------------------------------- .env config
if [ -f .env ]; then
    log ".env уже существует — оставляю без изменений."
else
    log "Настройка .env..."
    BOT_TOKEN="${BOT_TOKEN:-}"
    ADMIN_ID="${ADMIN_ID:-}"
    if [ -z "$BOT_TOKEN" ]; then
        read -r -p "Введите BOT_TOKEN (от @BotFather): " BOT_TOKEN
    fi
    if [ -z "$ADMIN_ID" ]; then
        read -r -p "Введите ADMIN_ID (ваш id из @userinfobot): " ADMIN_ID
    fi
    [ -n "$BOT_TOKEN" ] || die "BOT_TOKEN обязателен."
    [ -n "$ADMIN_ID" ] || die "ADMIN_ID обязателен."

    cp .env.example .env
    # Заполняем основные значения, остальное остаётся из .env.example.
    sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" .env
    sed -i "s|^ADMIN_ID=.*|ADMIN_ID=${ADMIN_ID}|" .env
    chmod 600 .env
fi

# --------------------------------------------------------------- systemd unit
log "Регистрация systemd-сервиса '${SERVICE}'..."
cat >"/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=VPN Telegram Bot
After=network.target

[Service]
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE"
# Перезапуск гарантирует, что работает ровно один экземпляр (без TelegramConflictError).
systemctl restart "$SERVICE"

sleep 2
log "Готово! Статус сервиса:"
systemctl --no-pager status "$SERVICE" || true

cat <<EOF

============================================================
 Бот установлен и запущен как сервис «${SERVICE}».
 Каталог:   ${INSTALL_DIR}
 Логи:      journalctl -u ${SERVICE} -f
 Рестарт:   systemctl restart ${SERVICE}
 Стоп:      systemctl stop ${SERVICE}

 Дальше в Telegram: отправьте боту /admin →
   🖥️ Серверы (добавьте сервер или 3X-UI панель) и 💰 Тарифы.

 ВАЖНО: не запускайте bot.py вручную, пока работает сервис —
 иначе получите ошибку «terminated by other getUpdates request».
============================================================
EOF
