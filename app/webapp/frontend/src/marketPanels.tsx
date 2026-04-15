import { useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "./api";
import {
  EmptyState,
  SectionCard,
  TrustBadgeCloud,
  errorMessage,
  formatAgo,
  formatBudgetRange,
  money,
  ratingSummary,
  renderStars,
  toneClass,
  statusLabel,
} from "./appHelpers";
import type { BootstrapResponse, JobPost, MasterCard } from "./types";

const boardPostSchema = z.object({
  title: z.string().min(4).max(160),
  description: z.string().min(12).max(1200),
  city: z.string().max(120).optional(),
  budget_from: z.number().int().nonnegative().nullable(),
  budget_to: z.number().int().nonnegative().nullable(),
  urgency: z.enum(["normal", "urgent", "asap"]),
});

const BOARD_EXAMPLES = [
  {
    title: "Поменять розетки в квартире",
    description: "Нужно заменить три розетки, проверить контакты и аккуратно поставить рамки.",
  },
  {
    title: "Установить смеситель",
    description: "Нужна замена старого смесителя и проверка соединений без подтеканий.",
  },
  {
    title: "Собрать шкаф",
    description: "Собрать новый шкаф, выставить по уровню и убрать упаковку.",
  },
];

const QUICK_RESPONSE_TEMPLATES = [
  "Могу сегодня, инструмент с собой.",
  "Нужны фото и адрес, дальше быстро сориентирую.",
  "Готов закрыть задачу без лишней переписки.",
];

export function BoardPanel({
  externalUserId,
  bootstrap,
  onOpenResponses,
}: {
  externalUserId: number;
  bootstrap: BootstrapResponse;
  onOpenResponses: (postId: number) => void;
}) {
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<"all" | "own">("all");
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
    queryKey: ["board-posts", externalUserId, scope],
    queryFn: () =>
      api.listBoardPosts(externalUserId, {
        only_own: scope === "own",
      }),
    initialData:
      scope === "all"
        ? { items: bootstrap.board.items, meta: { limit: 20, offset: 0 } }
        : undefined,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const parsed = boardPostSchema.parse({
        title: formState.title,
        description: formState.description,
        city: formState.city || undefined,
        budget_from: formState.budget_from ? Number(formState.budget_from) : null,
        budget_to: formState.budget_to ? Number(formState.budget_to) : null,
        urgency: formState.urgency as "normal" | "urgent" | "asap",
      });
      return api.createBoardPost(externalUserId, parsed);
    },
    onSuccess: async () => {
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
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  const posts = postsQuery.data?.items ?? [];
  const ownVisiblePosts = posts.filter((post) => post.is_owner);
  const totalResponses = ownVisiblePosts.reduce((sum, post) => sum + post.response_count, 0);

  return (
    <div className="panel-stack market-pane">
      <section className="market-overview section-card">
        <div className="market-overview-copy">
          <span className="eyebrow">Лента спроса</span>
          <h3>Заказы, которые можно понять за пару секунд</h3>
          <p>
            Сначала видно главное: что нужно сделать, где, насколько срочно и сколько уже есть
            откликов. Это снимает лишнее напряжение и сокращает число промахов.
          </p>
        </div>
        <div className="market-overview-stats">
          <div className="metric-card hero-metric">
            <span>Открыто</span>
            <strong>{bootstrap.board.total}</strong>
          </div>
          <div className="metric-card hero-metric">
            <span>Мои заявки</span>
            <strong>{ownVisiblePosts.length}</strong>
          </div>
          <div className="metric-card hero-metric">
            <span>Отклики</span>
            <strong>{totalResponses}</strong>
          </div>
        </div>
      </section>

      {bootstrap.capabilities.can_post_jobs ? (
        <SectionCard
          title="Создать заявку"
          subtitle="Минимум полей. Сначала понятный запрос, а не длинная форма."
          actions={
            <div className="tag-row">
              {BOARD_EXAMPLES.map((example) => (
                <button
                  key={example.title}
                  className="tag suggestion-chip"
                  type="button"
                  onClick={() =>
                    setFormState((state) => ({
                      ...state,
                      title: example.title,
                      description: example.description,
                    }))
                  }
                >
                  {example.title}
                </button>
              ))}
            </div>
          }
        >
          <form
            className="stack-form market-composer"
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
              placeholder="Коротко опишите задачу: что сделать, где и что важно учесть"
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
              <div className="segmented">
                {[
                  { id: "normal", label: "Спокойно" },
                  { id: "urgent", label: "Скоро" },
                  { id: "asap", label: "Как можно быстрее" },
                ].map((item) => (
                  <button
                    key={item.id}
                    className={`segment ${formState.urgency === item.id ? "active" : ""}`}
                    type="button"
                    onClick={() => setFormState((state) => ({ ...state, urgency: item.id }))}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
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
              <p className="inline-error">{errorMessage(createMutation.error, "Не удалось опубликовать заявку")}</p>
            ) : null}
            <div className="action-row">
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Публикуем..." : "Опубликовать заявку"}
              </button>
              <span className="muted">Детали и фото можно добавить позже. Сейчас важнее ясная суть.</span>
            </div>
          </form>
        </SectionCard>
      ) : null}

      <SectionCard
        title="Поток заявок"
        subtitle="Сначала самое важное. Всё остальное открывается только когда нужно."
        actions={
          <div className="segmented">
            {[
              { id: "all" as const, label: "Все" },
              { id: "own" as const, label: "Мои" },
            ].map((item) => (
              <button
                key={item.id}
                className={`segment ${scope === item.id ? "active" : ""}`}
                type="button"
                onClick={() => setScope(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        }
      >
        <div className="insight-strip">
          <span className="tag">Понятный бюджет</span>
          <span className="tag">Отклики без долгой переписки</span>
          <span className="tag">Каждая карточка ведёт к действию</span>
        </div>
      </SectionCard>

      <div className="card-list">
        {posts.length ? (
          posts.map((post: JobPost) => (
            <article key={post.id} className="glass-card board-card market-card">
              <div className="card-topline">
                <span className={`pill ${toneClass(post.urgency)}`}>{statusLabel(post.urgency)}</span>
                <span className="tag soft-tag">{post.is_owner ? "Моя заявка" : post.author.name}</span>
                <span className="muted">{formatAgo(post.created_at)}</span>
              </div>
              <h4>{post.title}</h4>
              <p>{post.description}</p>
              <div className="meta-cloud">
                {post.city ? <span>{post.city}</span> : null}
                {formatBudgetRange(post) ? <span>{formatBudgetRange(post)}</span> : null}
                {post.desired_start_label ? <span>{post.desired_start_label}</span> : null}
                <span>{post.response_count} откликов</span>
              </div>
              <div className="action-row">
                {post.is_owner ? (
                  post.response_count ? (
                    <button className="btn btn-primary" onClick={() => onOpenResponses(post.id)}>
                      Посмотреть отклики
                    </button>
                  ) : (
                    <span className="muted">Пока без откликов</span>
                  )
                ) : null}
                {!post.is_owner && post.has_responded ? <span className="tag">Вы уже откликнулись</span> : null}
                {post.can_respond ? (
                  <button className="btn" onClick={() => setResponsePostId(post.id)}>
                    {responsePostId === post.id ? "Свернуть отклик" : "Откликнуться"}
                  </button>
                ) : null}
              </div>
              {responsePostId === post.id ? (
                <div className="inline-composer response-composer">
                  <div className="tag-row">
                    {QUICK_RESPONSE_TEMPLATES.map((template) => (
                      <button
                        key={template}
                        className="tag suggestion-chip"
                        type="button"
                        onClick={() => setResponseMessage(template)}
                      >
                        {template}
                      </button>
                    ))}
                  </div>
                  <textarea
                    className="textarea compact"
                    placeholder="Коротко: когда сможете взяться, как решите задачу и что важно учесть"
                    value={responseMessage}
                    onChange={(event) => setResponseMessage(event.target.value)}
                  />
                  <div className="row-grid">
                    <input
                      className="input"
                      type="number"
                      min="0"
                      placeholder="Цена, если хотите указать"
                      value={responsePrice}
                      onChange={(event) => setResponsePrice(event.target.value)}
                    />
                    <div className="meta-cloud">
                      <span>Чем яснее отклик, тем быстрее клиент принимает решение.</span>
                    </div>
                  </div>
                  {respondMutation.error ? (
                    <p className="inline-error">{errorMessage(respondMutation.error, "Не удалось отправить отклик")}</p>
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
              ) : null}
            </article>
          ))
        ) : (
          <EmptyState
            title={scope === "own" ? "Ваших заявок пока нет" : "Пока нет открытых заявок"}
            subtitle="Когда появится новый спрос, он сразу окажется здесь в понятной короткой ленте."
          />
        )}
      </div>
    </div>
  );
}

export function NetworkPanel({
  externalUserId,
  bootstrap,
  onOpenMaster,
  onOpenProfile,
}: {
  externalUserId: number;
  bootstrap: BootstrapResponse;
  onOpenMaster: (externalUserId: number) => void;
  onOpenProfile: () => void;
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
    initialData: { items: bootstrap.network.items, meta: { limit: 20, offset: 0 } },
  });

  return (
    <div className="panel-stack market-pane">
      <section className="market-overview section-card">
        <div className="market-overview-copy">
          <span className="eyebrow">Сеть мастеров</span>
          <h3>Публичные страницы мастеров как живой рынок доверия</h3>
          <p>
            Тут сразу видно рейтинг, занятость, опыт и сильные стороны мастера, чтобы решение
            принималось быстро и спокойно.
          </p>
        </div>
        {bootstrap.capabilities.can_publish_master_profile ? (
          <div className="hero-actions">
            <button className="btn btn-primary" onClick={onOpenProfile}>
              Редактировать мою страницу
            </button>
          </div>
        ) : null}
      </section>

      <SectionCard title="Подобрать мастера" subtitle="Пара фильтров вместо тяжёлого каталога анкет.">
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
                type="button"
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
            <article key={master.external_user_id} className="glass-card master-card market-card">
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
                {master.hourly_rate_from ? <span>от {money(master.hourly_rate_from)} ₽</span> : null}
              </div>
              <TrustBadgeCloud badges={master.trust_badges} limit={3} />
              <div className="tag-row">
                {master.skills.slice(0, 4).map((skill) => (
                  <span key={skill} className="tag">
                    {skill}
                  </span>
                ))}
              </div>
              <div className="action-row">
                <button className="btn btn-primary" onClick={() => onOpenMaster(master.external_user_id)}>
                  Открыть страницу
                </button>
              </div>
            </article>
          ))
        ) : (
          <EmptyState
            title="Сеть пока пустая"
            subtitle="Как только мастера опубликуют свои страницы, они появятся здесь в одном спокойном потоке."
          />
        )}
      </div>
    </div>
  );
}

