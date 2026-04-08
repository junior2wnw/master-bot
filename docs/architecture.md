# Архитектура ПриДел

## Подход

Проект построен как modular monolith: один backend, несколько способов входа в продукт, общая бизнес-логика.

## Слои

```text
Delivery layer
  MAX Bot
  MAX Mini App
  HTTP API

Service layer
  auth, catalog, estimate, pricing, discount,
  commission, payment, notification, invite,
  hierarchy, staffing, ai, workspace

Core layer
  security (RBAC), events, audit,
  module_registry, exceptions

Data layer
  SQLAlchemy 2.0
  PostgreSQL 16
  Redis 7
```

## Главные принципы

1. Канал не управляет бизнес-логикой. MAX bot и Mini App используют один backend.
2. Все важные действия проходят через сервисный слой.
3. События расходятся через Event Bus, а не через прямые связи между модулями.
4. Аудит и уведомления считаются частью доменной логики, а не внешним дополнением.
5. Пользовательский интерфейс строится вокруг рабочего пространства: сметы, задачи, согласования, уведомления.

## Поток данных

```text
Клиент в MAX -> Bot / Mini App -> API -> Services -> Models -> DB
                                      |
                                      -> Event Bus -> Notification Dispatcher
                                      |
                                      -> Audit Log
```

## MAX-специфика

- Бот работает через MAX Bot API.
- Для разработки используется long polling через `GET /updates`.
- Mini App получает стартовые данные через `window.WebApp.initData`.
- Сервер валидирует подпись launch params по алгоритму MAX.
- Публичный запуск Mini App строится вокруг ссылки `https://max.ru/<botName>?startapp`.

## Хранилища

- PostgreSQL хранит пользователей, роли, каталог, сметы, заказы, оплаты, аудит и системные настройки.
- Redis используется для инфраструктурных задач: rate limit, очереди, кэш служебных данных.

## Эволюция

В коде сохранились отдельные исторические имена полей вроде `telegram_id`. Сейчас они используются как внешний ID пользователя мессенджера и не должны трактоваться как каналовая привязка документации или продукта.
