# Деплой на сервер `pridel`

## Текущий production-хост

- alias: `pridel`
- адрес: `193.47.43.64`
- пользователь: `root`
- публичный Mini App URL: `https://193.47.43.64.sslip.io/app`

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
  --webapp-url "https://193.47.43.64.sslip.io/app"
```

Если после первого деплоя меняете `MAX_BOT_TOKEN`, `WEBAPP_URL` или другие значения в `/opt/pridel/.env`, обычного `docker compose restart app` недостаточно: нужно пересоздать контейнер, чтобы Docker заново подхватил env:

```bash
cd /opt/pridel
docker compose up -d --force-recreate app
```

Что важно:

- на Ubuntu 22 пакет Compose может называться `docker-compose-v2`, а не `docker-compose-plugin`;
- без `WEBAPP_URL` Mini App в MAX не откроется;
- `deploy/setup.sh` не публикует домен сам по себе, он готовит backend и инфраструктуру приложения.

## HTTPS reverse proxy

Для `sslip.io` используется контейнер Caddy. Рабочая конфигурация:

```caddyfile
193.47.43.64.sslip.io {
    encode gzip zstd
    reverse_proxy pridel-app-1:8000
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
  -v /opt/pridel/Caddyfile:/etc/caddy/Caddyfile \
  -v pridel_caddy_data:/data \
  -v pridel_caddy_config:/config \
  caddy:2
```

## Проверки после деплоя

```bash
curl https://193.47.43.64.sslip.io/health
curl https://193.47.43.64.sslip.io/ready
curl -I https://193.47.43.64.sslip.io/app/
ssh pridel "cd /opt/pridel && docker compose logs --tail 100 app"
```

Нужно убедиться, что:

- `/health` отвечает `200`
- `/ready` показывает `database=ok` и `redis=ok`
- `/app/` отдаёт HTML Mini App
- в логах нет ошибок миграций и сборки

## Частые проблемы

- `docker compose` не найден:
  На Ubuntu 22 установите `docker-compose-v2`, если `docker-compose-plugin` недоступен.
- MAX бот не стартует:
  Сначала проверяйте токен через `/me`, потом убедитесь, что после правки `.env` контейнер `app` был пересоздан командой `docker compose up -d --force-recreate app`.
- Mini App не открывается в MAX:
  Обычно причина в отсутствии публичного `https` URL или в пустом `WEBAPP_URL`.
- Сертификат не выпускается:
  Проверьте, что `193.47.43.64.sslip.io` резолвится в сервер, и открыты порты `80` и `443`.
