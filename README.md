# ПриДел

> Продукт компании `4-2`: платформа услуг для мастеров с ботом и мини-приложением в MAX.

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)

## Что это

ПриДел помогает вести полный цикл сервисных работ: каталог услуг, сметы, заказы, согласования, оплаты, уведомления и роли команды.

Брендовая схема проекта:

- `4-2` — компания и домен
- `ПриДел` — продукт и главное имя в интерфейсе
- `pridel` / `придел` — допустимые технические slug-формы, но не основной display-бренд

Основной сценарий запуска:

- пользователь открывает бота в MAX;
- из чата запускает мини-приложение;
- работает в web-интерфейсе со сметами, профилем и заказами;
- backend на FastAPI хранит состояние в PostgreSQL и фоновые события в Redis.

## Что уже есть

- MAX bot runtime через Bot API: webhook-first в production, polling fallback в dev
- Mini App аутентификация по подписанным launch params
- каталог работ, поиск и коэффициенты
- сметы с версиями, экспортом PDF/XLSX и QR-оплатой
- роли `client`, `master`, `senior_master`, `admin`, `product_owner`
- уведомления, аудит, feature flags, AI intake

## Быстрый старт

```bash
git clone https://github.com/junior2wnw/master-bot.git
cd master-bot
cp .env.example .env
```

Заполните минимум:

- `MAX_BOT_TOKEN`
- `WEBAPP_URL`
- `DATABASE_URL`

Локальный запуск через Docker:

```bash
make up
make migrate
make seed
```

Приложение поднимется на `http://localhost:8000`, Mini App статика будет доступна по `/app`.

## Подключение в MAX

1. Создайте чат-бота в кабинете партнёров MAX: `business.max.ru`.
2. Получите токен в разделе интеграции и сохраните его в `MAX_BOT_TOKEN`.
3. Разместите приложение по публичному `https://` URL.
4. Укажите этот URL в настройках бота: `Чат-бот и мини-приложение -> Настроить`.
5. Выберите кнопку запуска мини-приложения и сохраните настройки.

Webhook-first поведение проекта:

- если `MAX_DELIVERY_MODE=auto`, backend в production сам переходит на webhook, когда видит публичный `https://` в `WEBAPP_URL`
- если `MAX_WEBHOOK_URL` пуст, webhook строится как `<scheme>://<host>/api/max/webhook` на основе `WEBAPP_URL`
- если `MAX_WEBHOOK_SECRET` задан, входящие запросы MAX проходят проверку по `X-Max-Bot-Api-Secret`
- если публичного URL нет, проект остаётся на polling fallback и это считается dev/test режимом, а не боевым

Что учитывает проект по документации MAX:

- Bot API авторизуется через заголовок `Authorization: <token>`
- production-контур синхронизирует webhook через `POST /subscriptions`
- webhook валидируется shared secret в заголовке `X-Max-Bot-Api-Secret`
- `GET /updates` используется как fallback для локальной разработки и тестовых стендов
- Mini App стартовые данные берутся из `window.WebApp.initData`
- подпись launch params валидируется через `HMAC-SHA256("WebAppData", token)`
- приложение открывается внутри MAX по диплинку вида `https://max.ru/<botName>?startapp`

## Архитектура

```text
MAX Bot / Mini App -> FastAPI -> Services -> SQLAlchemy models -> PostgreSQL
                                 |
                                 -> Event Bus -> Notifications / Audit / Background jobs
                                 |
                                 -> Redis
```

Ключевой принцип: бизнес-логика не должна зависеть от конкретного UI-канала. Бот и Mini App выступают слоем доставки над одним backend.

## Конфигурация

Основные переменные окружения:

- `MAX_BOT_TOKEN` — токен чат-бота MAX
- `MAX_API_BASE_URL` — базовый URL MAX API, по умолчанию `https://platform-api.max.ru`
- `MAX_POLLING_TIMEOUT_SEC` — таймаут long polling
- `MAX_DELIVERY_MODE` — `auto | webhook | polling`; в production рекомендуем `auto` или `webhook`
- `MAX_WEBHOOK_URL` — явный webhook URL, если нельзя выводить его из `WEBAPP_URL`
- `MAX_WEBHOOK_PATH` — путь webhook при авто-выводе URL, по умолчанию `/api/max/webhook`
- `MAX_WEBHOOK_SECRET` — секрет проверки заголовка `X-Max-Bot-Api-Secret`
- `WEBAPP_URL` — публичный URL мини-приложения
- `WEBAPP_SESSION_TTL_SEC` — срок жизни подписанной web-сессии Mini App
- `OWNER_TELEGRAM_ID` — историческое имя переменной для внешнего ID владельца; в MAX сюда ставится `user_id` пользователя MAX
- `PLATFORM_OPERATOR_NAME` — оператор и компания продукта, по умолчанию `4-2`
- `PLATFORM_NAME` — пользовательское имя платформы, по умолчанию `ПриДел`
- `PLATFORM_PUBLIC_DOMAIN` — человекочитаемый домен продукта, по умолчанию `4-2.рф`
- `PLATFORM_PUBLIC_DOMAIN_ASCII` — punycode-форма домена для server/proxy/TLS-конфигов, по умолчанию `4-2.xn--p1ai`

Полный шаблон смотрите в `.env.example`.

## Деплой

Для Ubuntu есть скрипт:

```bash
sudo bash deploy/setup.sh \
  --max-bot-token "YOUR_MAX_TOKEN" \
  --webapp-url "https://YOUR_DOMAIN/app"
```

Если меняете `MAX_BOT_TOKEN`, `WEBAPP_URL` или другие переменные окружения после первого запуска, применяйте их через пересоздание контейнера:

```bash
docker compose up -d --force-recreate app
```

Для MAX runtime это важно вдвойне: при смене `MAX_DELIVERY_MODE`, `MAX_WEBHOOK_URL`, `MAX_WEBHOOK_PATH` или `MAX_WEBHOOK_SECRET` контейнер `app` тоже нужно пересоздать, иначе runtime продолжит жить со старой конфигурацией.

Он:

- создаёт `.env`
- поднимает Docker Compose
- применяет миграции
- загружает seed-данные
- настраивает systemd и базовые системные параметры

После деплоя проверьте:

- `/health`
- публичный `https://.../app`
- запуск Mini App из интерфейса MAX

Подробный production-процесс для боевого сервера `pridel`:

- alias `pridel` указывает на `root@193.47.43.64`
- публичный домен продукта: `https://4-2.рф/app`
- технический ASCII-домен для конфигов и reverse proxy: `https://4-2.xn--p1ai/app`
- в Caddy, curl, cert/TLS и server-side конфигурациях используйте только `4-2.xn--p1ai`: Caddy нормализует `4-2.рф` в тот же host и считает двойную запись дубликатом
- отдельная инструкция лежит в [docs/deploy_pridel.md](docs/deploy_pridel.md)

## Разработка

- Mini App frontend source lives in `app/webapp/frontend`
- For local non-Docker frontend build:

```bash
cd app/webapp/frontend
npm install
npm run build
```

- FastAPI serves `app/webapp/dist` when it exists
- Production app image now bakes the Mini App build into Docker
- API после `/api/v1/auth` работает через `Authorization: Bearer <session>`; legacy query auth через `?user_id=` оставлен только для dev-контура
- After code changes, deploy with `docker compose up -d --build app`
- If only `.env` changed, use `docker compose up -d --force-recreate app`
- If code and `.env` changed together, use `docker compose up -d --build --force-recreate app`

- `make test` — локальные тесты
- `make lint` — линтеры
- `make dev` — локальный uvicorn

## Документация

- [docs/architecture.md](docs/architecture.md)
- [docs/deploy_pridel.md](docs/deploy_pridel.md)
- [docs/modules.md](docs/modules.md)
- [docs/db_schema.md](docs/db_schema.md)
- [ROADMAP.md](ROADMAP.md)

## English

PriDel is a service workflow platform for field specialists with a MAX bot, MAX Mini App, FastAPI backend, PostgreSQL, and Redis. The repo is structured as a modular monolith so the same business logic can power bot actions, Mini App screens, exports, approvals, and notifications.
