# Деплой на сервер `pridel`

## Текущий production-хост

- alias: `pridel`
- адрес: `193.47.43.64`
- пользователь: `root`
- публичный Mini App URL: `https://4-2.рф/app`
- ASCII / punycode для серверных конфигов: `4-2.xn--p1ai`
- DNS A-record для боевого домена должен указывать на `193.47.43.64`

Важно:

- для пользователя и в MAX можно показывать `4-2.рф`
- для `Caddyfile`, `curl`, сертификатов и server-side конфигов используйте только `4-2.xn--p1ai`
- не прописывайте `4-2.рф` и `4-2.xn--p1ai` одновременно в одном host-list Caddy: он нормализует IDN и воспримет это как дубликат

## Один раз настроить доступ

1. Создать отдельный ключ:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pridel -C "pridel@193.47.43.64"
```

2. Добавить alias в `~/.ssh/config`:

```sshconfig
Host pridel
  HostName 193.47.43.64
  User root
  Port 22
  IdentityFile ~/.ssh/pridel
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
```

3. Загрузить публичный ключ на сервер в `/root/.ssh/authorized_keys`.

Проверка:

```bash
ssh pridel hostname
```

## Проверка MAX-токена до деплоя

Перед запуском бота всегда проверяйте токен напрямую:

```bash
curl -H "Authorization: $MAX_BOT_TOKEN" https://platform-api.max.ru/me
```

Ожидается JSON с данными бота. Если MAX отвечает `401` и `Invalid access_token`, токен невалиден, и бот не поднимется даже при успешном деплое backend.

## Деплой приложения

Рекомендуемый путь:

1. Залить текущую версию проекта в `/opt/pridel`.
2. Запустить:

```bash
cd /opt/pridel
sudo bash deploy/setup.sh \
  --max-bot-token "$MAX_BOT_TOKEN" \
  --webapp-url "https://4-2.xn--p1ai/app"
```

Опционально для webhook-first production можно зафиксировать режим явно:

```bash
cd /opt/pridel
sudo bash deploy/setup.sh \
  --max-bot-token "$MAX_BOT_TOKEN" \
  --webapp-url "https://4-2.xn--p1ai/app" \
  --max-delivery-mode webhook \
  --max-webhook-secret "$(openssl rand -hex 16)"
```

Если после первого деплоя меняете `MAX_BOT_TOKEN`, `WEBAPP_URL` или другие значения в `/opt/pridel/.env`, обычного `docker compose restart app` недостаточно: нужно пересоздать контейнер, чтобы Docker заново подхватил env:

```bash
cd /opt/pridel
docker compose up -d --force-recreate app
```

То же правило обязательно для `MAX_DELIVERY_MODE`, `MAX_WEBHOOK_URL`, `MAX_WEBHOOK_PATH` и `MAX_WEBHOOK_SECRET`.

Если меняется код backend или новый Mini App shell, нужен rebuild образа:

```bash
cd /opt/pridel
docker compose up -d --build app
```

Если обновлялись и код, и env:

```bash
cd /opt/pridel
docker compose up -d --build --force-recreate app
```

Что важно:

- на Ubuntu 22 пакет Compose может называться `docker-compose-v2`, а не `docker-compose-plugin`;
- без `WEBAPP_URL` Mini App в MAX не откроется;
- в production лучше оставлять `MAX_DELIVERY_MODE=auto` или `webhook`; `polling` — только fallback для dev/test;
- если `MAX_WEBHOOK_URL` пуст, runtime строит webhook из `WEBAPP_URL` как `https://<host>/api/max/webhook`;
- если задан `MAX_WEBHOOK_SECRET`, MAX должен присылать его в заголовке `X-Max-Bot-Api-Secret`;
- в production Mini App API после `/api/v1/auth` ждёт `Authorization: Bearer <session>`; query auth через `?user_id=` запрещён вне dev;
- если меняете `APP_SECRET_KEY` или `WEBAPP_SESSION_TTL_SEC`, обязателен `docker compose up -d --force-recreate app`;
- `deploy/setup.sh` не публикует домен сам по себе, он готовит backend и инфраструктуру приложения.

## HTTPS reverse proxy

Для боевого домена используется контейнер Caddy. Рабочая конфигурация:

```caddyfile
4-2.xn--p1ai {
    encode gzip zstd
    reverse_proxy app:8000
}

193.47.43.64.sslip.io {
    redir https://4-2.xn--p1ai{uri} 308
}
```

Запуск:

```bash
docker rm -f pridel-caddy || true
docker run -d \
  --name pridel-caddy \
  --restart unless-stopped \
  --network pridel_default \
  -p 80:80 \
  -p 443:443 \
  -v /opt/pridel/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v pridel_caddy_data:/data \
  -v pridel_caddy_config:/config \
  caddy:2
```

- Проверяйте, что `/opt/pridel/Caddyfile` синхронизирован с git-checkout, а upstream в нём равен `app:8000`.
- Если после `docker compose up -d --build --force-recreate app` появился `502`, сначала пересоздайте `pridel-caddy` из текущего repo `Caddyfile`, а не ищите проблему в MAX Mini App.

## Проверки после деплоя

```bash
curl https://4-2.xn--p1ai/health
curl https://4-2.xn--p1ai/ready
curl -I https://4-2.xn--p1ai/app/
curl -i -X POST https://4-2.xn--p1ai/api/max/webhook
ssh pridel "cd /opt/pridel && docker compose logs --tail 100 app"
```

Нужно убедиться, что:

- `/health` отвечает `200`
- `/ready` показывает `database=ok` и `redis=ok`
- `/app/` отдаёт HTML Mini App
- webhook endpoint существует и отвечает `401/403` без секрета или `200` с корректным секретом
- в логах нет ошибок миграций и сборки

## Частые проблемы

- `docker compose` не найден:
  На Ubuntu 22 установите `docker-compose-v2`, если `docker-compose-plugin` недоступен.
- MAX бот не стартует:
  Сначала проверяйте токен через `/me`, потом убедитесь, что после правки `.env` контейнер `app` был пересоздан командой `docker compose up -d --force-recreate app`.
- Mini App не открывается в MAX:
  Обычно причина в отсутствии публичного `https` URL или в пустом `WEBAPP_URL`.
- Сертификат не выпускается:
  Проверьте, что `4-2.xn--p1ai` резолвится в `193.47.43.64`, и открыты порты `80` и `443`.

## 2026-04-09 production notes

- Verify exact Mini App entrypoint with `curl -I https://4-2.xn--p1ai/app`. This URL must return `200` and must not redirect to `http://.../app/`.
- `https://4-2.xn--p1ai/app/` may still serve HTML, but for MAX the critical path is the exact `/app` URL.
- In MAX bot/mini-app settings, save `https://4-2.xn--p1ai/app`, not `https://4-2.рф/app`.
- If MAX shows a native technical error before the frontend renders, first check exact `/app`, then verify `WEBAPP_URL`, and only after that inspect signed launch data.
- The shipped Mini App now supports launch payload extraction from URL fragments like `#WebAppData=...`, which matches MAX launch behavior.
- Control Center in the Mini App now includes role management, branch assignment, branch creation, invites, staffing, and owner insights. Treat it as the primary operational surface instead of legacy Telegram callbacks.
