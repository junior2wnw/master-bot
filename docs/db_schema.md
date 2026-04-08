# Схема базы данных

## Основные таблицы

### Пользователи и роли

- `users` — пользователи платформы, внешний ID мессенджера, имя, статус
- `user_roles` — роли пользователей
- `branches` — ветки мастеров
- `branch_members` — привязка пользователей к веткам

### Каталог

- `professions`
- `service_groups`
- `service_subgroups`
- `service_items`
- `shared_operations`
- `coefficients`

### Сметы

- `estimates`
- `estimate_versions`
- `estimate_line_items`
- `estimate_discounts`

### Заказы и оплаты

- `orders`
- `order_status_history`
- `payments`
- `commission_policies`
- `commission_records`

### Уведомления и согласования

- `notification_templates`
- `notifications`
- `approval_requests`
- `discount_requests`

### Служебные сущности

- `invites`
- `invite_activations`
- `staffing_actions`
- `audit_log`
- `feature_flags`
- `system_settings`
- `prompt_templates`
- `ai_request_logs`

## Ключевые индексы

- `users.telegram_id` — внешний ID пользователя мессенджера; имя поля историческое
- `service_items.code` — уникальный код каталога
- `service_items.search_text` — полнотекстовый поиск
- `estimates.status` — выборка по статусам
- `discount_requests.assigned_to + status` — очередь согласований
- `notifications.user_id + status` — очередь доставки
- `audit_log.entity_type + entity_id` — история сущности

## Замечание по именованию

Часть таблиц и колонок появилась раньше MAX-интеграции. Поэтому в схеме встречаются исторические имена вроде `telegram_id`. В текущей архитектуре это внешний ID пользователя в канале запуска, а не продуктовая привязка документации к конкретному мессенджеру.
