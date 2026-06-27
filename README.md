# VPN Shop Bot

Профессиональный Telegram-бот для продажи VPN подписок на базе 3X-UI + VLESS Reality.

## Возможности

- 🌍 Покупка VPN через бота (тарифы, оплата, автоматическая выдача ключа + QR)
- 🔑 Управление подписками (продление, просмотр ключей)
- 📡 Управление серверами 3X-UI через админ-панель
- 💳 ЮKassa интеграция (webhook автоматической обработки платежей)
- 🎁 Реферальная система (бонусные дни за приглашённых друзей)
- 📢 Рассылки (все / активные / с истекающей подпиской)
- ⏰ Автоуведомления (за 3 дня до конца, при отключении)
- 🛡️ Лимит устройств через 3X-UI `limitIp`
- ⚙️ Настройка дизайна бота через админку (тексты, контакты)
- 📊 Статистика (клиенты, подписки, доход, серверы)
- 🐳 Docker-деплой одной командой

## Стек

- Python 3.12, aiogram 3, FastAPI
- PostgreSQL + SQLAlchemy (async)
- Redis (кеш/очереди)
- 3X-UI API (VLESS Reality/TLS)
- ЮKassa
- Docker Compose

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/curcan-riwpyk-nikbE7/bot_vpn-.git
cd bot_vpn-

# 2. Настроить .env
cp .env.example .env
nano .env   # заполнить BOT_TOKEN, ADMIN_IDS, YOOKASSA_*

# 3. Запустить
docker compose up -d

# 4. Проверить
docker compose logs -f bot
```

После запуска:
1. Отправьте `/admin` боту
2. Добавьте серверы (📡 Серверы → ➕ Добавить сервер)
3. Добавьте тарифы (💰 Тарифы → ➕ Добавить тариф)
4. Бот готов к продажам

## Структура проекта

```
app/
├── bot/
│   ├── handlers/
│   │   ├── client.py    # /start, покупка, мой VPN, продление, рефералы
│   │   └── admin.py     # /admin, серверы, тарифы, клиенты, рассылки, статистика
│   ├── keyboards/
│   │   ├── client_kb.py # Клавиатуры клиента
│   │   └── admin_kb.py  # Клавиатуры админа
│   ├── states/
│   │   └── states.py    # FSM-состояния
│   └── filters/
│       └── admin.py     # Фильтр IsAdmin
├── database/
│   ├── models.py        # SQLAlchemy модели (users, servers, tariffs, ...)
│   └── database.py      # Engine + session factory
├── services/
│   ├── xui.py           # 3X-UI API клиент
│   ├── payments.py      # ЮKassa создание/проверка платежей
│   ├── vpn_generator.py # Генерация ключа + QR
│   ├── referral.py      # Реферальная система
│   ├── mailing.py       # Рассылки
│   └── notifications.py # Автоуведомления (истечение подписки)
├── admin/
│   └── webhook.py       # FastAPI: /webhook/yookassa
├── config/
│   └── settings.py      # Pydantic Settings
└── main.py              # Точка входа
docker-compose.yml
Dockerfile
requirements.txt
.env.example
```

## Клиентское меню (/start)

```
🔥 VPN SERVICE

🌍 Купить VPN
🔑 Мой VPN
💳 Продлить
🎁 Пригласить друга
⭐ Бонусы
🆘 Поддержка
```

## Админ-панель (/admin)

```
📡 Серверы      — добавить/проверить/выключить/удалить
💰 Тарифы       — добавить/изменить цену|срок/удалить
👥 Клиенты      — поиск, блокировка, продление
📊 Статистика   — клиенты, подписки, доход
📢 Рассылка     — все/активные/истекающие
⚙️ Настройки    — тексты, контакты, реферальные бонусы
```

## Оплата

При покупке бот создаёт платёж в ЮKassa, даёт ссылку на оплату. После успешной оплаты (через webhook или кнопку «Проверить оплату»):
1. Выбирается наименее загруженный сервер
2. Создаётся VLESS клиент через API 3X-UI
3. Пользователь получает `vless://` ссылку + QR-код

## Реферальная система

- Каждый пользователь получает реферальную ссылку
- 3 друга = 7 дней бесплатного VPN
- 10 друзей = 30 дней бесплатного VPN
- Пороги настраиваются через админку

## Webhook (ЮKassa)

FastAPI слушает на порту 8080:
- `POST /webhook/yookassa` — обработка `payment.succeeded`
- `GET /health` — проверка доступности

Настройте URL вебхука в личном кабинете ЮKassa: `https://your-domain:8080/webhook/yookassa`

## Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен от @BotFather |
| `ADMIN_IDS` | Telegram ID админов (через запятую) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis URL |
| `YOOKASSA_SHOP_ID` | Shop ID из ЮKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ ЮKassa |
| `XUI_FLOW` | XTLS flow (по умолчанию `xtls-rprx-vision`) |
| `XUI_VERIFY_SSL` | Проверять SSL панелей (по умолчанию `false`) |

## Безопасность

- Пароли серверов хранятся в PostgreSQL (шифрование на уровне приложения — расширяемо)
- Проверка прав админа через `IsAdmin` фильтр
- Логирование ошибок
- `.env` не коммитится в git
