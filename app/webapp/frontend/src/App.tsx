import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Group, Panel, Separator } from "react-resizable-panels";
import { z } from "zod";

import { api, ApiError } from "./api";
import { prepareBridge } from "./bridge";
import { useWorkspaceStore } from "./store";
import type {
  BootstrapResponse,
  CatalogItem,
  EstimateSummary,
  JobPost,
  MasterCard,
  NotificationItem,
  OrderSummary,
  PaneId,
  PanelMeta,
  PublicProfileResponse,
} from "./types";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const boardPostSchema = z.object({
  title: z.string().min(4).max(160),
  description: z.string().min(12).max(1200),
  city: z.string().max(120).optional(),
  budget_from: z.number().int().nonnegative().nullable(),
  budget_to: z.number().int().nonnegative().nullable(),
  urgency: z.enum(["normal", "urgent", "asap"]),
});

function money(value?: number | null): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(value ?? 0);
}

function formatAgo(value?: string | null): string {
  if (!value) {
    return "сейчас";
  }
  const diffMinutes = Math.max(1, Math.floor((Date.now() - new Date(value).getTime()) / 60_000));
  if (diffMinutes < 60) {
    return `${diffMinutes} мин назад`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} ч назад`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} д назад`;
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    open: "Открыта",
    submitted: "Новая",
    draft: "Черновик",
    client_review: "У клиента",
    approved: "Согласована",
    assigned: "Назначен мастер",
    in_progress: "В работе",
    completed: "Завершён",
    paid: "Оплачен",
    urgent: "Срочно",
    busy: "Занят",
    offline: "Оффлайн",
  };
  return map[status] ?? status;
}

function toneClass(status: string): string {
  if (["open", "approved", "paid"].includes(status)) {
    return "tone-success";
  }
  if (["urgent", "asap", "busy", "client_review"].includes(status)) {
    return "tone-warn";
  }
  if (["offline", "cancelled"].includes(status)) {
    return "tone-muted";
  }
  return "tone-neutral";
}

function Glyph({ name }: { name: string }) {
  switch (name) {
    case "users":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
          <path d="M16 11a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
          <path d="M3.5 19a4.5 4.5 0 0 1 9 0" />
          <path d="M13 19a3.5 3.5 0 0 1 7 0" />
        </svg>
      );
    case "grid":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="4" y="4" width="6" height="6" rx="1.5" />
          <rect x="14" y="4" width="6" height="6" rx="1.5" />
          <rect x="4" y="14" width="6" height="6" rx="1.5" />
          <rect x="14" y="14" width="6" height="6" rx="1.5" />
        </svg>
      );
    case "receipt":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 4h10v16l-2-1.5L12 20l-3-1.5L7 20V4Z" />
          <path d="M9 9h6" />
          <path d="M9 13h6" />
        </svg>
      );
    case "briefcase":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3" y="7" width="18" height="12" rx="2" />
          <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          <path d="M3 12h18" />
        </svg>
      );
    case "bell":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 9a6 6 0 1 1 12 0c0 6 2 8 2 8H4s2-2 2-8Z" />
          <path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
      );
    case "chart":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 19V5" />
          <path d="M4 19h16" />
          <path d="M8 15v-4" />
          <path d="M12 15V8" />
          <path d="M16 15v-6" />
        </svg>
      );
    case "check":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m5 13 4 4L19 7" />
        </svg>
      );
    case "id":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <circle cx="9" cy="11" r="2.5" />
          <path d="M14 10h4" />
          <path d="M14 14h4" />
        </svg>
      );
    case "spark":
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="5" y="5" width="14" height="14" rx="3" />
        </svg>
      );
  }
}

function PanelPicker({
  value,
  options,
  onChange,
}: {
  value: string;
  options: PanelMeta[];
  onChange: (next: string) => void;
}) {
  return (
    <label className="panel-picker">
      <span>Панель</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.title}
          </option>
        ))}
      </select>
    </label>
  );
}

function SectionCard({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="section-card">
      <header className="section-head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="section-actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

function EmptyState({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{subtitle}</p>
    </div>
  );
}

function BoardPanel({
  externalUserId,
  bootstrap,
}: {
  externalUserId: number;
  bootstrap: BootstrapResponse;
}) {
  const queryClient = useQueryClient();
  const [composerOpen, setComposerOpen] = useState(false);
  const [responsePostId, setResponsePostId] = useState<number | null>(null);
  const [responseMessage, setResponseMessage] = useState("");
  const [responsePrice, setResponsePrice] = useState("");
  const [formState, setFormState] = useState({
    title: "",
    description: "",
    city: "",
    budget_from: "",
    budget_to: "",
    urgency: "normal",
  });

  const postsQuery = useQuery({
    queryKey: ["board-posts", externalUserId],
    queryFn: () => api.listBoardPosts(externalUserId),
    initialData: {
      items: bootstrap.board.items,
      meta: { limit: 20, offset: 0 },
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const parsed = boardPostSchema.parse({
        title: formState.title,
        description: formState.description,
        city: formState.city || undefined,
        budget_from: formState.budget_from ? Number(formState.budget_from) : null,
        budget_to: formState.budget_to ? Number(formState.budget_to) : null,
        urgency: formState.urgency,
      });
      return api.createBoardPost(externalUserId, parsed);
    },
    onSuccess: async () => {
      setComposerOpen(false);
      setFormState({
        title: "",
        description: "",
        city: "",
        budget_from: "",
        budget_to: "",
        urgency: "normal",
      });
      await queryClient.invalidateQueries({ queryKey: ["board-posts", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  const respondMutation = useMutation({
    mutationFn: async (postId: number) =>
      api.respondBoardPost(externalUserId, postId, {
        message: responseMessage,
        price_offer: responsePrice ? Number(responsePrice) : null,
      }),
    onSuccess: async () => {
      setResponsePostId(null);
      setResponseMessage("");
      setResponsePrice("");
      await queryClient.invalidateQueries({ queryKey: ["board-posts", externalUserId] });
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard
        title="Доска спроса"
        subtitle="Лёгкая лента заявок без визуального шума."
        actions={
          bootstrap.capabilities.can_post_jobs ? (
            <button className="btn btn-primary" onClick={() => setComposerOpen((value) => !value)}>
              {composerOpen ? "Скрыть" : "Новая заявка"}
            </button>
          ) : null
        }
      >
        {composerOpen ? (
          <form
            className="stack-form"
            onSubmit={(event) => {
              event.preventDefault();
              void createMutation.mutateAsync();
            }}
          >
            <input
              className="input"
              placeholder="Что нужно сделать"
              value={formState.title}
              onChange={(event) => setFormState((state) => ({ ...state, title: event.target.value }))}
            />
            <textarea
              className="textarea"
              placeholder="Коротко опишите задачу, объём, место и ожидания"
              value={formState.description}
              onChange={(event) =>
                setFormState((state) => ({ ...state, description: event.target.value }))
              }
            />
            <div className="row-grid">
              <input
                className="input"
                placeholder="Город"
                value={formState.city}
                onChange={(event) => setFormState((state) => ({ ...state, city: event.target.value }))}
              />
              <select
                className="input"
                value={formState.urgency}
                onChange={(event) => setFormState((state) => ({ ...state, urgency: event.target.value }))}
              >
                <option value="normal">Спокойно</option>
                <option value="urgent">Скоро</option>
                <option value="asap">Как можно быстрее</option>
              </select>
            </div>
            <div className="row-grid">
              <input
                className="input"
                type="number"
                min="0"
                placeholder="Бюджет от"
                value={formState.budget_from}
                onChange={(event) =>
                  setFormState((state) => ({ ...state, budget_from: event.target.value }))
                }
              />
              <input
                className="input"
                type="number"
                min="0"
                placeholder="Бюджет до"
                value={formState.budget_to}
                onChange={(event) =>
                  setFormState((state) => ({ ...state, budget_to: event.target.value }))
                }
              />
            </div>
            {createMutation.error ? (
              <p className="inline-error">{(createMutation.error as ApiError).message}</p>
            ) : null}
            <div className="action-row">
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Публикуем..." : "Опубликовать"}
              </button>
            </div>
          </form>
        ) : null}
      </SectionCard>

      <div className="card-list">
        {postsQuery.data?.items.length ? (
          postsQuery.data.items.map((post: JobPost) => (
            <article key={post.id} className="glass-card board-card">
              <div className="card-topline">
                <span className={`pill ${toneClass(post.urgency)}`}>{statusLabel(post.urgency)}</span>
                <span className="muted">{formatAgo(post.created_at)}</span>
              </div>
              <h4>{post.title}</h4>
              <p>{post.description}</p>
              <div className="meta-cloud">
                {post.city ? <span>{post.city}</span> : null}
                {post.budget ? (
                  <span>
                    {post.budget.from ? `от ${money(post.budget.from)} ` : ""}
                    {post.budget.to ? `до ${money(post.budget.to)}` : ""}
                  </span>
                ) : null}
                <span>{post.response_count} откликов</span>
              </div>
              {post.can_respond ? (
                <>
                  {responsePostId === post.id ? (
                    <div className="inline-composer">
                      <textarea
                        className="textarea compact"
                        placeholder="Коротко: как возьмёте задачу, когда сможете и что важно учесть"
                        value={responseMessage}
                        onChange={(event) => setResponseMessage(event.target.value)}
                      />
                      <input
                        className="input"
                        type="number"
                        min="0"
                        placeholder="Цена, если хотите указать"
                        value={responsePrice}
                        onChange={(event) => setResponsePrice(event.target.value)}
                      />
                      {respondMutation.error ? (
                        <p className="inline-error">{(respondMutation.error as ApiError).message}</p>
                      ) : null}
                      <div className="action-row">
                        <button
                          className="btn btn-primary"
                          onClick={() => void respondMutation.mutateAsync(post.id)}
                          disabled={respondMutation.isPending}
                        >
                          {respondMutation.isPending ? "Отправляем..." : "Отправить отклик"}
                        </button>
                        <button className="btn" onClick={() => setResponsePostId(null)}>
                          Отмена
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button className="btn" onClick={() => setResponsePostId(post.id)}>
                      Откликнуться
                    </button>
                  )}
                </>
              ) : null}
            </article>
          ))
        ) : (
          <EmptyState
            title="Пока нет публичных заявок"
            subtitle="Начните с одной ясной публикации: короткий текст, город и желаемый бюджет."
          />
        )}
      </div>
    </div>
  );
}

function NetworkPanel({
  externalUserId,
  bootstrap,
  onOpenMaster,
}: {
  externalUserId: number;
  bootstrap: BootstrapResponse;
  onOpenMaster: (externalUserId: number) => void;
}) {
  const [queryText, setQueryText] = useState("");
  const [availability, setAvailability] = useState("open");
  const mastersQuery = useQuery({
    queryKey: ["masters", externalUserId, queryText, availability],
    queryFn: () =>
      api.listMasters(externalUserId, {
        q: queryText || undefined,
        availability: availability === "all" ? undefined : availability,
      }),
    initialData: {
      items: bootstrap.network.items,
      meta: { limit: 20, offset: 0 },
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Сеть мастеров" subtitle="Спокойная витрина специалистов без перегруза.">
        <div className="stack-form compact-stack">
          <input
            className="input"
            placeholder="Имя, специализация, город"
            value={queryText}
            onChange={(event) => setQueryText(event.target.value)}
          />
          <div className="segmented">
            {[
              { id: "open", label: "Свободны" },
              { id: "busy", label: "Заняты" },
              { id: "all", label: "Все" },
            ].map((item) => (
              <button
                key={item.id}
                className={`segment ${availability === item.id ? "active" : ""}`}
                onClick={() => setAvailability(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </SectionCard>
      <div className="card-list">
        {mastersQuery.data?.items.length ? (
          mastersQuery.data.items.map((master: MasterCard) => (
            <article key={master.external_user_id} className="glass-card master-card">
              <div className="master-accent" style={{ background: master.accent_color }} />
              <div className="card-topline">
                <span className={`pill ${toneClass(master.availability_status)}`}>
                  {statusLabel(master.availability_status)}
                </span>
                <span className="muted">{master.completed_jobs} завершено</span>
              </div>
              <h4>{master.name}</h4>
              <p className="card-title">{master.title}</p>
              {master.bio ? <p>{master.bio}</p> : null}
              <div className="meta-cloud">
                {master.city ? <span>{master.city}</span> : null}
                {master.experience_years ? <span>{master.experience_years}+ лет</span> : null}
                {master.hourly_rate_from ? <span>от {money(master.hourly_rate_from)}</span> : null}
              </div>
              <div className="tag-row">
                {master.skills.slice(0, 4).map((skill) => (
                  <span key={skill} className="tag">
                    {skill}
                  </span>
                ))}
              </div>
              <button className="btn" onClick={() => onOpenMaster(master.external_user_id)}>
                Открыть страницу
              </button>
            </article>
          ))
        ) : (
          <EmptyState
            title="Сеть пока пустая"
            subtitle="Как только мастера опубликуют свои страницы, они появятся здесь в один поток."
          />
        )}
      </div>
    </div>
  );
}

function WorkspacePanel({
  bootstrap,
  onFocusPanel,
}: {
  bootstrap: BootstrapResponse;
  onFocusPanel: (pane: PaneId, panelId: string) => void;
}) {
  const metrics = [
    { label: "Сметы", value: bootstrap.workspace.active_estimates },
    { label: "Заказы", value: bootstrap.workspace.active_orders },
    { label: "Нужно решить", value: bootstrap.workspace.pending_approvals },
    { label: "Сигналы", value: bootstrap.notifications.unread },
  ];

  return (
    <div className="panel-stack">
      <SectionCard title="Рабочий стол" subtitle="Только то, что реально требует внимания сейчас.">
        <div className="metric-grid">
          {metrics.map((metric) => (
            <div key={metric.label} className="metric-card">
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </SectionCard>

      {bootstrap.workspace.onboarding.length ? (
        <SectionCard title="Подготовить основу" subtitle="Несколько шагов, которые повышают доверие и конверсию.">
          <div className="task-list">
            {bootstrap.workspace.onboarding.map((task) => (
              <button
                key={task.id}
                className="task-card"
                onClick={() => onFocusPanel("bottom", "profile-card")}
              >
                <strong>{task.title}</strong>
                <span>{task.description}</span>
              </button>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title="Быстрый маршрут" subtitle="Переключение без блуждания по меню.">
        <div className="quick-grid">
          {[
            { label: "Каталог сверху", pane: "top" as PaneId, panel: "catalog-browser" },
            { label: "Сметы снизу", pane: "bottom" as PaneId, panel: "estimates-list" },
            { label: "Заказы сверху", pane: "top" as PaneId, panel: "orders-list" },
            { label: "Профиль снизу", pane: "bottom" as PaneId, panel: "profile-card" },
          ].map((item) => (
            <button key={item.label} className="quick-card" onClick={() => onFocusPanel(item.pane, item.panel)}>
              {item.label}
            </button>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

function CatalogPanel({
  externalUserId,
  canCreateEstimate,
}: {
  externalUserId: number;
  canCreateEstimate: boolean;
}) {
  const queryClient = useQueryClient();
  const [queryText, setQueryText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const searchQuery = useQuery({
    queryKey: ["catalog-search", externalUserId, queryText],
    queryFn: () => api.searchCatalog(externalUserId, queryText),
    enabled: queryText.trim().length >= 2,
  });

  const addItemMutation = useMutation({
    mutationFn: async (item: CatalogItem) => {
      const cached = queryClient.getQueryData<EstimateSummary[]>(["estimates", externalUserId]) ?? [];
      let draft = cached.find((estimate) => estimate.status === "draft");
      if (!draft) {
        const created = await api.createEstimate(externalUserId);
        draft = {
          id: created.id,
          status: created.status,
          version: 1,
          total: 0,
          discount: 0,
          final: 0,
          client_id: null,
          master_id: null,
          created_at: null,
        };
      }
      await api.addEstimateItem(externalUserId, draft.id, item.id);
      return draft.id;
    },
    onSuccess: async (estimateId) => {
      setStatus(`Добавлено в смету #${estimateId}`);
      await queryClient.invalidateQueries({ queryKey: ["estimates", externalUserId] });
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Каталог" subtitle="Чистый поиск по работам без длинной навигации.">
        <input
          className="input"
          placeholder="Например: розетка, люстра, смеситель"
          value={queryText}
          onChange={(event) => setQueryText(event.target.value)}
        />
        {status ? <p className="inline-success">{status}</p> : null}
      </SectionCard>
      <div className="card-list">
        {queryText.trim().length < 2 ? (
          <EmptyState
            title="Начните с 2 символов"
            subtitle="Интерфейс остаётся лёгким и не грузит результаты заранее."
          />
        ) : searchQuery.data?.length ? (
          searchQuery.data.map((item) => (
            <article key={item.id} className="glass-card compact-card">
              <div>
                <h4>{item.name}</h4>
                <p>
                  {money(item.price || item.price_min)} / {item.unit}
                </p>
              </div>
              {canCreateEstimate ? (
                <button className="btn" onClick={() => void addItemMutation.mutateAsync(item)}>
                  В смету
                </button>
              ) : null}
            </article>
          ))
        ) : (
          <EmptyState
            title="Ничего не нашли"
            subtitle="Попробуйте более общий запрос или короткое название работы."
          />
        )}
      </div>
    </div>
  );
}

function EstimatesPanel({ externalUserId }: { externalUserId: number }) {
  const estimatesQuery = useQuery({
    queryKey: ["estimates", externalUserId],
    queryFn: () => api.listEstimates(externalUserId),
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Сметы" subtitle="Черновики и уже согласованные предложения." />
      <div className="card-list">
        {estimatesQuery.data?.length ? (
          estimatesQuery.data.map((estimate) => (
            <article key={estimate.id} className="glass-card compact-card">
              <div>
                <div className="card-topline">
                  <span className={`pill ${toneClass(estimate.status)}`}>{statusLabel(estimate.status)}</span>
                  <span className="muted">v{estimate.version}</span>
                </div>
                <h4>Смета #{estimate.id}</h4>
                <p>{money(estimate.final)} ₽ итогом</p>
              </div>
              <span className="muted">{formatAgo(estimate.created_at)}</span>
            </article>
          ))
        ) : (
          <EmptyState title="Смет пока нет" subtitle="Каталог и доска помогут создать первую смету без лишних шагов." />
        )}
      </div>
    </div>
  );
}

function OrdersPanel({ externalUserId }: { externalUserId: number }) {
  const ordersQuery = useQuery({
    queryKey: ["orders", externalUserId],
    queryFn: () => api.listOrders(externalUserId),
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Заказы" subtitle="Сжатый поток активной работы и истории." />
      <div className="card-list">
        {ordersQuery.data?.length ? (
          ordersQuery.data.map((order: OrderSummary) => (
            <article key={order.id} className="glass-card compact-card">
              <div>
                <div className="card-topline">
                  <span className={`pill ${toneClass(order.status)}`}>{statusLabel(order.status)}</span>
                  {order.estimate_id ? <span className="muted">из сметы #{order.estimate_id}</span> : null}
                </div>
                <h4>Заказ #{order.id}</h4>
                <p>{order.address || "Адрес пока не указан"}</p>
              </div>
              <span className="muted">{formatAgo(order.created_at)}</span>
            </article>
          ))
        ) : (
          <EmptyState title="Заказов пока нет" subtitle="Они появятся здесь после согласования смет и запуска работ." />
        )}
      </div>
    </div>
  );
}

function NotificationsPanel({ externalUserId }: { externalUserId: number }) {
  const queryClient = useQueryClient();
  const notificationsQuery = useQuery({
    queryKey: ["notifications", externalUserId],
    queryFn: () => api.listNotifications(externalUserId),
  });
  const readMutation = useMutation({
    mutationFn: async (notificationId: number) => api.markNotificationRead(externalUserId, notificationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["notifications", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Уведомления" subtitle="Только значимые события, без шумового канала." />
      <div className="card-list">
        {notificationsQuery.data?.length ? (
          notificationsQuery.data.map((notification: NotificationItem) => (
            <article key={notification.id} className="glass-card">
              <div className="card-topline">
                <span className={`pill ${notification.is_unread ? "tone-warn" : "tone-muted"}`}>
                  {notification.is_unread ? "Новое" : "Прочитано"}
                </span>
                <span className="muted">{formatAgo(notification.created_at)}</span>
              </div>
              <h4>{notification.title}</h4>
              <p>{notification.body}</p>
              {notification.is_unread ? (
                <button className="btn" onClick={() => void readMutation.mutateAsync(notification.id)}>
                  Отметить прочитанным
                </button>
              ) : null}
            </article>
          ))
        ) : (
          <EmptyState title="Пусто" subtitle="Когда появятся реальные события, они всплывут здесь компактной лентой." />
        )}
      </div>
    </div>
  );
}

function ProfilePanel({
  externalUserId,
  canPublishMasterProfile,
}: {
  externalUserId: number;
  canPublishMasterProfile: boolean;
}) {
  const queryClient = useQueryClient();
  const profileQuery = useQuery({
    queryKey: ["profile", externalUserId],
    queryFn: () => api.getProfile(externalUserId),
  });
  const publicProfileQuery = useQuery({
    queryKey: ["public-profile", externalUserId],
    queryFn: () => api.getPublicProfile(externalUserId),
    enabled: canPublishMasterProfile,
  });
  const [basicForm, setBasicForm] = useState({
    full_name: "",
    phone: "",
    specialization: "",
  });
  const [publicForm, setPublicForm] = useState({
    headline: "",
    city: "",
    bio: "",
    availability_status: "open",
    skills: "",
    is_public: false,
    accent_color: "#95c7ff",
  });

  useEffect(() => {
    if (profileQuery.data) {
      setBasicForm({
        full_name: profileQuery.data.full_name || "",
        phone: profileQuery.data.phone || "",
        specialization: profileQuery.data.specialization || "",
      });
    }
  }, [profileQuery.data]);

  useEffect(() => {
    const data = publicProfileQuery.data;
    if (data) {
      setPublicForm({
        headline: data.edit.headline || "",
        city: data.edit.city || "",
        bio: data.edit.bio || "",
        availability_status: data.edit.availability_status || "open",
        skills: data.edit.skills.join(", "),
        is_public: data.edit.is_public,
        accent_color: data.edit.accent_color || "#95c7ff",
      });
    }
  }, [publicProfileQuery.data]);

  const saveBasicMutation = useMutation({
    mutationFn: () => api.updateProfile(externalUserId, basicForm),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["profile", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  const savePublicMutation = useMutation({
    mutationFn: () =>
      api.updatePublicProfile(externalUserId, {
        headline: publicForm.headline,
        city: publicForm.city,
        bio: publicForm.bio,
        availability_status: publicForm.availability_status,
        skills: publicForm.skills
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        is_public: publicForm.is_public,
        accent_color: publicForm.accent_color,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["public-profile", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["masters"] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Основной профиль" subtitle="Минимум полей, которые реально нужны продукту.">
        <div className="stack-form">
          <input
            className="input"
            placeholder="Как вас отображать"
            value={basicForm.full_name}
            onChange={(event) => setBasicForm((state) => ({ ...state, full_name: event.target.value }))}
          />
          <div className="row-grid">
            <input
              className="input"
              placeholder="Телефон"
              value={basicForm.phone}
              onChange={(event) => setBasicForm((state) => ({ ...state, phone: event.target.value }))}
            />
            <input
              className="input"
              placeholder="Специализация"
              value={basicForm.specialization}
              onChange={(event) =>
                setBasicForm((state) => ({ ...state, specialization: event.target.value }))
              }
            />
          </div>
          <div className="action-row">
            <button className="btn btn-primary" onClick={() => void saveBasicMutation.mutateAsync()}>
              Сохранить
            </button>
          </div>
        </div>
      </SectionCard>

      {canPublishMasterProfile ? (
        <SectionCard title="Публичная страница мастера" subtitle="Это ваша витрина в сети мастеров.">
          <div className="stack-form">
            <input
              className="input"
              placeholder="Короткий заголовок"
              value={publicForm.headline}
              onChange={(event) => setPublicForm((state) => ({ ...state, headline: event.target.value }))}
            />
            <div className="row-grid">
              <input
                className="input"
                placeholder="Город"
                value={publicForm.city}
                onChange={(event) => setPublicForm((state) => ({ ...state, city: event.target.value }))}
              />
              <select
                className="input"
                value={publicForm.availability_status}
                onChange={(event) =>
                  setPublicForm((state) => ({ ...state, availability_status: event.target.value }))
                }
              >
                <option value="open">Свободен</option>
                <option value="busy">Занят</option>
                <option value="offline">Скрыт</option>
              </select>
            </div>
            <textarea
              className="textarea"
              placeholder="2–3 предложения о вашем стиле работы"
              value={publicForm.bio}
              onChange={(event) => setPublicForm((state) => ({ ...state, bio: event.target.value }))}
            />
            <input
              className="input"
              placeholder="Навыки через запятую"
              value={publicForm.skills}
              onChange={(event) => setPublicForm((state) => ({ ...state, skills: event.target.value }))}
            />
            <div className="row-grid">
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={publicForm.is_public}
                  onChange={(event) => setPublicForm((state) => ({ ...state, is_public: event.target.checked }))}
                />
                <span>Показывать в сети</span>
              </label>
              <input
                className="input"
                placeholder="#95c7ff"
                value={publicForm.accent_color}
                onChange={(event) =>
                  setPublicForm((state) => ({ ...state, accent_color: event.target.value }))
                }
              />
            </div>
            <div className="action-row">
              <button className="btn btn-primary" onClick={() => void savePublicMutation.mutateAsync()}>
                Обновить страницу
              </button>
            </div>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}

function ApprovalsPanel({ externalUserId }: { externalUserId: number }) {
  const approvalsQuery = useQuery({
    queryKey: ["approvals", externalUserId],
    queryFn: () => api.listApprovals(externalUserId),
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Согласования" subtitle="Живая очередь решений без перегрузки деталями." />
      <div className="card-list">
        {approvalsQuery.data?.length ? (
          approvalsQuery.data.map((approval) => (
            <article key={approval.id} className="glass-card compact-card">
              <div>
                <div className="card-topline">
                  <span className={`pill ${toneClass(approval.status)}`}>{statusLabel(approval.status)}</span>
                  <span className="muted">Смета #{approval.estimate_id}</span>
                </div>
                <h4>Запрос #{approval.id}</h4>
                <p>{approval.type}: {approval.value}</p>
              </div>
              <span className="muted">{formatAgo(approval.created_at)}</span>
            </article>
          ))
        ) : (
          <EmptyState title="Очередь чистая" subtitle="Сейчас нет скидок или решений, которые требуют вашего участия." />
        )}
      </div>
    </div>
  );
}

function AnalyticsPanel({ externalUserId }: { externalUserId: number }) {
  const analyticsQuery = useQuery({
    queryKey: ["analytics", externalUserId],
    queryFn: () => api.getAnalytics(externalUserId),
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Аналитика платформы" subtitle="Одна плоскость для экономики и воронки.">
        {analyticsQuery.data ? (
          <div className="metric-grid dense">
            {[
              { label: "Пользователи", value: analyticsQuery.data.users },
              { label: "Мастера", value: analyticsQuery.data.masters },
              { label: "Сметы", value: analyticsQuery.data.estimates },
              { label: "Заказы", value: analyticsQuery.data.orders },
              { label: "Оборот", value: money(analyticsQuery.data.gross) },
              { label: "Чистый доход", value: money(analyticsQuery.data.platform_net) },
            ].map((metric) => (
              <div key={metric.label} className="metric-card">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Считаем..." subtitle="Аналитика появится сразу после ответа сервера." />
        )}
      </SectionCard>
    </div>
  );
}

function CommandPalette({
  open,
  panels,
  onClose,
  onSelect,
}: {
  open: boolean;
  panels: PanelMeta[];
  onClose: () => void;
  onSelect: (pane: PaneId, panelId: string) => void;
}) {
  const [targetPane, setTargetPane] = useState<PaneId>("top");
  const grouped = useMemo(() => {
    return panels.reduce<Record<string, PanelMeta[]>>((acc, panel) => {
      acc[panel.group] = acc[panel.group] || [];
      acc[panel.group].push(panel);
      return acc;
    }, {});
  }, [panels]);

  if (!open) {
    return null;
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="palette" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>Меню панелей</h3>
            <p>Добавляйте функции в нужное окно без перегруженной навигации.</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <div className="segmented">
          <button className={`segment ${targetPane === "top" ? "active" : ""}`} onClick={() => setTargetPane("top")}>
            Верхнее окно
          </button>
          <button className={`segment ${targetPane === "bottom" ? "active" : ""}`} onClick={() => setTargetPane("bottom")}>
            Нижнее окно
          </button>
        </div>
        <div className="palette-groups">
          {Object.entries(grouped).map(([group, items]) => (
            <section key={group} className="palette-group">
              <strong>{group}</strong>
              <div className="quick-grid">
                {items.map((panel) => (
                  <button
                    key={panel.id}
                    className="quick-card"
                    onClick={() => {
                      onSelect(targetPane, panel.id);
                      onClose();
                    }}
                  >
                    {panel.title}
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

function MasterDrawer({
  externalUserId,
  selectedMasterId,
  onClose,
}: {
  externalUserId: number;
  selectedMasterId: number | null;
  onClose: () => void;
}) {
  const masterQuery = useQuery({
    queryKey: ["master", externalUserId, selectedMasterId],
    queryFn: () => api.getMaster(externalUserId, selectedMasterId as number),
    enabled: selectedMasterId !== null,
  });

  if (selectedMasterId === null) {
    return null;
  }

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>{masterQuery.data?.name || "Мастер"}</h3>
            <p>{masterQuery.data?.title || "Профиль"}</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        {masterQuery.data ? (
          <div className="panel-stack">
            <div className="glass-card">
              <div className="meta-cloud">
                {masterQuery.data.city ? <span>{masterQuery.data.city}</span> : null}
                <span>{masterQuery.data.completed_jobs} завершённых работ</span>
                <span>{statusLabel(masterQuery.data.availability_status)}</span>
              </div>
              <p>{masterQuery.data.bio || "Профиль пока без описания."}</p>
            </div>
            <div className="tag-row">
              {masterQuery.data.skills.map((skill) => (
                <span key={skill} className="tag">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState title="Загружаем профиль" subtitle="Сейчас подтянем все публичные данные мастера." />
        )}
      </aside>
    </div>
  );
}

function PaneSurface({
  paneId,
  panelId,
  title,
  icon,
  panels,
  onChange,
  children,
}: {
  paneId: PaneId;
  panelId: string;
  title: string;
  icon: string;
  panels: PanelMeta[];
  onChange: (pane: PaneId, panelId: string) => void;
  children: ReactNode;
}) {
  return (
    <section className="pane-surface">
      <header className="pane-head">
        <div className="pane-title">
          <span className="glyph-shell">
            <Glyph name={icon} />
          </span>
          <div>
            <span className="pane-label">{paneId === "top" ? "Верхнее окно" : "Нижнее окно"}</span>
            <h2>{title}</h2>
          </div>
        </div>
        <PanelPicker value={panelId} options={panels} onChange={(next) => onChange(paneId, next)} />
      </header>
      <div className="pane-content">{children}</div>
    </section>
  );
}

function Shell({ auth, bootstrap }: { auth: { telegram_id: number; name: string }; bootstrap: BootstrapResponse }) {
  const externalUserId = auth.telegram_id;
  const {
    layout,
    panels,
    presets,
    bootstrap: bootState,
    commandOpen,
    hydrateFromBootstrap,
    replaceLayout,
    setPanePanel,
    setRatio,
    setCommandOpen,
  } = useWorkspaceStore();
  const [selectedMasterId, setSelectedMasterId] = useState<number | null>(null);
  const layoutSaveRef = useRef<string | null>(null);
  const panelLookup = useMemo(
    () => new Map(panels.map((panel) => [panel.id, panel])),
    [panels],
  );

  useEffect(() => {
    hydrateFromBootstrap(bootstrap);
    layoutSaveRef.current = JSON.stringify(bootstrap.layout);
  }, [bootstrap, hydrateFromBootstrap]);

  const presetMutation = useMutation({
    mutationFn: async (presetId: string) => api.getLayout(externalUserId, presetId),
    onSuccess: (nextLayout) => {
      layoutSaveRef.current = JSON.stringify(nextLayout);
      replaceLayout(nextLayout);
    },
  });

  const saveLayoutMutation = useMutation({
    mutationFn: async (nextLayout: NonNullable<typeof layout>) =>
      api.saveLayout(externalUserId, nextLayout.preset, nextLayout),
    onSuccess: (savedLayout) => {
      layoutSaveRef.current = JSON.stringify(savedLayout);
      replaceLayout(savedLayout);
    },
  });

  useEffect(() => {
    if (!layout) {
      return;
    }
    const serialized = JSON.stringify(layout);
    if (serialized === layoutSaveRef.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      void saveLayoutMutation.mutateAsync(layout);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [layout, saveLayoutMutation]);

  if (!layout || !bootState) {
    return null;
  }

  const renderPanel = (panelId: string) => {
    switch (panelId) {
      case "board-feed":
        return <BoardPanel externalUserId={externalUserId} bootstrap={bootState} />;
      case "network-directory":
        return (
          <NetworkPanel
            externalUserId={externalUserId}
            bootstrap={bootState}
            onOpenMaster={setSelectedMasterId}
          />
        );
      case "workspace-overview":
        return <WorkspacePanel bootstrap={bootState} onFocusPanel={setPanePanel} />;
      case "catalog-browser":
        return (
          <CatalogPanel
            externalUserId={externalUserId}
            canCreateEstimate={bootState.capabilities.can_publish_master_profile}
          />
        );
      case "estimates-list":
        return <EstimatesPanel externalUserId={externalUserId} />;
      case "orders-list":
        return <OrdersPanel externalUserId={externalUserId} />;
      case "notifications-list":
        return <NotificationsPanel externalUserId={externalUserId} />;
      case "profile-card":
        return (
          <ProfilePanel
            externalUserId={externalUserId}
            canPublishMasterProfile={bootState.capabilities.can_publish_master_profile}
          />
        );
      case "approvals-queue":
        return <ApprovalsPanel externalUserId={externalUserId} />;
      case "analytics-overview":
        return <AnalyticsPanel externalUserId={externalUserId} />;
      default:
        return (
          <EmptyState
            title="Панель ещё не подключена"
            subtitle="Структура уже модульная: следующий модуль подключится сюда без переделки shell."
          />
        );
    }
  };

  const topMeta = panelLookup.get(layout.panes.top) ?? panels[0];
  const bottomMeta = panelLookup.get(layout.panes.bottom) ?? panels[0];

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">П</div>
          <div>
            <span className="eyebrow">ПриДел</span>
            <h1>{bootState.workspace.active_role_label || auth.name}</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <div className="preset-strip">
            {presets.map((preset) => (
              <button
                key={preset.id}
                className={`preset-chip ${layout.preset === preset.id ? "active" : ""}`}
                onClick={() => void presetMutation.mutateAsync(preset.id)}
              >
                {preset.title}
              </button>
            ))}
          </div>
          <button className="command-btn" onClick={() => setCommandOpen(true)}>
            Меню
          </button>
        </div>
      </header>

      <main className="workspace-frame">
        <Group
          direction="vertical"
          onLayout={(sizes) => {
            if (sizes[0]) {
              setRatio(Number(sizes[0].toFixed(1)));
            }
          }}
        >
          <Panel defaultSize={layout.ratio} minSize={34}>
            <PaneSurface
              paneId="top"
              panelId={layout.panes.top}
              title={topMeta?.title || "Панель"}
              icon={topMeta?.icon || "layers"}
              panels={panels}
              onChange={setPanePanel}
            >
              {renderPanel(layout.panes.top)}
            </PaneSurface>
          </Panel>
          <Separator className="resize-handle">
            <div className="handle-core" />
          </Separator>
          <Panel defaultSize={100 - layout.ratio} minSize={30}>
            <PaneSurface
              paneId="bottom"
              panelId={layout.panes.bottom}
              title={bottomMeta?.title || "Панель"}
              icon={bottomMeta?.icon || "users"}
              panels={panels}
              onChange={setPanePanel}
            >
              {renderPanel(layout.panes.bottom)}
            </PaneSurface>
          </Panel>
        </Group>
      </main>

      <footer className="dock">
        <button className="dock-btn" onClick={() => void presetMutation.mutateAsync("market")}>
          Рынок
        </button>
        <button className="dock-btn" onClick={() => void presetMutation.mutateAsync("workbench")}>
          Работа
        </button>
        <button className="dock-btn" onClick={() => setPanePanel("bottom", "profile-card")}>
          Профиль
        </button>
        <button className="dock-btn strong" onClick={() => setCommandOpen(true)}>
          Все модули
        </button>
      </footer>

      <CommandPalette
        open={commandOpen}
        panels={panels}
        onClose={() => setCommandOpen(false)}
        onSelect={setPanePanel}
      />
      <MasterDrawer
        externalUserId={externalUserId}
        selectedMasterId={selectedMasterId}
        onClose={() => setSelectedMasterId(null)}
      />
    </div>
  );
}

function AppBody() {
  useEffect(() => {
    prepareBridge();
  }, []);

  const authQuery = useQuery({
    queryKey: ["auth"],
    queryFn: () => api.auth(),
  });

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap", authQuery.data?.telegram_id],
    queryFn: () => api.bootstrap(authQuery.data?.telegram_id as number),
    enabled: Boolean(authQuery.data?.telegram_id),
  });

  if (authQuery.isPending || bootstrapQuery.isPending) {
    return (
      <div className="screen-center">
        <div className="loader-orb" />
        <p>Собираем лёгкое рабочее пространство…</p>
      </div>
    );
  }

  if (authQuery.error || bootstrapQuery.error || !authQuery.data || !bootstrapQuery.data) {
    const error = (authQuery.error || bootstrapQuery.error) as ApiError | undefined;
    return (
      <div className="screen-center">
        <div className="error-card">
          <strong>Не удалось открыть Mini App</strong>
          <p>{error?.message || "Проверьте доступ и повторите запуск из MAX."}</p>
        </div>
      </div>
    );
  }

  return <Shell auth={authQuery.data} bootstrap={bootstrapQuery.data} />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppBody />
    </QueryClientProvider>
  );
}
