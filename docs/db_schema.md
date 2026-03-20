# Схема базы данных

## Таблицы

### Пользователи и роли
- `users` — пользователи (telegram_id, имя, активность)
- `user_roles` — роли пользователей (M2M, role_code)
- `branches` — ветки мастеров
- `branch_members` — привязка пользователей к веткам

### Инвайты
- `invites` — инвайт-коды (роль, ветка, лимиты, TTL)
- `invite_activations` — история активаций

### Каталог
- `professions` — направления (электрика, сантехника, мебель)
- `service_groups` — группы работ
- `service_subgroups` — подгруппы
- `service_items` — позиции каталога (330+ записей)
- `shared_operations` — общие операции (48 записей)
- `coefficients` — коэффициенты (11 записей)

### Сметы
- `estimates` — сметы (клиент, мастер, статус)
- `estimate_versions` — версии сметы (номер, суммы)
- `estimate_line_items` — позиции версии (снимок цены)
- `estimate_discounts` — скидки на версию

### Скидки
- `discount_requests` — запросы на скидку с workflow

### Заказы
- `orders` — заказы
- `order_status_history` — история статусов

### Платежи
- `payments` — записи платежей
- `commission_policies` — политики комиссий
- `commission_records` — рассчитанные комиссии

### Уведомления
- `notification_templates` — шаблоны
- `notifications` — очередь уведомлений

### Согласования
- `approval_requests` — универсальные согласования

### Кадры
- `staffing_actions` — кадровые действия

### Аудит
- `audit_log` — все бизнес-события

### Настройки
- `feature_flags` — флаги модулей
- `system_settings` — системные настройки

### AI
- `prompt_templates` — шаблоны промтов
- `ai_request_logs` — логи AI-запросов

## Ключевые индексы

- `users.telegram_id` — UNIQUE, lookup при каждом сообщении
- `service_items.code` — UNIQUE, lookup при добавлении в смету
- `service_items.search_text` — поиск по каталогу
- `estimates.status` — фильтрация по статусу
- `discount_requests.assigned_to + status` — очередь согласований
- `notifications.user_id + status` — очередь доставки
- `audit_log.entity_type + entity_id` — просмотр истории сущности
