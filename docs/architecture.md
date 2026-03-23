# Архитектура МастерБот

## Подход: Modular Monolith

Единое приложение с чётким разделением на модули. Не микросервисы, не monolith-spaghetti.

## Слои

```
┌────────────────────────────────────┐
│          Delivery Layer            │
│  Telegram Bot  │  HTTP API         │
│  (aiogram 3)   │  (FastAPI)        │
└───────┬────────┴──────┬────────────┘
        │               │
┌───────▼───────────────▼────────────┐
│          Service Layer              │
│  auth, catalog, estimate, pricing, │
│  discount, commission, notification,│
│  invite, hierarchy, staffing, ai   │
└───────┬────────────────────────────┘
        │
┌───────▼────────────────────────────┐
│          Core Layer                 │
│  security (RBAC), events, audit,   │
│  module_registry, exceptions       │
└───────┬────────────────────────────┘
        │
┌───────▼────────────────────────────┐
│          Data Layer                 │
│  SQLAlchemy 2.0 models             │
│  PostgreSQL 16 + Redis 7           │
└────────────────────────────────────┘
```

## Ключевые принципы

1. **Минимум кода на единицу полезности** — нет абстракций ради абстракций
2. **Каждый модуль автономен** — свои модели, сервисы, handlers
3. **Feature flags** — модули отключаются без изменения кода
4. **Event-driven** — модули общаются через EventBus
5. **Audit-first** — все бизнес-действия логируются
6. **Channel-agnostic** — бизнес-логика не зависит от канала доставки
7. **Workspace-first UX** — bot/web используют единый workspace-сервис для dashboard, inbox и action-needed очередей

## Поток данных

```
Клиент → Telegram → Bot Handler → Service → Model → DB
                                      ↓
                              Event Bus → Notification Service → Telegram
                                      ↓
                              Audit Log
```

## База данных

PostgreSQL 16 с async через asyncpg. SQLAlchemy 2.0 Mapped types.
Миграции через Alembic. Naming convention для всех constraints.

## Кэширование

Redis используется для:
- Feature flags cache (in-memory + Redis fallback)
- Rate limiting
- Session cache (future)

## AI

Provider-agnostic интерфейс. Текущая реализация: HTTP-based (OpenAI-compatible).
Переключение через env. Prompt management через БД с версионированием.
