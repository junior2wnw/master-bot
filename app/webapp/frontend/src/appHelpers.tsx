import { type ReactNode, useEffect, useState } from "react";

import type {
  BootstrapResponse,
  JobPost,
  MasterReviewItem,
  PaneId,
  PanelMeta,
  RoleModeResponse,
  TrustBadge,
} from "./types";

export const MAX_BOT_STARTAPP_URL = "https://max.ru/id026303852801_bot?startapp";
const DESKTOP_SPLIT_QUERY = "(min-width: 1040px)";

export function money(value?: number | null): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value ?? 0);
}

export function formatAgo(value?: string | null): string {
  if (!value) {
    return "только что";
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

export function statusLabel(status: string): string {
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
    cancelled: "Отменён",
    urgent: "Скоро",
    asap: "Как можно быстрее",
    busy: "Занят",
    offline: "Скрыт",
    normal: "Спокойно",
    pending: "Ожидает",
    executed: "Выполнено",
    rejected: "Отклонено",
  };
  return map[status] ?? status;
}

export function toneClass(status: string): string {
  if (["open", "approved", "paid", "completed", "executed"].includes(status)) {
    return "tone-success";
  }
  if (["urgent", "asap", "busy", "client_review", "pending"].includes(status)) {
    return "tone-warn";
  }
  if (["offline", "cancelled", "rejected"].includes(status)) {
    return "tone-muted";
  }
  return "tone-neutral";
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function reviewNoun(count: number): string {
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

export function ratingSummary(ratingAverage: number, ratingCount: number): string {
  if (!ratingCount) {
    return "Пока без отзывов";
  }
  return `${ratingAverage.toFixed(1)} • ${ratingCount} ${reviewNoun(ratingCount)}`;
}

export function renderStars(rating: number): string {
  const filled = Math.max(0, Math.min(5, Math.round(rating)));
  return `${"★".repeat(filled)}${"☆".repeat(Math.max(0, 5 - filled))}`;
}

export function formatBudgetRange(post: JobPost): string | null {
  if (!post.budget) {
    return null;
  }
  if (post.budget.from && post.budget.to) {
    return `${money(post.budget.from)}–${money(post.budget.to)} ₽`;
  }
  if (post.budget.from) {
    return `от ${money(post.budget.from)} ₽`;
  }
  if (post.budget.to) {
    return `до ${money(post.budget.to)} ₽`;
  }
  return null;
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function parseWorkflowCallback(callback?: string | null): { type: string; id: number | null } | null {
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

export function useSplitDirection(): "horizontal" | "vertical" {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(DESKTOP_SPLIT_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const media = window.matchMedia(DESKTOP_SPLIT_QUERY);
    const onChange = (event: MediaQueryListEvent) => setIsDesktop(event.matches);
    setIsDesktop(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return isDesktop ? "horizontal" : "vertical";
}

export function Glyph({ name }: { name: string }) {
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

export function TrustBadgeCloud({ badges, limit = 3 }: { badges: TrustBadge[]; limit?: number }) {
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

export function ReviewCard({ review }: { review: MasterReviewItem }) {
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
        <span>{review.is_public ? "Публичный отзыв" : "Частный отзыв"}</span>
      </div>
    </article>
  );
}

export function PanelPicker({
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
      <span>Модуль</span>
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

export function SectionCard({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children?: ReactNode;
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

export function EmptyState({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{subtitle}</p>
    </div>
  );
}

export function SpotlightHero({
  auth,
  bootstrap,
  activeRoleLabel,
  maxRoleLabel,
  canSwitchRole,
  onOpenRoleMode,
  onSelectPreset,
  onOpenModules,
  onOpenProfile,
}: {
  auth: { name: string };
  bootstrap: BootstrapResponse;
  activeRoleLabel: string;
  maxRoleLabel: string;
  canSwitchRole: boolean;
  onOpenRoleMode: () => void;
  onSelectPreset: (presetId: string) => void;
  onOpenModules: () => void;
  onOpenProfile: () => void;
}) {
  const summaryCards = [
    { label: "Заказы на рынке", value: bootstrap.board.total },
    { label: "Мастеров в сети", value: bootstrap.network.total },
    { label: "Активных заказов", value: bootstrap.workspace.active_orders },
    { label: "Сигналов", value: bootstrap.notifications.unread },
  ];

  return (
    <header className="hero-shell" data-testid="spotlight-hero">
      <div className="hero-main glass-card">
        <div className="hero-brand">
          <div className="brand-mark">4-2</div>
          <div>
            <span className="eyebrow">4-2 • ПриДел</span>
            <h1>{auth.name}</h1>
            <p className="hero-role">
              {activeRoleLabel}
              {maxRoleLabel && maxRoleLabel !== activeRoleLabel ? ` • потолок ${maxRoleLabel}` : ""}
            </p>
          </div>
        </div>
        <div className="hero-copy">
          <h2>Одна простая среда для спроса, мастеров и выполнения работ</h2>
          <p>
            Слева и справа не хаос из экранов, а живой рынок: людям легче оставить заявку,
            мастерам легче показать себя и быстрее взять работу.
          </p>
        </div>
        <div className="hero-actions">
          <button className="btn btn-primary" data-testid="hero-preset-market" onClick={() => onSelectPreset("market")}>
            Рынок
          </button>
          <button className="btn" data-testid="hero-preset-workbench" onClick={() => onSelectPreset("workbench")}>
            Работа
          </button>
          <button className="btn" data-testid="hero-open-profile" onClick={onOpenProfile}>
            Профиль
          </button>
          {canSwitchRole ? (
            <button className="btn" data-testid="hero-open-role-mode" onClick={onOpenRoleMode}>
              Роль
            </button>
          ) : null}
          <button className="btn" data-testid="hero-open-modules" onClick={onOpenModules}>
            Модули
          </button>
        </div>
      </div>
      <div className="hero-stats">
        {summaryCards.map((card) => (
          <div key={card.label} className="metric-card hero-metric">
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </div>
    </header>
  );
}

export function paneLabel(paneId: PaneId, direction: "horizontal" | "vertical"): string {
  if (direction === "horizontal") {
    return paneId === "top" ? "Левая половина" : "Правая половина";
  }
  return paneId === "top" ? "Верхняя половина" : "Нижняя половина";
}
