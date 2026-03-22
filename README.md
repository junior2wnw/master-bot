# МастерБот

> Модульная платформа услуг для мастеров. Telegram-first, future-ready.

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)

---

## Что это

МастерБот — open-source платформа для управления услугами мастеров: электрика, сантехника, сборка мебели и любые другие сервисные профессии.

Платформа решает весь цикл: от заявки клиента до оплаты, включая каталог работ, сметы, согласования, скидки, комиссии, уведомления и аналитику.

**Стартуем с Telegram**, но архитектура позволяет подключить любой канал: web, VK, MAX и другие.

## Ключевые возможности

**Для клиента:**
- Описание задачи текстом или голосом (AI-парсинг)
- Предварительная смета с прозрачным breakdown
- Согласование изменений сметы на месте
- Оплата по QR / номеру телефона
- История заказов и повтор

**Для мастера:**
- Быстрый поиск работ по каталогу (full-text, алиасы, хэштеги)
- Сборка сметы в несколько кликов
- Шаблоны и популярные работы
- Изменение объёма на месте с версионированием
- Личный кабинет с доходами и статистикой

**Для старшего мастера:**
- Управление своей веткой мастеров
- Согласование скидок
- 5% комиссия с первой линии
- Аналитика по ветке

**Для админа:**
- Полное управление каталогом, ценами, коэффициентами
- Инвайты и модерация подключений
- Назначение старших мастеров
- Feature flags и управление модулями
- Кадровые действия с audit trail

**Для product owner:**
- Финансовый мониторинг и комиссии
- Воронка, споры, качество AI
- Управление провайдерами и каналами
- Глобальные настройки платформы

## Архитектура

```
┌─────────────────────────────────────────────┐
│              КАНАЛЫ ДОСТУПА                 │
│  Telegram (active) │ Web │ VK │ MAX (plan)  │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│              ЯДРО ПЛАТФОРМЫ                  │
│  Auth → RBAC → Иерархия → Feature Flags     │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│           БИЗНЕС-МОДУЛИ                      │
│  Каталог → Поиск → Сметы → Заказы           │
│  Ценообразование → Коэффициенты → Скидки     │
│  Платежи → Комиссии → AI Intake              │
│  Согласования → Уведомления → Аудит          │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│             УПРАВЛЕНИЕ                       │
│  Админ-панель → Owner-панель → Аналитика     │
└─────────────────────────────────────────────┘
```

## Ролевая модель

```
product_owner ─── полный доступ
  └── admin ─── управление платформой + может быть мастером
        ├── senior_master ─── ветка мастеров, 5% комиссия
        │     ├── master
        │     └── master
        └── master ─── напрямую под админом
client ─── отдельная роль, может сосуществовать с другими
```

## Быстрый старт

```bash
# Клонировать
git clone https://github.com/junior2wnw/master-bot.git
cd master-bot

# Настроить
cp .env.example .env
# Отредактировать .env: BOT_TOKEN, DATABASE_URL

# Поднять
make up

# Инициализировать БД и загрузить каталог
make migrate
make seed
```

Одна команда `make up` поднимает: приложение, PostgreSQL, Redis.

## Деплой на сервер (Ubuntu)

Для production-деплоя на чистый Ubuntu-сервер — один скрипт делает всё:

```bash
# Скачиваем проект
git clone https://github.com/junior2wnw/master-bot.git
cd master-bot

# Запускаем — установит Docker, создаст .env, поднимет контейнеры, настроит systemd
sudo bash deploy/setup.sh --bot-token "YOUR_BOT_TOKEN"
```

Скрипт автоматически:
- Установит Docker CE + Compose v2
- Сгенерирует надёжные пароли и секреты
- Применит миграции и загрузит каталог
- Настроит systemd, UFW, logrotate
- Проверит здоровье всех сервисов

Дополнительные флаги: `--domain`, `--port`, `--skip-firewall`, `--skip-systemd`, `--skip-seed`.

## CI/CD

GitHub Actions автоматически запускает на каждый push/PR:
- **Lint** — ruff check + format
- **Unit tests** — быстрые тесты без зависимостей
- **Integration tests** — с PostgreSQL + Redis в контейнерах
- **Docker build** — проверка сборки образа

## Модульность

Каждый модуль автономен и может быть отключен через feature flags:

| Модуль | Описание | Можно отключить |
|--------|----------|:---:|
| auth | Аутентификация через Telegram | - |
| catalog | Каталог работ и поиск | - |
| estimates | Сметы и версионирование | - |
| orders | Заказы и заявки | + |
| discounts | Скидки и согласование | + |
| payments | Платежи и QR | + |
| commissions | Расчёт комиссий | + |
| ai | AI-парсинг голоса и текста | + |
| notifications | Уведомления | + |
| invites | Инвайт-система | + |
| analytics | Аналитика и метрики | + |

## Стек

- **Python 3.12+** — FastAPI + aiogram 3
- **PostgreSQL 16** — основная БД
- **Redis 7** — кэш и очереди
- **Alembic** — миграции
- **Docker Compose** — деплой одной командой

## Roadmap

См. [ROADMAP.md](ROADMAP.md)

## Участие

См. [CONTRIBUTING.md](CONTRIBUTING.md)

---

## English

**MasterBot** is an open-source modular service platform for skilled workers (electricians, plumbers, furniture assemblers, etc.). Telegram-first, but designed for multi-channel expansion.

Key features: service catalog with fast search, versioned estimates, discount approval workflows, commission engine, role hierarchy (owner → admin → senior master → master → client), AI voice/text intake, QR payments, and full audit trail.

```bash
cp .env.example .env && make up && make migrate && make seed
```

See [ROADMAP.md](ROADMAP.md) for planned features. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

License: [MIT](LICENSE)
