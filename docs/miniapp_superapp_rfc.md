# RFC: ПриДел SuperApp Mini App

Статус: draft  
Дата: 2026-04-08  
Основание: аудит текущего бота, API, MAX Mini App ограничений и production-сервера `pridel`

## 1. Реальная цель задачи

[ТОЧНО] Пользователь хочет не просто "перерисовать текущий бот в web", а превратить ПриДел в Mini App-платформу нового класса:

- маркетплейс спроса на работы;
- сеть мастеров с профилями, уровнями, репутацией и командной структурой;
- операционный workspace для смет, заказов, согласований, платежей и модерации;
- модульный UX-конструктор, куда можно добавлять новые окна и функции без переписывания всего приложения.

[ТОЧНО] Минимально жизнеспособная цель не подходит. Нужна архитектура, которая:

- выдержит рост фичей;
- не сломает существующую бизнес-логику;
- не будет Telegram-first костылём;
- даст сильный UX на mobile-first MAX Mini App;
- позволит строить "соцсеть мастеров" без разрушения текущей service-платформы.

## 2. Что уже есть в проекте

[ТОЧНО] Текущий backend уже довольно сильный как доменная база:

- `catalog` — каталог работ, профессии, группы, поиск;
- `estimate` — сметы, версии, line items, экспорт PDF/XLSX, QR;
- `order` — заказы, статусы, назначение, история;
- `discount` — запросы и согласования;
- `payment` / `commission` — платежи и финансовая модель платформы;
- `invite` / `staffing` / `hierarchy` — ветки мастеров, инвайты, кадровые действия;
- `workspace` / `notification` — action center, inbox, рабочий dashboard;
- `profile` — расширенные профили мастеров и реквизиты;
- `analytics` / `audit` / `feature_flags` — админский и owner слой.

[ТОЧНО] Текущий Mini App уже не пустой. В [app/webapp/app.js](D:/master_bot/app/webapp/app.js) реализованы:

- dashboard;
- catalog + search;
- estimates + editor;
- orders + lifecycle actions;
- approvals;
- analytics;
- profile + role context;
- suggestions;
- notifications inbox;
- QR payments.

[ТОЧНО] MAX-бот сейчас уже:

- валидно подключён;
- умеет `/start`, `/app`, `/help`;
- открывает Mini App;
- получает updates через long polling;
- регистрирует MAX-пользователей в БД при взаимодействиях.

## 3. Жёсткая критика текущего состояния

### 3.1. Что хорошо

[ТОЧНО]

- Бизнес-ядро уже отделено от delivery-layer.
- Есть RBAC, события, аудит, feature flags.
- Уже есть работающий production MAX runtime.
- Mini App и бот уже сидят на одном backend.

### 3.2. Что слабо

[ТОЧНО]

- Текущий фронт монолитен: один `app.js` примерно 1680 строк и один `style.css` примерно 930 строк.
- UI собран как ручной string-render SPA, без компонентной архитектуры.
- Нет panel manager, layout engine, view registry, typed contracts и testable UI-композиции.
- Нет публичного каталога мастеров как market entity.
- Нет сущности публичной доски заявок; текущие `orders` — это уже поздняя стадия исполнения.
- Нет социальной модели: подписки, отзывы, рейтинг, портфолио, витрина, trust-маркеры, availability.
- Роли (`master`, `senior_master`, `admin`) смешивают доступы и частично орг-структуру, но не описывают рыночную репутацию мастера.
- Часть UX всё ещё Telegram-specific: inline mode, forwarded message, Telegram-only copy.
- MAX runtime в production всё ещё запущен на long polling, а не на webhook.

### 3.3. Что нельзя делать

[ТОЧНО]

- Нельзя превращать `orders` в публичную доску объявлений. Это приведёт к грязным статусам и поломанному lifecycle.
- Нельзя использовать RBAC-роли как "класс мастера". Это разные оси.
- Нельзя строить новый "оконный" UX поверх текущего монолитного `app.js` без декомпозиции.
- Нельзя делать настоящий desktop-like floating window manager как primary UX внутри mobile Mini App. Это будет красиво на концептах и неудобно в реальном MAX webview.

## 4. Критическая оценка исходной идеи пользователя

### 4.1. Идея "два окна, верх/низ, между ними resizer"

[ТОЧНО] Идея хорошая как базовый workspace pattern, но не как буквальная и единственная модель.

Правильная интерпретация:

- не "два произвольных floating окна";
- а `adaptive split workspace`:
  - верхняя рабочая зона;
  - нижняя рабочая зона;
  - между ними draggable divider;
  - сохранение layout per user + per role + per viewport;
  - дополнительные панели через drawer, sheet, overlay, full-focus mode.

[ТОЧНО] Это действительно может стать сильной основой продукта.

### 4.2. Идея "ещё одно окно меню"

[ТОЧНО] Как третье постоянное окно на mobile — плохая идея.  
[РЕКОМЕНДАЦИЯ] Меню нужно делать как:

- command palette;
- dock / side rail на больших экранах;
- bottom sheet / drawer на телефонах;
- quick actions внутри header и contextual toolbar.

### 4.3. Идея "сверху объявления, снизу мастера"

[ТОЧНО] Это хороший default preset, но не универсальный.

[РЕКОМЕНДАЦИЯ] Нужны role-aware presets:

- `client.default`:
  - top: board feed + composer;
  - bottom: recommended masters / replies / shortlist.
- `master.default`:
  - top: demand feed / invited jobs / nearby jobs;
  - bottom: network / profile leads / active deals.
- `admin.default`:
  - top: moderation + staffing + flags;
  - bottom: master network / incidents / funnel.
- `owner.default`:
  - top: market board KPIs + approvals;
  - bottom: org graph + top masters + revenue slices.

## 5. Лучшее целевое решение

## 5.1. Продуктовая форма

[PRODUCTION-GRADE] ПриДел должен стать не "ботом с web-мордой", а `service-network superapp` с тремя осями:

1. `Demand Graph`
   - публичные и полу-публичные заявки на работы;
   - подбор мастеров;
   - приглашения;
   - конверсия в смету;
   - конверсия в заказ.

2. `Master Network`
   - личные страницы мастеров;
   - навыки, портфолио, города, статус, availability;
   - уровни доверия, верификация, отзывы;
   - ветки, команды, связи senior -> master;
   - подписки / избранные / рекомендации.

3. `Operations Workspace`
   - сметы, заказы, согласования, оплаты, уведомления;
   - кадровые действия, инвайты, аналitika;
   - role-aware control center.

## 5.2. Базовый UX-каркас

[PRODUCTION-GRADE] Рекомендуемый UX shell:

- `Top Pane`
  - primary context panel;
  - feed, detail, composer, analytics block, estimate editor.
- `Bottom Pane`
  - companion context;
  - directory, shortlist, comments, related masters, inbox, queue.
- `Divider`
  - drag resize;
  - snap points: `30/70`, `40/60`, `50/50`, `60/40`, `70/30`;
  - double tap = reset to preset;
  - long press = open layout menu.
- `Command Surface`
  - command palette;
  - contextual actions;
  - pinned actions;
  - module launchers.
- `Transient Overlays`
  - profile quick peek;
  - estimate preview;
  - moderation dialog;
  - sheet-based filters;
  - full-screen focus mode.

## 5.3. Почему не настоящий PiP window manager

[ТОЧНО] Внутри MAX Mini App основная среда — mobile webview.  
[РИСК] Настоящие перекрывающиеся окна дадут:

- плохую жестовую эргономику;
- проблемы со scroll nesting;
- конфликт с системным viewport;
- слабую доступность;
- хаос на маленьких экранах.

[РЕКОМЕНДАЦИЯ] Вместо этого нужен `bounded pane system`:

- максимум 2 docked panes одновременно;
- overlays только для временных сущностей;
- desktop/web режим может разрешать 3-column layout, но не как mobile default.

## 6. Целевая информационная архитектура

## 6.1. Основные продуктовые разделы

### A. Board

Новая доменная сущность: `job_post`

Функции:

- создать объявление о работе;
- привязать к категориям каталога;
- указать город, радиус, сроки, бюджет, срочность;
- приложить фото/видео;
- показать видимость: public / city / invited-only;
- принимать отклики;
- приглашать мастеров напрямую;
- преобразовывать в estimate lead / order.

### B. Network

Новая доменная сущность: `public_master_profile`

Функции:

- публичная карточка мастера;
- специализации;
- витрина услуг;
- рейтинг, отзывов, completed jobs;
- верификация;
- география;
- доступность "свободен / занят / только по приглашению";
- портфолио;
- подписка / избранное / шортлист.

### C. Workspace

Основан на текущих модулях:

- inbox;
- dashboard;
- estimates;
- orders;
- approvals;
- payments;
- analytics;
- staffing;
- profile;
- admin functions.

## 6.2. Что переносим из текущего бота в новый Mini App

[ТОЧНО]

- `/start` workbench -> dashboard / command center;
- inbox / notifications -> отдельная панель;
- profile editor -> модуль profile/settings;
- estimates -> модуль estimate workspace;
- orders -> модуль execution;
- approvals -> модуль approvals queue;
- analytics -> owner/admin panels;
- invites / staffing / branches -> ops & org modules;
- catalog / search -> skill graph + service graph + demand tagging.

## 6.3. Что не переносим буквально

[ТОЧНО]

- Telegram inline mode;
- привязку клиента через forwarded message;
- raw callback-first UX;
- Telegram-specific copy и mental model.

## 7. Архитектура frontend

## 7.1. Рекомендуемый стек

[PRODUCTION-GRADE] Для нового Mini App рекомендован:

- React 19 + TypeScript;
- Vite build;
- TanStack Query для server state;
- Zustand или Redux Toolkit для local UI state;
- Zod для runtime validation контрактов;
- CSS variables + design tokens;
- Framer Motion или Motion One только для осмысленных переходов;
- Vitest + Testing Library;
- Playwright для critical E2E.

### Почему не оставаться на текущем vanilla SPA

[ТОЧНО]

- уже слишком много экранов и ролей;
- понадобится panel registry;
- понадобится persistent layout engine;
- понадобится typed contracts и composable modules;
- потребуется изоляция фичей по доменным пакетам.

## 7.2. Новая структура frontend

[PRODUCTION-GRADE]

```text
app/webapp/
  src/
    app/
      bootstrap/
      providers/
      router/
      shell/
        workspace-shell/
        pane-manager/
        layout-engine/
        command-surface/
        dock/
    core/
      api/
      auth/
      contracts/
      errors/
      telemetry/
      feature-flags/
      permissions/
      design-system/
      state/
      utils/
    panels/
      board-feed/
      board-detail/
      board-compose/
      masters-directory/
      master-profile/
      notifications/
      estimates/
      orders/
      approvals/
      analytics/
      profile/
      menu/
    features/
      board/
      network/
      estimates/
      orders/
      payments/
      staffing/
      invites/
      analytics/
      suggestions/
    entities/
      user/
      master-profile/
      job-post/
      estimate/
      order/
      notification/
      branch/
    shared/
      ui/
      hooks/
      lib/
      config/
```

## 7.3. Panel registry как основа "конструктора"

[PRODUCTION-GRADE]

```ts
export type PanelId =
  | 'board.feed'
  | 'board.compose'
  | 'board.detail'
  | 'network.directory'
  | 'network.profile'
  | 'workspace.inbox'
  | 'workspace.menu'
  | 'estimates.list'
  | 'estimates.detail'
  | 'orders.list'
  | 'orders.detail'
  | 'approvals.queue'
  | 'analytics.overview'
  | 'profile.settings';

export interface PanelManifest<TParams = unknown> {
  id: PanelId;
  title: string;
  featureFlag?: string;
  minHeight?: number;
  minWidth?: number;
  mobileBehavior: 'pane' | 'overlay' | 'sheet' | 'fullscreen';
  desktopBehavior: 'pane' | 'overlay' | 'column';
  permissions?: string[];
  loader?: (params: TParams) => Promise<unknown>;
  component: React.ComponentType<{ params: TParams }>;
}
```

[ТОЧНО] Новая панель должна добавляться декларативно, а не через ручной switch на 300 строк.

## 7.4. Layout engine

[PRODUCTION-GRADE]

Состояние layout:

- какие панели открыты;
- какая панель в top pane;
- какая панель в bottom pane;
- текущий split ratio;
- preset по роли;
- override пользователя;
- mobile/desktop variant;
- pinned/favorite tools;
- last context per panel.

Пример:

```ts
type WorkspaceLayout = {
  presetId: string;
  topPanel: { id: PanelId; params?: Record<string, unknown> };
  bottomPanel: { id: PanelId; params?: Record<string, unknown> };
  splitRatio: number; // 0.3..0.7
  overlays: Array<{ id: PanelId; params?: Record<string, unknown> }>;
  updatedAt: string;
};
```

## 7.5. Где хранить размер и раскладку

[PRODUCTION-GRADE] Не только в localStorage.

Нужно хранить:

- `localStorage` как быстрый cache;
- backend-профиль layout как source of truth между устройствами.

[РЕКОМЕНДАЦИЯ] Ввести таблицу `user_workspace_layouts`:

- `user_id`
- `scope` (`mobile`, `desktop`, `role:master`, `role:client`)
- `layout_json`
- `version`
- `updated_at`

Причина:

- пользователь заходит с разных устройств;
- messenger webview может сбрасывать локальный state;
- нужен rollback при битом layout;
- нужны A/B rollout и миграции layout schema.

## 7.6. UX-правила pane-resize

[PRODUCTION-GRADE]

- divider hit area не меньше 24px;
- реальная линия 1-2px, но gesture-zone шире;
- drag update через `requestAnimationFrame`;
- state commit только по `pointerup`;
- persistence через debounced save;
- snap points;
- hard min-height для pane content;
- keyboard fallback для accessibility;
- reset preset;
- orientation-aware recalculation;
- safe-area support;
- reduced-motion mode.

## 8. Дизайн-система

## 8.1. Визуальный стиль

[PRODUCTION-GRADE]

- стеклянные слои, но без грязного glassmorphism;
- полупрозрачные панели с сильной контрастной типографикой;
- холодная нейтральная база + один акцентный цвет состояния;
- чёткая иерархия depth через blur + thin stroke + shadow;
- не перегружать сиянием и "киберпанком".

### Рекомендуемое направление

- фон: многослойный градиент с очень мягкими световыми пятнами;
- surface: frosted glass;
- borders: тонкие холодные semi-transparent линии;
- typography: современный grotesk, без дефолтного system-only ощущения;
- motion: slow, precise, inertial;
- иконки: monoline / semi-rounded;
- density: compact, но не мелкая.

## 8.2. Чего нельзя делать

[ТОЧНО]

- не делать тяжёлое блюро-всё-везде;
- не делать темные полупрозрачные панели с низким contrast ratio;
- не делать мобильный интерфейс как уменьшенный desktop;
- не делать футуризм ценой читабельности.

## 8.3. Accessibility baseline

[PRODUCTION-GRADE]

- AA contrast;
- target size 44x44;
- screen-reader labels;
- keyboard traversal;
- visible focus ring;
- reduced motion;
- font scaling tolerance;
- не кодировать смысл только цветом.

## 9. Новые доменные модули, которых сейчас нет

## 9.1. `board`

Новые сущности:

- `job_posts`
- `job_post_media`
- `job_post_targets`
- `job_applications`
- `job_shortlists`
- `job_matches`

Lifecycle:

`draft -> published -> collecting_responses -> shortlisted -> matched -> estimated -> ordered -> closed`

## 9.2. `network`

Новые сущности:

- `public_profiles`
- `master_skills`
- `master_portfolio_items`
- `master_verifications`
- `master_reviews`
- `master_followers`
- `master_availability_slots`
- `master_service_areas`

## 9.3. `reputation`

Новые сущности:

- `review`
- `rating_aggregate`
- `trust_badges`
- `verification_events`

## 9.4. `workspace_layout`

Новые сущности:

- `user_workspace_layouts`
- `user_panel_prefs`
- `saved_views`

## 9.5. `recommendation`

[ВРЕМЕННОЕ РЕШЕНИЕ] На первой фазе допустим deterministic matching без ML:

- география;
- skill overlap;
- availability;
- response SLA;
- rating;
- price segment;
- branch/team trust;
- historical completion rate.

[PRODUCTION-GRADE] Позже:

- ranking service;
- offline scoring jobs;
- explainable recommendations.

## 10. Что можно переиспользовать из текущей схемы

[ТОЧНО]

- `users`, `user_roles` — остаются;
- `master_profiles` — становятся частью private profile, но недостаточны как public identity;
- `branches`, `branch_members` — пригодны как team/org graph;
- `catalog` — отлично подходит как skill taxonomy;
- `estimates`, `orders`, `payments` — остаются execution layer;
- `notifications`, `audit`, `feature_flags` — остаются платформенными модулями.

## 11. Что нужно изменить в данных

## 11.1. Не смешивать доступ и рыночный статус

[ТОЧНО]

Сейчас:

- `master`, `senior_master`, `admin`, `product_owner` = права.

Нужно отдельно:

- `access_role` = права;
- `professional_tier` = уровень;
- `verification_status` = доверие;
- `market_visibility` = видимость;
- `seller_mode` = принимает ли новые заявки.

Иначе:

- логика разрешений сломает каталог мастеров;
- "старший мастер" станет странным public label;
- продуктовые и орг-осевые статусы перепутаются.

## 11.2. Не переиспользовать `project_suggestions` как доску работ

[ТОЧНО] `project_suggestions` — это feedback в продукт, а не клиентские заявки.

## 11.3. Не переиспользовать `orders` как feed

[ТОЧНО] `orders` должны оставаться объектом исполнения, а не discovery.

## 12. API-контракты, которых не хватает

## 12.1. Board API

Нужны новые endpoints:

- `GET /api/v2/board/feed`
- `POST /api/v2/board/posts`
- `GET /api/v2/board/posts/{id}`
- `POST /api/v2/board/posts/{id}/apply`
- `POST /api/v2/board/posts/{id}/invite-master`
- `POST /api/v2/board/posts/{id}/shortlist`
- `POST /api/v2/board/posts/{id}/convert-to-estimate`

## 12.2. Network API

- `GET /api/v2/network/masters`
- `GET /api/v2/network/masters/{id}`
- `GET /api/v2/network/masters/{id}/portfolio`
- `POST /api/v2/network/masters/{id}/follow`
- `POST /api/v2/network/masters/{id}/favorite`
- `GET /api/v2/network/recommendations`

## 12.3. Workspace layout API

- `GET /api/v2/workspace/layout`
- `PUT /api/v2/workspace/layout`
- `POST /api/v2/workspace/layout/reset`
- `GET /api/v2/workspace/presets`

## 12.4. Presence and events

[PRODUCTION-GRADE]

- `GET /api/v2/events/stream` (SSE) для:
  - новых заявок;
  - откликов;
  - notification deltas;
  - approval changes;
  - presence-lite.

[РЕКОМЕНДАЦИЯ] На старте SSE лучше WebSocket:

- проще backend;
- хватает для односторонних обновлений;
- легче proxy/debug/observability.

## 13. Mapping текущих функций бота в новый интерфейс

| Текущая функция | Новый модуль | Новый panel/preset |
|---|---|---|
| `/start`, workbench | workspace | `workspace.menu`, `workspace.dashboard` |
| Каталог и поиск | catalog + network skills | `board.compose`, `catalog.browser` |
| Сметы | estimates | `estimates.list`, `estimates.detail` |
| Заказы | execution | `orders.list`, `orders.detail` |
| Согласования | approvals | `approvals.queue` |
| Профиль и реквизиты | profile | `profile.settings` |
| Уведомления | inbox | `workspace.inbox` |
| AI intake | board compose helper | `board.compose.ai-assist` |
| Инвайты и staffing | org tools | `ops.team`, `ops.invites` |
| Analytics | owner/admin | `analytics.overview` |

## 14. MAX-специфика, которую нельзя игнорировать

[ТОЧНО] По официальной документации MAX:

- `window.WebApp.initData` нужно валидировать на сервере;
- `initDataUnsafe` нельзя считать безопасным источником;
- для production рекомендуется Webhook, а не long polling;
- при активном webhook long polling не работает;
- webhook должен быть на HTTPS:443, с корректным TLS и ответом 200 за 30 секунд;
- `window.WebApp.openMaxLink(...)` можно использовать для диплинков внутри MAX;
- `window.WebApp.requestContact()` можно использовать для нативного запроса телефона;
- `window.WebApp.enableClosingConfirmation()` нужен для несохранённых данных.

[ТОЧНО] Это означает:

- основной workflow можно и нужно строить в Mini App;
- бот нужен как entrypoint, уведомления, deep links и fallback-команды;
- полноценный продукт только в чате делать не стоит.

## 15. Нефункциональные требования

## 15.1. Performance

[PRODUCTION-GRADE]

- bundle splitting по panel domains;
- route/panel lazy loading;
- виртуализация длинных списков мастеров и ленты;
- skeleton loading вместо layout shift;
- image thumb pipeline;
- debounced search;
- optimistic UI только на безопасных действиях;
- background prefetch соседних panel payloads.

## 15.2. Reliability

[PRODUCTION-GRADE]

- idempotency keys для publish/apply/invite/convert actions;
- dedupe повторных webhook/update deliveries;
- backoff на MAX API;
- fail-soft UI при сетевых сбоях;
- layout schema versioning;
- invalid layout recovery;
- feature-flag rollout на новые панели.

## 15.3. Observability

[PRODUCTION-GRADE]

- structured logs;
- API latency metrics;
- panel open/render timings;
- board feed load timings;
- save layout success/fail metrics;
- SSE disconnect metrics;
- MAX webhook delivery metrics;
- audit log на публикацию заявок, отклики, назначения, конверсию в заказ.

## 15.4. Security

[PRODUCTION-GRADE]

- server-side validation of MAX init data;
- strict permission boundaries между public network и private ops;
- PII separation for public/private profiles;
- media upload validation;
- rate limiting на publish/apply/suggestion flows;
- anti-spam и abuse controls;
- moderation flags;
- secret verification for MAX webhook (`X-Max-Bot-Api-Secret`).

## 16. Что делать по этапам

## Phase 0 — Stabilization

[ТОЧНО]

- перевести MAX bot production на webhook;
- убрать Telegram-only blockers;
- завершить MAX user registration path;
- почистить legacy copy;
- выделить contract layer для frontend.

Критерий готовности:

- production MAX работает через webhook;
- Mini App auth стабилен;
- все текущие bot-critical функции доступны через API или явно вынесены из scope.

## Phase 1 — Frontend Replatform

- ввести React + TS frontend shell;
- реализовать panel registry;
- реализовать adaptive split workspace;
- перенести dashboard, notifications, profile, menu;
- перенести estimates/orders как первые production panels.

Критерий:

- новый shell работает в MAX;
- split ratio сохраняется;
- 2-pane UX стабилен на mobile;
- есть fallback fullscreen mode.

## Phase 2 — Board + Network Foundation

- `job_posts`;
- `public_profiles`;
- master directory;
- board feed;
- shortlist / apply / invite;
- conversion to estimate.

Критерий:

- клиент публикует запрос;
- мастер видит релевантный feed;
- мастер откликается;
- клиент шортлистит;
- лид конвертируется в estimate.

## Phase 3 — Trust and Reputation

- reviews;
- verification;
- badges;
- response SLA;
- availability;
- portfolio.

Критерий:

- профиль мастера становится достаточным для выбора без внешнего общения.

## Phase 4 — Social Layer

- follows;
- collections;
- recommendation feed;
- team pages;
- reusable saved searches;
- invite chains.

## Phase 5 — Advanced Ops

- live event stream;
- richer analytics;
- cross-team staffing graph;
- moderation cockpit;
- experiment framework for layouts.

## 17. Что добавить сверх очевидного

[PRODUCTION-GRADE]

- role-based layout presets;
- market mode vs operations mode;
- explicit separation `job_post` vs `order`;
- layout persistence on backend;
- declarative panel manifests;
- separate public/private profile surfaces;
- recommendation-ready schema from day one;
- webhook-first MAX production path;
- module rollout through feature flags.

## 18. Главные риски и failure modes

### Risk 1: Пытаемся впихнуть весь продукт в один универсальный экран

Последствие:

- перегруженность;
- сложный onboarding;
- медленный UI;
- хаос в навигации.

Снижение риска:

- panel manifests;
- role presets;
- focus mode;
- progressive disclosure.

### Risk 2: Путаем операционный и рыночный слои

Последствие:

- грязные статусы;
- сломанные отчёты;
- слабая продуктовая аналитика.

Снижение риска:

- отдельные сущности `job_post`, `application`, `match`, `order`.

### Risk 3: Делаем "футуристично", но неудобно

Последствие:

- низкая конверсия;
- слабая читаемость;
- высокий bounce.

Снижение риска:

- mobile-first ergonomics;
- glass only as surface treatment;
- usability tests;
- reduced motion.

### Risk 4: Слишком рано строим внутренний чат

[РЕКОМЕНДАЦИЯ] Не делать internal chat в первой волне.  
Использовать:

- MAX bot / dialog as notification and re-entry mechanism;
- заявки, отклики, комментарии и structured actions внутри Mini App.

Причина:

- внутренний чат резко поднимает сложность доставки, presence, unread-state, moderation, attachments и abuse-handling.

## 19. Что я рекомендую убрать или поменять в исходном видении

[ТОЧНО]

- убрать идею постоянного третьего окна меню на mobile;
- убрать идею настоящих floating PiP окон как core interaction model;
- убрать смешение "соцсеть" и "орг-иерархия" в одной оси ролей;
- убрать попытку перенести Telegram UX буквально;
- убрать мысль, что можно построить мировой продукт только на красивом интерфейсе без trust/reputation/data model.

[РЕКОМЕНДАЦИЯ]

- оставить 2-pane workspace как основу;
- сделать menu как command surface;
- сделать board + network как public discovery layer;
- сделать estimates/orders/payments как execution layer;
- сделать separate trust layer.

## 20. Почему это не игрушечное решение

[ТОЧНО]

- решение опирается на реальный аудит текущего кода;
- учитывает реальные ограничения MAX;
- не смешивает продуктовые сущности;
- предлагает не просто дизайн, а новую доменную модель;
- закрывает архитектуру, данные, API, UX, эксплуатацию, rollout, риски и миграцию;
- сохраняет текущее сильное ядро и не предлагает "переписать всё ради красоты".

## 21. Что считать production-grade на следующем шаге

[PRODUCTION-GRADE] Следующий шаг разработки должен быть не "рисуем красивые стёкла", а:

1. утвердить новую доменную модель (`job_post`, `public_profile`, `layout`);
2. утвердить frontend replatform на typed component architecture;
3. перевести MAX на webhook;
4. реализовать новый shell и первые panel manifests;
5. только потом переносить фичи пачками.

## 22. Что требует уточнения

[ТРЕБУЕТ ПРОВЕРКИ]

- точный GitHub-репозиторий `arbilab`, который пользователь имел в виду; публичным поиском его однозначно идентифицировать не удалось;
- приоритет первой аудитории:
  - клиентский маркетплейс;
  - сеть мастеров;
  - внутренняя ops-панель;
- необходимость geo search и карт в первой волне;
- нужна ли публичная веб-версия вне MAX или только Mini App.

## 23. Прямой вывод

[ТОЧНО] Лучший путь — не "переносить бота в web", а строить `adaptive split-pane superapp`:

- board сверху как спрос и конверсия;
- network снизу как supply и trust;
- command surface вместо третьего окна;
- текущие estimates/orders/payments как execution core;
- новые social modules как discovery/trust layer;
- новая фронтенд-архитектура как panel-based constructor.

[PRODUCTION-GRADE] Именно этот путь даёт шанс сделать продукт сильнее обычного сервиса мастеров, а не просто ещё один чат-бот с кнопками.
