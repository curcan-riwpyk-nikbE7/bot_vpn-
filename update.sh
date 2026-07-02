#!/bin/bash

echo "🔄 Обновление бота..."
cd "$(dirname "$0")"

git pull origin main

docker compose down
docker compose up -d --build

echo ""
echo "✅ Бот обновлён и запущен!"
echo ""
docker compose ps
