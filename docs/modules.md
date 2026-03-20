# Модули МастерБот

## Карта модулей

| Модуль | Файлы | Feature Flag | Описание |
|--------|-------|:---:|-----------|
| **auth** | `services/auth.py`, `models/user.py` | - | Регистрация, роли, Telegram auth |
| **catalog** | `services/catalog.py`, `models/catalog.py` | - | Каталог работ, поиск |
| **estimates** | `services/estimate.py`, `models/estimate.py` | - | Сметы с версионированием |
| **pricing** | `services/pricing.py`, `models/coefficient.py` | - | Расчёт цен, коэффициенты |
| **discounts** | `services/discount.py`, `models/discount.py` | `module.discounts` | Скидки и workflow согласования |
| **orders** | `models/order.py` | `module.orders` | Заказы и заявки |
| **payments** | `models/payment.py` | `module.payments` | Платежи, QR |
| **commissions** | `services/commission.py`, `models/payment.py` | - | Расчёт комиссий |
| **notifications** | `services/notification.py`, `models/notification.py` | `module.notifications` | Уведомления |
| **invites** | `services/invite.py`, `models/invite.py` | `module.invites` | Инвайт-система |
| **hierarchy** | `services/hierarchy.py`, `models/hierarchy.py` | - | Ветки и назначения |
| **staffing** | `services/staffing.py`, `models/staffing.py` | - | Кадровые действия |
| **ai** | `services/ai_intake.py`, `models/ai.py` | `module.ai_intake` | AI-парсинг |
| **analytics** | - | `module.analytics` | Аналитика (план) |
| **audit** | `core/audit.py`, `models/audit.py` | - | Аудит-лог |
| **feature_flags** | `core/module_registry.py`, `models/feature_flag.py` | - | Управление модулями |

## Зависимости между модулями

```
auth ← все модули
catalog ← estimates, pricing, ai
estimates ← orders, payments, discounts
hierarchy ← discounts (маршрутизация), staffing, invites
notifications ← discounts, orders, staffing, invites
audit ← все модули (через core/audit.py)
```

## Как отключить модуль

1. Через Telegram бот: Админ-панель → Feature Flags → переключить
2. Через HTTP API: `PATCH /api/admin/flags/module.discounts {"enabled": false}`
3. Через БД: `UPDATE feature_flags SET is_enabled = false WHERE code = 'module.discounts'`

Код проверяет `is_enabled("module.xxx")` перед выполнением логики.
