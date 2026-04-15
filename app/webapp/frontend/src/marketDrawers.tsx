import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import {
  EmptyState,
  ReviewCard,
  SectionCard,
  TrustBadgeCloud,
  errorMessage,
  formatAgo,
  money,
  ratingSummary,
  renderStars,
  statusLabel,
  toneClass,
} from "./appHelpers";
import type { JobPostResponseList, RoleModeResponse } from "./types";

export function BoardResponsesDrawer({
  externalUserId,
  postId,
  onClose,
}: {
  externalUserId: number;
  postId: number | null;
  onClose: () => void;
}) {
  const responsesQuery = useQuery({
    queryKey: ["board-responses", externalUserId, postId],
    queryFn: () => api.listBoardResponses(externalUserId, postId as number),
    enabled: postId !== null,
  });

  if (postId === null) {
    return null;
  }

  const payload: JobPostResponseList | undefined = responsesQuery.data;

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>{payload?.post.title || "Отклики на заявку"}</h3>
            <p>{payload ? `${payload.meta.count} откликов` : "Собираем отклики"}</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        {responsesQuery.isPending ? (
          <EmptyState title="Загружаем отклики" subtitle="Подтягиваем ответы мастеров на вашу заявку." />
        ) : responsesQuery.error ? (
          <EmptyState title="Не удалось открыть отклики" subtitle={errorMessage(responsesQuery.error, "Попробуйте ещё раз")} />
        ) : payload?.items.length ? (
          <div className="panel-stack">
            {payload.items.map((item) => (
              <article key={item.id} className="glass-card review-card">
                <div className="card-topline">
                  <span className={`pill ${toneClass(item.status)}`}>{statusLabel(item.status)}</span>
                  <span className="muted">{formatAgo(item.created_at)}</span>
                </div>
                <h4>{item.responder.name}</h4>
                <p>{item.message}</p>
                <div className="meta-cloud">
                  {item.price_offer ? <span>{money(item.price_offer)} ₽</span> : null}
                  {item.eta_label ? <span>{item.eta_label}</span> : null}
                  {item.responder.username ? <span>@{item.responder.username}</span> : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Пока без откликов" subtitle="Как только мастера ответят на заявку, они появятся здесь." />
        )}
      </aside>
    </div>
  );
}

export function MasterDrawer({
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
                  {masterQuery.data.hourly_rate_from ? <span>от {money(masterQuery.data.hourly_rate_from)} ₽</span> : null}
                </div>
                <p>{masterQuery.data.bio || "Профиль пока без описания."}</p>
              </div>
            </SectionCard>

            <SectionCard title="Навыки" subtitle="Ключевые теги, чтобы быстро понять специализацию.">
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
              <SectionCard title="Портфолио" subtitle="Короткая витрина кейсов и ссылок.">
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

            <SectionCard title="Проверенные отзывы" subtitle="Отзывы привязаны к завершённым заказам и реальным сделкам.">
              {masterQuery.data.reviews.length ? (
                <div className="timeline-list">
                  {masterQuery.data.reviews.map((review) => (
                    <ReviewCard key={review.id} review={review} />
                  ))}
                </div>
              ) : (
                <EmptyState title="Отзывов пока нет" subtitle="Когда появятся оценки по завершённым заказам, они будут здесь." />
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

export function RoleModeDrawer({
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
            <h3>Роль и режим</h3>
            <p>Интерфейс и права аккуратно перестраиваются под выбранный контекст.</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <SectionCard title="Активный режим" subtitle="Переключение помогает смотреть на продукт глазами клиента, мастера или оператора.">
          <div className="meta-cloud">
            <span>{roleMode.active_role_label}</span>
            <span>Максимум: {roleMode.max_role_label}</span>
          </div>
          {roleMode.is_role_switched ? (
            <p className="muted">
              Включён временный рабочий режим. Базовые роли не меняются, меняется только текущий контекст.
            </p>
          ) : null}
          <div className="role-switch-grid">
            <button className={`quick-card ${!roleMode.role_override ? "active-card" : ""}`} onClick={() => onSelect(null)} disabled={isPending}>
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

