# Changelog

## [0.1.0] — 2026-03-21

### Added
- Инициализация проекта
- Модульная архитектура (modular monolith)
- Ролевая модель: product_owner, admin, senior_master, master, client
- Иерархия веток (admin → senior_master → master)
- Каталог работ: электрика (100), сантехника (137), сборка мебели (92)
- 48 общих операций, 11 коэффициентов, 20 правил исключений
- Full-text поиск по каталогу с алиасами и хэштегами
- Сметы с версионированием и diff
- Workflow согласования скидок (master → senior_master → admin)
- Расчёт комиссий (платформа 20%, senior_master 5%, admin 5%)
- Инвайт-система с ролевой привязкой и модерацией
- Уведомления через Telegram (channel-based абстракция)
- Feature flags с управлением через админку
- Кадровые действия с audit trail
- RBAC с permission checks
- Docker Compose деплой (app + postgres + redis)
- Alembic миграции
- Seed data из реального каталога Стерлитамака
- Тесты критической бизнес-логики
