import { type ReactNode, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
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
import { prepareBridge, resolveBridge } from "./bridge";
import { ControlCenterPanel } from "./ControlCenterPanel";
import { useWorkspaceStore } from "./store";
import type {
  BootstrapResponse,
  CatalogItem,
  EstimateSummary,
  JobPost,
  MasterCard,
  MasterReviewItem,
  NotificationItem,
  OrderDetail,
  OrderSummary,
  PaneId,
  PanelMeta,
  PublicProfileResponse,
  RoleModeResponse,
  TrustBadge,
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

const MAX_BOT_STARTAPP_URL = "https://max.ru/id026303852801_bot?startapp";

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

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function reviewNoun(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return "отзыв";
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "отзыва";
  }
  return "отзывов";
}

function ratingSummary(ratingAverage: number, ratingCount: number): string {
  if (!ratingCount) {
    return "Пока без отзывов";
  }
  return `${ratingAverage.toFixed(1)} • ${ratingCount} ${reviewNoun(ratingCount)}`;
}

function renderStars(rating: number): string {
  const filled = Math.max(0, Math.min(5, Math.round(rating)));
  return `${"★".repeat(filled)}${"☆".repeat(Math.max(0, 5 - filled))}`;
}

function TrustBadgeCloud({ badges, limit = 3 }: { badges: TrustBadge[]; limit?: number }) {
  if (!badges.length) {
    return null;
  }

  return (
    <div className="trust-badges">
      {badges.slice(0, limit).map((badge) => (
        <span key={badge.code} className={`pill trust-badge ${badge.tone === "success" ? "tone-success" : "tone-neutral"}`}>
          {badge.label}
        </span>
      ))}
    </div>
  );
}

function ReviewCard({ review }: { review: MasterReviewItem }) {
  return (
    <article className="glass-card review-card">
      <div className="card-topline">
        <div className="review-rating">
          <strong>{renderStars(review.rating)}</strong>
          <span>{review.rating.toFixed(1)}</span>
        </div>
        <span className="muted">{formatAgo(review.created_at)}</span>
      </div>
      {review.headline ? <h4>{review.headline}</h4> : null}
      {review.body ? <p>{review.body}</p> : <p className="muted">Клиент подтвердил работу и оставил оценку.</p>}
      <div className="meta-cloud">
        <span>Заказ #{review.order_id}</span>
        <span>{review.author.name}</span>
        {review.is_public ? <span>Публичный отзыв</span> : <span>Частный отзыв</span>}
      </div>
    </article>
  );
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function parseWorkflowCallback(callback?: string | null): { type: string; id: number | null } | null {
  if (!callback) {
    return null;
  }
  const [type, rawId] = callback.split(":");
  if (!rawId) {
    return { type, id: null };
  }
  const id = Number(rawId);
  return { type, id: Number.isFinite(id) ? id : null };
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
  const deferredQueryText = useDeferredValue(queryText.trim());
  const mastersQuery = useQuery({
    queryKey: ["masters", externalUserId, deferredQueryText, availability],
    queryFn: () =>
      api.listMasters(externalUserId, {
        q: deferredQueryText || undefined,
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
              <div className="trust-summary">
                <span className="rating-inline">
                  <strong>{master.rating_count ? renderStars(master.rating_average) : "☆☆☆☆☆"}</strong>
                  <span>{ratingSummary(master.rating_average, master.rating_count)}</span>
                </span>
                {master.response_time_label ? <span className="muted">{master.response_time_label}</span> : null}
              </div>
              {master.bio ? <p>{master.bio}</p> : null}
              <div className="meta-cloud">
                {master.city ? <span>{master.city}</span> : null}
                {master.experience_years ? <span>{master.experience_years}+ лет</span> : null}
                {master.hourly_rate_from ? <span>от {money(master.hourly_rate_from)}</span> : null}
              </div>
              <TrustBadgeCloud badges={master.trust_badges} limit={2} />
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
  onOpenWorkflow,
}: {
  bootstrap: BootstrapResponse;
  onFocusPanel: (pane: PaneId, panelId: string) => void;
  onOpenWorkflow: (callback?: string | null) => void;
}) {
  const metrics = [
    { label: "Сметы", value: bootstrap.workspace.active_estimates },
    { label: "Заказы", value: bootstrap.workspace.active_orders },
    { label: "Нужно решить", value: bootstrap.workspace.pending_approvals },
    { label: "Сигналы", value: bootstrap.notifications.unread },
  ];
  if (typeof bootstrap.workspace.completed_orders === "number") {
    metrics.push({ label: "Завершено", value: bootstrap.workspace.completed_orders });
  }
  if (typeof bootstrap.workspace.total_earned === "number") {
    metrics.push({ label: "Заработано", value: money(bootstrap.workspace.total_earned) });
  }

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

      {bootstrap.workspace.action_items.length ? (
        <SectionCard
          title="Следующие действия"
          subtitle="Собрали только то, что реально двигает работу вперёд прямо сейчас."
        >
          <div className="task-list">
            {bootstrap.workspace.action_items.map((task) => (
              <button key={task.callback} className="task-card" onClick={() => onOpenWorkflow(task.callback)}>
                <strong>{task.title}</strong>
                <span>{task.body}</span>
              </button>
            ))}
          </div>
        </SectionCard>
      ) : null}

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
  const deferredQueryText = useDeferredValue(queryText.trim());
  const searchQuery = useQuery({
    queryKey: ["catalog-search", externalUserId, deferredQueryText],
    queryFn: () => api.searchCatalog(externalUserId, deferredQueryText),
    enabled: deferredQueryText.length >= 2,
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
      await queryClient.invalidateQueries({ queryKey: ["estimate-detail", externalUserId] });
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
        {deferredQueryText.length < 2 ? (
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

function EstimatesPanel({
  externalUserId,
  canCreateEstimate,
  onOpenEstimate,
}: {
  externalUserId: number;
  canCreateEstimate: boolean;
  onOpenEstimate: (estimateId: number) => void;
}) {
  const queryClient = useQueryClient();
  const estimatesQuery = useQuery({
    queryKey: ["estimates", externalUserId],
    queryFn: () => api.listEstimates(externalUserId),
  });
  const createMutation = useMutation({
    mutationFn: () => api.createEstimate(externalUserId),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["estimates", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
      onOpenEstimate(created.id);
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard
        title="Сметы"
        subtitle="Черновики, клиентские ответы и готовые предложения в одном спокойном потоке."
        actions={
          canCreateEstimate ? (
            <button className="btn btn-primary" onClick={() => void createMutation.mutateAsync()}>
              {createMutation.isPending ? "Создаём..." : "Новая смета"}
            </button>
          ) : null
        }
      />
      <div className="card-list">
        {estimatesQuery.data?.length ? (
          estimatesQuery.data.map((estimate) => (
            <button
              key={estimate.id}
              className="glass-card compact-card card-button"
              onClick={() => onOpenEstimate(estimate.id)}
            >
              <div>
                <div className="card-topline">
                  <span className={`pill ${toneClass(estimate.status)}`}>{statusLabel(estimate.status)}</span>
                  <span className="muted">v{estimate.version}</span>
                </div>
                <h4>Смета #{estimate.id}</h4>
                <p>{money(estimate.final)} ₽ итогом</p>
              </div>
              <span className="muted">{formatAgo(estimate.created_at)}</span>
            </button>
          ))
        ) : (
          <EmptyState
            title="Смет пока нет"
            subtitle={
              canCreateEstimate
                ? "Каталог и доска помогут создать первую смету без лишних шагов."
                : "Когда мастер подготовит предложение или вы откроете его сами, сметы появятся здесь."
            }
          />
        )}
      </div>
    </div>
  );
}

function OrdersPanel({
  externalUserId,
  onOpenOrder,
}: {
  externalUserId: number;
  onOpenOrder: (orderId: number) => void;
}) {
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
            <button
              key={order.id}
              className="glass-card compact-card card-button"
              onClick={() => onOpenOrder(order.id)}
            >
              <div>
                <div className="card-topline">
                  <span className={`pill ${toneClass(order.status)}`}>{statusLabel(order.status)}</span>
                  {order.estimate_id ? <span className="muted">из сметы #{order.estimate_id}</span> : null}
                </div>
                <h4>Заказ #{order.id}</h4>
                <p>{order.address || "Адрес пока не указан"}</p>
              </div>
              <span className="muted">{formatAgo(order.created_at)}</span>
            </button>
          ))
        ) : (
          <EmptyState title="Заказов пока нет" subtitle="Они появятся здесь после согласования смет и запуска работ." />
        )}
      </div>
    </div>
  );
}

function NotificationsPanel({
  externalUserId,
  onOpenTarget,
}: {
  externalUserId: number;
  onOpenTarget: (callback?: string | null) => void;
}) {
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
              <div className="action-row">
                {notification.target_label ? (
                  <button className="btn" onClick={() => onOpenTarget(notification.target_callback)}>
                    {notification.target_label}
                  </button>
                ) : null}
                {notification.is_unread ? (
                  <button className="btn" onClick={() => void readMutation.mutateAsync(notification.id)}>
                    Отметить прочитанным
                  </button>
                ) : null}
              </div>
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
  const queryClient = useQueryClient();
  const [rejectId, setRejectId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const approvalsQuery = useQuery({
    queryKey: ["approvals", externalUserId],
    queryFn: () => api.listApprovals(externalUserId),
  });
  const actionMutation = useMutation({
    mutationFn: async ({
      requestId,
      action,
      comment,
    }: {
      requestId: number;
      action: "approve" | "reject";
      comment?: string;
    }) => api.processApproval(externalUserId, requestId, action, comment),
    onSuccess: async () => {
      setRejectId(null);
      setComment("");
      await queryClient.invalidateQueries({ queryKey: ["approvals", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["estimate-detail", externalUserId] });
    },
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
                <p>
                  {approval.type}: {approval.value}%
                </p>
              </div>
              <div className="approval-actions">
                <span className="muted">{formatAgo(approval.created_at)}</span>
                <div className="action-row">
                  <button
                    className="btn btn-primary"
                    onClick={() =>
                      void actionMutation.mutateAsync({ requestId: approval.id, action: "approve" })
                    }
                  >
                    Одобрить
                  </button>
                  <button className="btn" onClick={() => setRejectId((current) => (current === approval.id ? null : approval.id))}>
                    Отклонить
                  </button>
                </div>
                {rejectId === approval.id ? (
                  <div className="inline-composer">
                    <textarea
                      className="textarea compact"
                      placeholder="Короткий комментарий к отклонению"
                      value={comment}
                      onChange={(event) => setComment(event.target.value)}
                    />
                    <div className="action-row">
                      <button
                        className="btn btn-primary"
                        onClick={() =>
                          void actionMutation.mutateAsync({
                            requestId: approval.id,
                            action: "reject",
                            comment: comment || "Отклонено",
                          })
                        }
                      >
                        Подтвердить отклонение
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
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
            <SectionCard title="Профиль" subtitle="Короткий срез доверия и специализации без перегруза.">
              <div className="glass-card">
                <div className="trust-summary">
                  <span className="rating-inline">
                    <strong>{masterQuery.data.rating_count ? renderStars(masterQuery.data.rating_average) : "☆☆☆☆☆"}</strong>
                    <span>{ratingSummary(masterQuery.data.rating_average, masterQuery.data.rating_count)}</span>
                  </span>
                  {masterQuery.data.response_time_label ? <span className="muted">{masterQuery.data.response_time_label}</span> : null}
                </div>
                <TrustBadgeCloud badges={masterQuery.data.trust_badges} limit={4} />
                <div className="meta-cloud">
                  {masterQuery.data.city ? <span>{masterQuery.data.city}</span> : null}
                  <span>{masterQuery.data.completed_jobs} завершённых работ</span>
                  <span>{statusLabel(masterQuery.data.availability_status)}</span>
                  {masterQuery.data.hourly_rate_from ? <span>от {money(masterQuery.data.hourly_rate_from)}</span> : null}
                </div>
                <p>{masterQuery.data.bio || "Профиль пока без описания."}</p>
              </div>
            </SectionCard>
            <SectionCard title="Навыки" subtitle="Только ключевые теги, чтобы быстро понять специализацию.">
              <div className="tag-row">
                {masterQuery.data.skills.length ? (
                  masterQuery.data.skills.map((skill) => (
                    <span key={skill} className="tag">
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="muted">Навыки пока не заполнены.</span>
                )}
              </div>
            </SectionCard>
            {masterQuery.data.portfolio.length ? (
              <SectionCard title="Портфолио" subtitle="Короткая витрина подтверждённых кейсов и ссылок.">
                <div className="card-list">
                  {masterQuery.data.portfolio.slice(0, 3).map((item, index) => (
                    <article key={`${item.title}-${index}`} className="glass-card compact-card align-start">
                      <div>
                        <h4>{item.title}</h4>
                        <p>{item.kind}</p>
                      </div>
                      {item.url ? (
                        <a className="btn" href={item.url} target="_blank" rel="noreferrer">
                          Открыть
                        </a>
                      ) : null}
                    </article>
                  ))}
                </div>
              </SectionCard>
            ) : null}
            <SectionCard
              title="Проверенные отзывы"
              subtitle="Отзывы привязаны к завершённым заказам, поэтому доверие строится на реальных сделках."
            >
              {masterQuery.data.reviews.length ? (
                <div className="timeline-list">
                  {masterQuery.data.reviews.map((review) => (
                    <ReviewCard key={review.id} review={review} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="Отзывов пока нет"
                  subtitle="Когда по завершённым заказам появятся оценки, здесь будет спокойная лента проверенной репутации."
                />
              )}
            </SectionCard>
          </div>
        ) : (
          <EmptyState title="Загружаем профиль" subtitle="Сейчас подтянем все публичные данные мастера." />
        )}
      </aside>
    </div>
  );
}

function RoleModeDrawer({
  open,
  roleMode,
  onClose,
  onSelect,
  isPending,
  errorText,
}: {
  open: boolean;
  roleMode: RoleModeResponse | undefined;
  onClose: () => void;
  onSelect: (roleCode: string | null) => void;
  isPending: boolean;
  errorText?: string | null;
}) {
  if (!open || !roleMode) {
    return null;
  }

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>Режим работы</h3>
            <p>Переключайте контекст аккуратно: интерфейс и права подстроятся под выбранную роль.</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <SectionCard title="Сейчас активно" subtitle="Текущий контекст влияет на панели, действия и очереди.">
          <div className="meta-cloud">
            <span>{roleMode.active_role_label}</span>
            <span>Максимум: {roleMode.max_role_label}</span>
          </div>
          {roleMode.is_role_switched ? (
            <p className="muted">
              Включён временный тестовый режим. Прямые роли в базе не меняются, меняется только рабочий контекст.
            </p>
          ) : null}
          <div className="role-switch-grid">
            <button
              className={`quick-card ${!roleMode.role_override ? "active-card" : ""}`}
              onClick={() => onSelect(null)}
              disabled={isPending}
            >
              Авто
            </button>
            {roleMode.available_roles.map((role) => (
              <button
                key={role.code}
                className={`quick-card ${roleMode.active_role === role.code ? "active-card" : ""}`}
                onClick={() => onSelect(role.code)}
                disabled={isPending}
              >
                {role.label}
              </button>
            ))}
          </div>
          {errorText ? <p className="inline-error">{errorText}</p> : null}
        </SectionCard>
      </aside>
    </div>
  );
}

function EstimateDrawer({
  externalUserId,
  estimateId,
  onClose,
  onFocusPanel,
  onOpenOrder,
}: {
  externalUserId: number;
  estimateId: number | null;
  onClose: () => void;
  onFocusPanel: (pane: PaneId, panelId: string) => void;
  onOpenOrder: (orderId: number) => void;
}) {
  const queryClient = useQueryClient();
  const [sendOpen, setSendOpen] = useState(false);
  const [clientExternalId, setClientExternalId] = useState("");
  const [discountOpen, setDiscountOpen] = useState(false);
  const [discountValue, setDiscountValue] = useState("");
  const [orderOpen, setOrderOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [orderForm, setOrderForm] = useState({
    address: "",
    urgency: "normal",
    notes: "",
  });

  useEffect(() => {
    setSendOpen(false);
    setClientExternalId("");
    setDiscountOpen(false);
    setDiscountValue("");
    setOrderOpen(false);
    setQrOpen(false);
    setOrderForm({ address: "", urgency: "normal", notes: "" });
  }, [estimateId]);

  const estimateQuery = useQuery({
    queryKey: ["estimate-detail", externalUserId, estimateId],
    queryFn: () => api.getEstimate(externalUserId, estimateId as number),
    enabled: estimateId !== null,
  });

  const qrQuery = useQuery({
    queryKey: ["estimate-qr", externalUserId, estimateId],
    queryFn: () => api.getEstimateQr(externalUserId, estimateId as number),
    enabled: estimateId !== null && qrOpen,
  });

  const refreshEstimateData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["estimate-detail", externalUserId, estimateId] }),
      queryClient.invalidateQueries({ queryKey: ["estimates", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["orders", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["approvals", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["notifications", externalUserId] }),
    ]);
  };

  const updateItemMutation = useMutation({
    mutationFn: async ({ lineItemId, quantity }: { lineItemId: number; quantity: number }) =>
      api.updateEstimateItem(externalUserId, estimateId as number, lineItemId, quantity),
    onSuccess: refreshEstimateData,
  });

  const deleteItemMutation = useMutation({
    mutationFn: async (lineItemId: number) => api.deleteEstimateItem(externalUserId, estimateId as number, lineItemId),
    onSuccess: refreshEstimateData,
  });

  const statusMutation = useMutation({
    mutationFn: async (body: { status: string; client_external_id?: number | null }) =>
      api.updateEstimateStatus(externalUserId, estimateId as number, body),
    onSuccess: refreshEstimateData,
  });

  const discountMutation = useMutation({
    mutationFn: async (value: number) => api.requestEstimateDiscount(externalUserId, estimateId as number, value),
    onSuccess: async () => {
      setDiscountOpen(false);
      setDiscountValue("");
      await refreshEstimateData();
    },
  });

  const deleteEstimateMutation = useMutation({
    mutationFn: async () => api.deleteEstimate(externalUserId, estimateId as number),
    onSuccess: async () => {
      await refreshEstimateData();
      onClose();
    },
  });

  const createOrderMutation = useMutation({
    mutationFn: async () =>
      api.createOrder(externalUserId, {
        estimate_id: estimateId as number,
        address: orderForm.address,
        urgency: orderForm.urgency,
        notes: orderForm.notes || null,
      }),
    onSuccess: async (order) => {
      setOrderOpen(false);
      await refreshEstimateData();
      onOpenOrder(order.id);
    },
  });

  if (estimateId === null) {
    return null;
  }

  const estimate = estimateQuery.data;
  const capabilities = estimate?.capabilities ?? {};

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer wide-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>{estimate ? `Смета #${estimate.id}` : "Смета"}</h3>
            <p>{estimate ? `${statusLabel(estimate.status)} · версия ${estimate.version}` : "Загружаем детали"}</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>

        {!estimate ? (
          <EmptyState title="Загружаем смету" subtitle="Собираем позиции, статусы и доступные действия." />
        ) : (
          <div className="panel-stack">
            <SectionCard title="Состав" subtitle="Редактирование остаётся внутри drawer, не перегружая основной split-view.">
              <div className="card-list">
                {estimate.items.length ? (
                  estimate.items.map((item, index) => (
                    <article key={item.id} className="glass-card compact-card align-start">
                      <div>
                        <div className="card-topline">
                          <span className="muted">#{index + 1}</span>
                          <span className="muted">
                            {item.quantity} {item.unit} · {money(item.unit_price)}
                          </span>
                        </div>
                        <h4>{item.name}</h4>
                        <p>{money(item.subtotal)} ₽</p>
                      </div>
                      {capabilities.can_edit && estimate.status === "draft" ? (
                        <div className="qty-shell">
                          <button
                            className="btn"
                            onClick={() =>
                              item.quantity <= 1
                                ? void deleteItemMutation.mutateAsync(item.id)
                                : void updateItemMutation.mutateAsync({
                                    lineItemId: item.id,
                                    quantity: Math.max(1, item.quantity - 1),
                                  })
                            }
                          >
                            −
                          </button>
                          <span>{item.quantity}</span>
                          <button
                            className="btn"
                            onClick={() =>
                              void updateItemMutation.mutateAsync({
                                lineItemId: item.id,
                                quantity: item.quantity + 1,
                              })
                            }
                          >
                            +
                          </button>
                        </div>
                      ) : null}
                    </article>
                  ))
                ) : (
                  <EmptyState title="Смета пока пустая" subtitle="Добавьте работы через каталог или поиск, когда будете готовы." />
                )}
              </div>
              {capabilities.can_edit && estimate.status === "draft" ? (
                <div className="action-row">
                  <button className="btn btn-primary" onClick={() => onFocusPanel("top", "catalog-browser")}>
                    Открыть каталог
                  </button>
                  <button className="btn" onClick={() => onFocusPanel("bottom", "catalog-browser")}>
                    Каталог снизу
                  </button>
                </div>
              ) : null}
            </SectionCard>

            <SectionCard title="Итоги" subtitle="Короткая финансовая сводка без лишних таблиц.">
              <div className="metric-grid dense">
                <div className="metric-card">
                  <span>Сумма</span>
                  <strong>{money(estimate.total)}</strong>
                </div>
                <div className="metric-card">
                  <span>Скидка</span>
                  <strong>{money(estimate.discount)}</strong>
                </div>
                <div className="metric-card">
                  <span>Итог</span>
                  <strong>{money(estimate.final)}</strong>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Действия" subtitle="Только сценарии, которые реально доступны по правам и статусу.">
              <div className="action-row">
                {capabilities.can_send_to_client && estimate.status === "draft" ? (
                  <button className="btn btn-primary" onClick={() => setSendOpen((current) => !current)}>
                    Клиенту
                  </button>
                ) : null}
                {capabilities.can_request_discount ? (
                  <button className="btn" onClick={() => setDiscountOpen((current) => !current)}>
                    Скидка
                  </button>
                ) : null}
                {capabilities.can_create_order && estimate.status === "approved" ? (
                  <button className="btn btn-primary" onClick={() => setOrderOpen((current) => !current)}>
                    Создать заказ
                  </button>
                ) : null}
                {capabilities.can_delete && estimate.status === "draft" ? (
                  <button className="btn" onClick={() => void deleteEstimateMutation.mutateAsync()}>
                    Удалить
                  </button>
                ) : null}
              </div>

              {sendOpen ? (
                <div className="inline-composer">
                  <input
                    className="input"
                    type="number"
                    min="1"
                    placeholder="ID клиента в MAX, если ещё не привязан"
                    value={clientExternalId}
                    onChange={(event) => setClientExternalId(event.target.value)}
                  />
                  <div className="action-row">
                    <button
                      className="btn btn-primary"
                      onClick={() =>
                        void statusMutation.mutateAsync({
                          status: "client_review",
                          client_external_id: clientExternalId ? Number(clientExternalId) : null,
                        })
                      }
                    >
                      Отправить клиенту
                    </button>
                  </div>
                  {statusMutation.error ? (
                    <p className="inline-error">{errorMessage(statusMutation.error, "Не удалось отправить смету")}</p>
                  ) : null}
                </div>
              ) : null}

              {discountOpen ? (
                <div className="inline-composer">
                  <input
                    className="input"
                    type="number"
                    min="1"
                    max="50"
                    placeholder="Процент скидки"
                    value={discountValue}
                    onChange={(event) => setDiscountValue(event.target.value)}
                  />
                  <div className="action-row">
                    <button
                      className="btn btn-primary"
                      onClick={() => void discountMutation.mutateAsync(Number(discountValue))}
                    >
                      Запросить скидку
                    </button>
                  </div>
                  {discountMutation.error ? (
                    <p className="inline-error">{errorMessage(discountMutation.error, "Не удалось отправить скидку")}</p>
                  ) : null}
                </div>
              ) : null}

              {estimate.status === "client_review" && capabilities.can_client_respond ? (
                <div className="action-row">
                  <button
                    className="btn btn-primary"
                    onClick={() => void statusMutation.mutateAsync({ status: "approved" })}
                  >
                    Согласовать
                  </button>
                  <button className="btn" onClick={() => void statusMutation.mutateAsync({ status: "draft" })}>
                    Вернуть на доработку
                  </button>
                </div>
              ) : null}

              {orderOpen ? (
                <div className="inline-composer">
                  <input
                    className="input"
                    placeholder="Адрес выполнения работ"
                    value={orderForm.address}
                    onChange={(event) => setOrderForm((state) => ({ ...state, address: event.target.value }))}
                  />
                  <div className="row-grid">
                    <select
                      className="input"
                      value={orderForm.urgency}
                      onChange={(event) => setOrderForm((state) => ({ ...state, urgency: event.target.value }))}
                    >
                      <option value="normal">Обычная</option>
                      <option value="urgent">Срочная</option>
                      <option value="emergency">Экстренная</option>
                    </select>
                    <input
                      className="input"
                      placeholder="Краткая заметка"
                      value={orderForm.notes}
                      onChange={(event) => setOrderForm((state) => ({ ...state, notes: event.target.value }))}
                    />
                  </div>
                  <div className="action-row">
                    <button className="btn btn-primary" onClick={() => void createOrderMutation.mutateAsync()}>
                      Создать заказ
                    </button>
                  </div>
                  {createOrderMutation.error ? (
                    <p className="inline-error">{errorMessage(createOrderMutation.error, "Не удалось создать заказ")}</p>
                  ) : null}
                </div>
              ) : null}

              {deleteEstimateMutation.error ? (
                <p className="inline-error">{errorMessage(deleteEstimateMutation.error, "Не удалось удалить смету")}</p>
              ) : null}
            </SectionCard>

            {estimate.items.length ? (
              <SectionCard title="Экспорт и оплата" subtitle="Файлы и QR доступны прямо из drawer, без разрыва сценария.">
                <div className="action-row">
                  <button
                    className="btn"
                    onClick={async () => {
                      const file = await api.downloadEstimatePdf(externalUserId, estimate.id);
                      triggerBlobDownload(file.blob, file.filename);
                    }}
                  >
                    PDF
                  </button>
                  <button
                    className="btn"
                    onClick={async () => {
                      const file = await api.downloadEstimateXlsx(externalUserId, estimate.id);
                      triggerBlobDownload(file.blob, file.filename);
                    }}
                  >
                    XLSX
                  </button>
                  <button className="btn btn-primary" onClick={() => setQrOpen((current) => !current)}>
                    QR оплата
                  </button>
                </div>
                {qrOpen ? (
                  <div className="inline-composer">
                    {qrQuery.data?.qr_image ? (
                      <img
                        className="qr-preview"
                        alt="QR оплаты"
                        src={`data:image/png;base64,${qrQuery.data.qr_image}`}
                      />
                    ) : null}
                    <div className="meta-cloud">
                      {qrQuery.data?.recipient ? <span>{qrQuery.data.recipient}</span> : null}
                      {qrQuery.data?.bank ? <span>{qrQuery.data.bank}</span> : null}
                      {qrQuery.data?.sbp_phone ? <span>{qrQuery.data.sbp_phone}</span> : null}
                    </div>
                    {qrQuery.data?.fallback_notice ? <p className="muted">{qrQuery.data.fallback_notice}</p> : null}
                    {qrQuery.error ? (
                      <p className="inline-error">{errorMessage(qrQuery.error, "Не удалось сформировать QR")}</p>
                    ) : null}
                  </div>
                ) : null}
              </SectionCard>
            ) : null}
          </div>
        )}
      </aside>
    </div>
  );
}

function OrderDrawer({
  externalUserId,
  orderId,
  onClose,
}: {
  externalUserId: number;
  orderId: number | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [cancelReason, setCancelReason] = useState("");
  const [showPayment, setShowPayment] = useState(false);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewHeadline, setReviewHeadline] = useState("");
  const [reviewBody, setReviewBody] = useState("");
  const [reviewIsPublic, setReviewIsPublic] = useState(true);

  useEffect(() => {
    setCancelReason("");
    setShowPayment(false);
    setReviewRating(5);
    setReviewHeadline("");
    setReviewBody("");
    setReviewIsPublic(true);
  }, [orderId]);

  const orderQuery = useQuery({
    queryKey: ["order-detail", externalUserId, orderId],
    queryFn: () => api.getOrder(externalUserId, orderId as number),
    enabled: orderId !== null,
  });

  const paymentQuery = useQuery({
    queryKey: ["order-payment", externalUserId, orderId],
    queryFn: () => api.getOrderPayment(externalUserId, orderId as number),
    enabled: orderId !== null && showPayment,
  });

  const refreshOrderData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["orders", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["order-detail", externalUserId, orderId] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["notifications", externalUserId] }),
      queryClient.invalidateQueries({ queryKey: ["masters"] }),
      queryClient.invalidateQueries({ queryKey: ["master"] }),
      queryClient.invalidateQueries({ queryKey: ["public-profile", externalUserId] }),
    ]);
  };

  const statusMutation = useMutation({
    mutationFn: async (body: { status: string; reason?: string | null }) =>
      api.updateOrderStatus(externalUserId, orderId as number, body),
    onSuccess: refreshOrderData,
  });

  const assignMutation = useMutation({
    mutationFn: async () => api.assignOrderToSelf(externalUserId, orderId as number),
    onSuccess: refreshOrderData,
  });

  const reviewMutation = useMutation({
    mutationFn: async () =>
      api.createOrderReview(externalUserId, orderId as number, {
        rating: reviewRating,
        headline: reviewHeadline.trim() || null,
        body: reviewBody.trim() || null,
        is_public: reviewIsPublic,
      }),
    onSuccess: async () => {
      setReviewHeadline("");
      setReviewBody("");
      setReviewRating(5);
      setReviewIsPublic(true);
      await refreshOrderData();
    },
  });

  if (orderId === null) {
    return null;
  }

  const order: OrderDetail | undefined = orderQuery.data;
  const capabilities = order?.capabilities ?? {};

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer wide-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>{order ? `Заказ #${order.id}` : "Заказ"}</h3>
            <p>{order ? statusLabel(order.status) : "Загружаем детали"}</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        {!order ? (
          <EmptyState title="Загружаем заказ" subtitle="Подтягиваем историю, состав работ и доступные переходы." />
        ) : (
          <div className="panel-stack">
            <SectionCard title="Контекст" subtitle="Ключевые данные без ухода в отдельный экран.">
              <div className="meta-cloud">
                {order.address ? <span>{order.address}</span> : null}
                {order.client_name ? <span>Клиент: {order.client_name}</span> : null}
                {order.master_name ? <span>Мастер: {order.master_name}</span> : null}
                {order.payment_status ? <span>Оплата: {order.payment_status}</span> : null}
              </div>
              {order.notes ? <p>{order.notes}</p> : null}
              {order.cancellation_reason ? <p className="muted">Причина отмены: {order.cancellation_reason}</p> : null}
            </SectionCard>

            {order.estimate ? (
              <SectionCard title="Состав работ" subtitle={`По смете #${order.estimate.id}, версия ${order.estimate.version}.`}>
                <div className="card-list">
                  {order.estimate.items.map((item, index) => (
                    <article key={`${item.name}-${index}`} className="glass-card compact-card align-start">
                      <div>
                        <h4>{item.name}</h4>
                        <p>
                          {item.quantity} × {money(item.unit_price)}
                        </p>
                      </div>
                      <strong>{money(item.subtotal)}</strong>
                    </article>
                  ))}
                </div>
                <div className="metric-grid dense">
                  <div className="metric-card">
                    <span>Сумма</span>
                    <strong>{money(order.estimate.total)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Итог</span>
                    <strong>{money(order.estimate.final)}</strong>
                  </div>
                </div>
              </SectionCard>
            ) : null}

            <SectionCard title="Статусные действия" subtitle="Ровно те переходы, которые доступны вам сейчас.">
              <div className="action-row">
                {capabilities.can_submit ? (
                  <button className="btn btn-primary" onClick={() => void statusMutation.mutateAsync({ status: "submitted" })}>
                    Отправить заказ
                  </button>
                ) : null}
                {capabilities.can_assign ? (
                  <button className="btn btn-primary" onClick={() => void assignMutation.mutateAsync()}>
                    Взять заказ
                  </button>
                ) : null}
                {capabilities.can_start ? (
                  <button className="btn btn-primary" onClick={() => void statusMutation.mutateAsync({ status: "in_progress" })}>
                    Начать работу
                  </button>
                ) : null}
                {capabilities.can_complete ? (
                  <button className="btn btn-primary" onClick={() => void statusMutation.mutateAsync({ status: "completed" })}>
                    Завершить
                  </button>
                ) : null}
                {capabilities.can_pay ? (
                  <button className="btn" onClick={() => setShowPayment((current) => !current)}>
                    Оплата
                  </button>
                ) : null}
              </div>

              {capabilities.can_cancel ? (
                <div className="inline-composer">
                  {order.cancel_reasons.length ? (
                    <select
                      className="input"
                      value={cancelReason}
                      onChange={(event) => setCancelReason(event.target.value)}
                    >
                      <option value="">Причина отмены</option>
                      {order.cancel_reasons.map((option) => (
                        <option key={option.code} value={option.code}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      className="input"
                      placeholder="Причина отмены"
                      value={cancelReason}
                      onChange={(event) => setCancelReason(event.target.value)}
                    />
                  )}
                  <div className="action-row">
                    <button
                      className="btn"
                      onClick={() =>
                        void statusMutation.mutateAsync({
                          status: "cancelled",
                          reason: cancelReason || null,
                        })
                      }
                    >
                      Отменить заказ
                    </button>
                  </div>
                </div>
              ) : null}

              {showPayment ? (
                <div className="inline-composer">
                  {paymentQuery.data ? (
                    <>
                      <div className="metric-grid dense">
                        <div className="metric-card">
                          <span>Сумма</span>
                          <strong>{money(paymentQuery.data.amount)}</strong>
                        </div>
                        {paymentQuery.data.recipient ? (
                          <div className="metric-card">
                            <span>Получатель</span>
                            <strong>{paymentQuery.data.recipient}</strong>
                          </div>
                        ) : null}
                        {paymentQuery.data.phone ? (
                          <div className="metric-card">
                            <span>Телефон</span>
                            <strong>{paymentQuery.data.phone}</strong>
                          </div>
                        ) : null}
                      </div>
                      <div className="action-row">
                        <button
                          className="btn btn-primary"
                          onClick={() => void statusMutation.mutateAsync({ status: "paid" })}
                        >
                          Отметить оплаченным
                        </button>
                      </div>
                    </>
                  ) : null}
                  {paymentQuery.error ? (
                    <p className="inline-error">{errorMessage(paymentQuery.error, "Не удалось получить реквизиты")}</p>
                  ) : null}
                </div>
              ) : null}

              {statusMutation.error ? (
                <p className="inline-error">{errorMessage(statusMutation.error, "Не удалось обновить заказ")}</p>
              ) : null}
              {assignMutation.error ? (
                <p className="inline-error">{errorMessage(assignMutation.error, "Не удалось назначить заказ")}</p>
              ) : null}
            </SectionCard>

            {order.review.item || order.review.can_create ? (
              <SectionCard
                title="Отзыв о мастере"
                subtitle="Оценка создаётся прямо из завершённой сделки, поэтому путь остаётся коротким и понятным."
              >
                {order.review.item ? (
                  <ReviewCard review={order.review.item} />
                ) : null}

                {order.review.can_create ? (
                  <div className="inline-composer">
                    <div className="review-rating-picker">
                      {[1, 2, 3, 4, 5].map((value) => (
                        <button
                          key={value}
                          className={`star-btn ${reviewRating >= value ? "active" : ""}`}
                          onClick={() => setReviewRating(value)}
                        >
                          ★
                        </button>
                      ))}
                      <span className="muted">{reviewRating} из 5</span>
                    </div>
                    <input
                      className="input"
                      placeholder="Короткий заголовок отзыва"
                      value={reviewHeadline}
                      onChange={(event) => setReviewHeadline(event.target.value)}
                    />
                    <textarea
                      className="textarea compact"
                      placeholder="Что особенно понравилось в работе мастера"
                      value={reviewBody}
                      onChange={(event) => setReviewBody(event.target.value)}
                    />
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={reviewIsPublic}
                        onChange={(event) => setReviewIsPublic(event.target.checked)}
                      />
                      <span>Показывать отзыв в публичном профиле мастера</span>
                    </label>
                    <div className="action-row">
                      <button className="btn btn-primary" onClick={() => void reviewMutation.mutateAsync()}>
                        {reviewMutation.isPending ? "Сохраняем..." : "Оставить отзыв"}
                      </button>
                    </div>
                    {reviewMutation.error ? (
                      <p className="inline-error">{errorMessage(reviewMutation.error, "Не удалось сохранить отзыв")}</p>
                    ) : null}
                  </div>
                ) : null}
              </SectionCard>
            ) : null}

            {order.history.length ? (
              <SectionCard title="История" subtitle="Переходы и причины изменений по заказу.">
                <div className="timeline-list">
                  {order.history.map((item, index) => (
                    <article key={`${item.to}-${index}`} className="glass-card">
                      <div className="card-topline">
                        <span className={`pill ${toneClass(item.to)}`}>{statusLabel(item.to)}</span>
                        <span className="muted">{formatAgo(item.at)}</span>
                      </div>
                      <p>
                        {item.from ? `${statusLabel(item.from)} → ` : ""}
                        {statusLabel(item.to)}
                      </p>
                      {item.reason ? <p className="muted">{item.reason}</p> : null}
                    </article>
                  ))}
                </div>
              </SectionCard>
            ) : null}
          </div>
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
  const queryClient = useQueryClient();
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
  const [selectedEstimateId, setSelectedEstimateId] = useState<number | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
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

  const roleModeQuery = useQuery({
    queryKey: ["role-mode", externalUserId],
    queryFn: () => api.getRoleMode(externalUserId),
    initialData: {
      direct_roles: bootstrap.workspace.roles,
      roles: bootstrap.workspace.roles,
      active_role: bootstrap.workspace.primary_role,
      active_role_label: bootstrap.workspace.active_role_label,
      max_role: bootstrap.workspace.max_role,
      max_role_label: bootstrap.workspace.max_role_label,
      role_override: null,
      is_role_switched: false,
      can_switch_role: bootstrap.workspace.can_switch_role,
      available_roles: [],
    } satisfies RoleModeResponse,
  });

  const roleModeMutation = useMutation({
    mutationFn: async (roleCode: string | null) => api.setRoleMode(externalUserId, roleCode),
    onSuccess: async (roleMode) => {
      setSelectedEstimateId(null);
      setSelectedOrderId(null);
      setSelectedMasterId(null);
      queryClient.setQueryData(["role-mode", externalUserId], roleMode);
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["profile", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["public-profile", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["notifications", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["approvals", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["orders", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["estimates", externalUserId] });
      if (!roleMode.can_switch_role) {
        setRoleDrawerOpen(false);
      }
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

  const openEstimate = (estimateId: number) => {
    setSelectedEstimateId(estimateId);
    setSelectedOrderId(null);
  };

  const openOrder = (orderId: number) => {
    setSelectedEstimateId(null);
    setSelectedOrderId(orderId);
  };

  const focusPanelByCallback = (pane: PaneId, panelId: string) => {
    setPanePanel(pane, panelId);
    setCommandOpen(false);
  };

  const handleWorkflowTarget = (callback?: string | null) => {
    const parsed = parseWorkflowCallback(callback);
    if (!parsed) {
      return;
    }

    switch (parsed.type) {
      case "est_view":
      case "est_send":
      case "est_discount":
      case "est_pdf":
      case "est_qr":
      case "est_to_order":
      case "est_approve":
      case "est_reject":
        focusPanelByCallback("top", "estimates-list");
        if (parsed.id !== null) {
          openEstimate(parsed.id);
        }
        return;
      case "order_view":
      case "order_submit":
      case "order_assign":
      case "order_start":
      case "order_complete":
      case "order_pay":
      case "order_cancel":
        focusPanelByCallback("top", "orders-list");
        if (parsed.id !== null) {
          openOrder(parsed.id);
        }
        return;
      case "disc_detail":
      case "approvals":
        focusPanelByCallback("top", "approvals-queue");
        return;
      case "notif_open":
        focusPanelByCallback("top", "notifications-list");
        return;
      case "profile":
      case "profile_edit":
      case "profile_requisites":
        focusPanelByCallback("bottom", "profile-card");
        return;
      case "profile_role_mode":
        setRoleDrawerOpen(true);
        return;
      case "catalog":
      case "search":
      case "popular":
        focusPanelByCallback("top", "catalog-browser");
        return;
      case "my_estimates":
        focusPanelByCallback("top", "estimates-list");
        return;
      case "my_orders":
        focusPanelByCallback("top", "orders-list");
        return;
      case "inv_pending":
      case "adm_staffing":
      case "admin_panel":
      case "owner_panel":
      case "adm_flags":
        focusPanelByCallback("top", "control-center");
        return;
      case "own_finance":
      case "own_funnel":
      case "own_masters":
      case "own_branches":
      case "own_discounts":
      case "own_settings":
      case "adm_audit":
        focusPanelByCallback("top", "control-center");
        return;
      default:
        focusPanelByCallback("top", "workspace-overview");
    }
  };

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
        return (
          <WorkspacePanel
            bootstrap={bootState}
            onFocusPanel={setPanePanel}
            onOpenWorkflow={handleWorkflowTarget}
          />
        );
      case "catalog-browser":
        return (
          <CatalogPanel
            externalUserId={externalUserId}
            canCreateEstimate={bootState.capabilities.can_create_estimate}
          />
        );
      case "estimates-list":
        return (
          <EstimatesPanel
            externalUserId={externalUserId}
            canCreateEstimate={bootState.capabilities.can_create_estimate}
            onOpenEstimate={openEstimate}
          />
        );
      case "orders-list":
        return <OrdersPanel externalUserId={externalUserId} onOpenOrder={openOrder} />;
      case "notifications-list":
        return <NotificationsPanel externalUserId={externalUserId} onOpenTarget={handleWorkflowTarget} />;
      case "profile-card":
        return (
          <ProfilePanel
            externalUserId={externalUserId}
            canPublishMasterProfile={bootState.capabilities.can_publish_master_profile}
          />
        );
      case "control-center":
        return <ControlCenterPanel externalUserId={externalUserId} />;
      case "approvals-queue":
        return <ApprovalsPanel externalUserId={externalUserId} />;
      case "analytics-overview":
        return <AnalyticsPanel externalUserId={externalUserId} />;
      default:
        return (
          <EmptyState
            title="Панель ещё не подключена"
            subtitle="Shell уже модульный: следующий функциональный блок подключится сюда без пересборки всей навигации."
          />
        );
    }
  };

  const topMeta = panelLookup.get(layout.panes.top) ?? panels[0];
  const bottomMeta = panelLookup.get(layout.panes.bottom) ?? panels[0];
  const activeRoleLabel = roleModeQuery.data?.active_role_label || bootState.workspace.active_role_label;
  const maxRoleLabel = roleModeQuery.data?.max_role_label || bootState.workspace.max_role_label;
  const canSwitchRole = roleModeQuery.data?.can_switch_role || bootState.workspace.can_switch_role;

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">П</div>
          <div>
            <span className="eyebrow">4-2 • ПриДел</span>
            <h1>{auth.name}</h1>
            <p className="topbar-role">
              {activeRoleLabel}
              {maxRoleLabel && maxRoleLabel !== activeRoleLabel ? ` • потолок ${maxRoleLabel}` : ""}
            </p>
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
          {canSwitchRole ? (
            <button className="btn" onClick={() => setRoleDrawerOpen(true)}>
              {roleModeMutation.isPending ? "Переключаем…" : "Режим"}
            </button>
          ) : null}
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
      <RoleModeDrawer
        open={roleDrawerOpen}
        roleMode={roleModeQuery.data}
        onClose={() => setRoleDrawerOpen(false)}
        onSelect={(roleCode) => void roleModeMutation.mutateAsync(roleCode)}
        isPending={roleModeMutation.isPending}
        errorText={roleModeMutation.error ? errorMessage(roleModeMutation.error, "Не удалось переключить роль") : null}
      />
      <EstimateDrawer
        externalUserId={externalUserId}
        estimateId={selectedEstimateId}
        onClose={() => setSelectedEstimateId(null)}
        onFocusPanel={setPanePanel}
        onOpenOrder={openOrder}
      />
      <OrderDrawer
        externalUserId={externalUserId}
        orderId={selectedOrderId}
        onClose={() => setSelectedOrderId(null)}
      />
    </div>
  );
}

function LaunchGate() {
  return (
    <div className="screen-center">
      <div className="error-card launch-gate">
        <strong>Откройте ПриДел внутри MAX</strong>
        <p>
          Мини-приложение работает внутри клиента MAX. Если открыть ссылку в обычном браузере, рабочая сессия не
          создаётся.
        </p>
        <div className="action-row">
          <button className="btn btn-primary" onClick={() => window.location.assign(MAX_BOT_STARTAPP_URL)}>
            Открыть в MAX
          </button>
        </div>
        <p className="muted">Если MAX уже открыт, перейдите в бота ПриДел и нажмите “Открыть приложение”.</p>
      </div>
    </div>
  );
}

function AppBody() {
  const bridge = resolveBridge();
  const shouldShowLaunchGate = !bridge.embedded && !bridge.initData;

  useEffect(() => {
    prepareBridge();
  }, []);

  const authQuery = useQuery({
    queryKey: ["auth"],
    queryFn: () => api.auth(),
    enabled: !shouldShowLaunchGate,
  });

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap", authQuery.data?.telegram_id],
    queryFn: () => api.bootstrap(authQuery.data?.telegram_id as number),
    enabled: !shouldShowLaunchGate && Boolean(authQuery.data?.telegram_id),
  });

  if (shouldShowLaunchGate) {
    return <LaunchGate />;
  }

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
