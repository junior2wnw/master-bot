# Модули ПриДел

## Карта модулей

| Модуль | Файлы | Feature Flag | Назначение |
|--------|-------|:---:|------------|
| `auth` | `services/auth.py`, `models/user.py` | - | Регистрация, роли, вход в Mini App |
| `catalog` | `services/catalog.py`, `models/catalog.py` | - | Каталог работ, поиск, коэффициенты |
| `estimates` | `services/estimate.py`, `models/estimate.py` | - | Сметы и версии смет |
| `pricing` | `services/pricing.py`, `models/coefficient.py` | - | Расчёт цен и поправок |
| `discounts` | `services/discount.py`, `models/discount.py` | `module.discounts` | Скидки и согласования |
| `orders` | `services/order.py`, `models/order.py` | `module.orders` | Заказы и жизненный цикл работ |
| `payments` | `services/payment.py`, `models/payment.py` | `module.payments` | Оплата, QR и реквизиты |
| `commissions` | `services/commission.py`, `models/payment.py` | - | Комиссии платформы и распределение долей |
| `notifications` | `services/notification.py`, `models/notification.py` | `module.notifications` | События, шаблоны, доставка |
| `invites` | `services/invite.py`, `models/invite.py` | `module.invites` | Инвайты и подключения |
| `hierarchy` | `services/hierarchy.py`, `models/hierarchy.py` | - | Ветки мастеров и подчинённость |
| `staffing` | `services/staffing.py`, `models/staffing.py` | - | Кадровые действия |
| `ai` | `services/ai_intake.py`, `models/ai.py` | `module.ai_intake` | AI-разбор запросов |
| `workspace` | `services/workspace.py` | - | Дашборд, уведомления, рабочее пространство |
| `audit` | `core/audit.py`, `models/audit.py` | - | Журнал действий |
| `feature_flags` | `core/module_registry.py`, `models/feature_flag.py` | - | Включение и выключение модулей |

## Связи между модулями

```text
auth <- используется почти везде
catalog <- estimates, pricing, ai
estimates <- discounts, orders, payments
hierarchy <- discounts, staffing, invites
notifications <- estimates, discounts, orders, staffing, invites
audit <- все доменные действия
workspace <- API и Mini App
```

## Как отключить модуль

1. Через административный интерфейс или API фич-флагов.
2. Через HTTP API: `PATCH /api/admin/flags/module.discounts {"enabled": false}`.
3. Через БД: `UPDATE feature_flags SET is_enabled = false WHERE code = 'module.discounts'`.

Сервисный код обязан проверять `is_enabled("module.xxx")` перед выполнением необязательной логики.
