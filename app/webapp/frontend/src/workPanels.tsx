import { useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { EmptyState, SectionCard, errorMessage, formatAgo, money, statusLabel, toneClass, useCompactLayout } from "./appHelpers";
import type { BootstrapResponse, EstimateSummary, NotificationItem, OrderSummary, PaneId } from "./types";

export function WorkspacePanel({
  bootstrap,
  onFocusPanel,
  onOpenWorkflow,
}: {
  bootstrap: BootstrapResponse;
  onFocusPanel: (pane: PaneId, panelId: string) => void;
  onOpenWorkflow: (callback?: string | null) => void;
}) {
  const isCompact = useCompactLayout();
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
    metrics.push({ label: "Заработано", value: `${money(bootstrap.workspace.total_earned)} ₽` });
  }
  const nextSteps = [
    ...bootstrap.workspace.action_items.slice(0, isCompact ? 2 : 3).map((task) => ({
      id: `workflow-${task.callback}`,
      title: task.title,
      meta: "Сейчас",
      onClick: () => onOpenWorkflow(task.callback),
    })),
    ...bootstrap.workspace.onboarding.slice(0, isCompact ? 1 : 2).map((task) => ({
      id: `setup-${task.id}`,
      title: task.title,
      meta: "Профиль",
      onClick: () => onFocusPanel("bottom", "profile-card"),
    })),
  ].slice(0, isCompact ? 3 : 4);

  return (
    <div className={`panel-stack workspace-pane ${isCompact ? "compact-market-pane" : ""}`}>
      <section className={`${isCompact ? "section-card compact-hero-card" : "market-overview section-card"}`}>
        <div className="market-overview-copy">
          <span className="eyebrow">Рабочий стол</span>
          <h3>{isCompact ? "Главное сейчас" : "Текущая работа без перегруза"}</h3>
          <p>{isCompact ? "Числа, шаги и переходы." : "Сводка, следующий шаг и быстрые переходы."}</p>
        </div>
      </section>

      <SectionCard title={isCompact ? "Сейчас" : "Сводка"}>
        <div className={`metric-grid ${isCompact ? "metric-grid-compact" : ""}`}>
          {metrics.map((metric) => (
            <div key={metric.label} className="metric-card">
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </SectionCard>

      {nextSteps.length ? (
        <SectionCard title="Дальше">
          <div className="task-list">
            {nextSteps.map((step) => (
              <button key={step.id} className="task-card task-card-compact" onClick={step.onClick}>
                <strong>{step.title}</strong>
                <span>{step.meta}</span>
              </button>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title={isCompact ? "Перейти" : "Быстрые переходы"}>
        <div className={`quick-grid ${isCompact ? "quick-grid-compact" : ""}`}>
          {[
            { label: "Каталог", pane: "top" as PaneId, panel: "catalog-browser" },
            { label: "Сметы", pane: "top" as PaneId, panel: "estimates-list" },
            { label: "Заказы", pane: "bottom" as PaneId, panel: "orders-list" },
            { label: "Профиль", pane: "bottom" as PaneId, panel: "profile-card" },
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

export function CatalogPanel({
  externalUserId,
  canCreateEstimate,
  onOpenEstimate,
}: {
  externalUserId: number;
  canCreateEstimate: boolean;
  onOpenEstimate: (estimateId: number) => void;
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
    mutationFn: async (item: { id: number }) => {
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
      setStatus(`Добавили в смету #${estimateId}`);
      await queryClient.invalidateQueries({ queryKey: ["estimates", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["estimate-detail", externalUserId] });
      onOpenEstimate(estimateId);
    },
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Собрать смету">
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
          <EmptyState title="Начните поиск" subtitle="Минимум 2 символа." />
        ) : searchQuery.data?.length ? (
          searchQuery.data.map((item) => (
            <article key={item.id} className="glass-card compact-card">
              <div>
                <h4>{item.name}</h4>
                <p>
                  {money(item.price || item.price_min)} ₽ / {item.unit}
                </p>
              </div>
              {canCreateEstimate ? (
                <button className="btn btn-primary" onClick={() => void addItemMutation.mutateAsync(item)}>
                  В смету
                </button>
              ) : null}
            </article>
          ))
        ) : (
          <EmptyState title="Ничего не нашли" subtitle="Попробуйте короче или шире запрос." />
        )}
      </div>
    </div>
  );
}

export function EstimatesPanel({
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
            <button key={estimate.id} className="glass-card compact-card card-button" onClick={() => onOpenEstimate(estimate.id)}>
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
          <EmptyState title="Смет пока нет" subtitle={canCreateEstimate ? "Создайте первую." : "Они появятся после запуска."} />
        )}
      </div>
    </div>
  );
}

export function OrdersPanel({
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
      <SectionCard title="Заказы" />
      <div className="card-list">
        {ordersQuery.data?.length ? (
          ordersQuery.data.map((order: OrderSummary) => (
            <button key={order.id} className="glass-card compact-card card-button" onClick={() => onOpenOrder(order.id)}>
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
          <EmptyState title="Заказов пока нет" subtitle="Они появятся после запуска работы." />
        )}
      </div>
    </div>
  );
}

export function NotificationsPanel({
  externalUserId,
  onOpenTarget,
}: {
  externalUserId: number;
  onOpenTarget: (notification: NotificationItem) => void;
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
      <SectionCard title="Уведомления" />
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
                  <button className="btn btn-primary" onClick={() => onOpenTarget(notification)}>
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
          <EmptyState title="Пусто" subtitle="Новые события появятся здесь." />
        )}
      </div>
    </div>
  );
}

export function ApprovalsPanel({ externalUserId }: { externalUserId: number }) {
  const queryClient = useQueryClient();
  const [rejectId, setRejectId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const approvalsQuery = useQuery({
    queryKey: ["approvals", externalUserId],
    queryFn: () => api.listApprovals(externalUserId),
  });

  const actionMutation = useMutation({
    mutationFn: async ({ requestId, action, comment }: { requestId: number; action: "approve" | "reject"; comment?: string }) =>
      api.processApproval(externalUserId, requestId, action, comment),
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
      <SectionCard title="Согласования" />
      <div className="card-list">
        {approvalsQuery.data?.length ? (
          approvalsQuery.data.map((approval) => (
            <article key={approval.id} className="glass-card compact-card align-start">
              <div className="card-topline">
                <span className={`pill ${toneClass(approval.status)}`}>{statusLabel(approval.status)}</span>
                <span className="muted">Смета #{approval.estimate_id}</span>
              </div>
              <h4>Запрос #{approval.id}</h4>
              <p>
                {approval.type}: {approval.value}%
              </p>
              <div className="action-row">
                <button className="btn btn-primary" onClick={() => void actionMutation.mutateAsync({ requestId: approval.id, action: "approve" })}>
                  Одобрить
                </button>
                <button className="btn" onClick={() => setRejectId((current) => (current === approval.id ? null : approval.id))}>
                  Отклонить
                </button>
              </div>
              {rejectId === approval.id ? (
                <div className="inline-composer">
                  <textarea className="textarea compact" placeholder="Короткий комментарий к отклонению" value={comment} onChange={(event) => setComment(event.target.value)} />
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
            </article>
          ))
        ) : (
          <EmptyState title="Очередь чистая" subtitle="Решений пока нет." />
        )}
      </div>
    </div>
  );
}

export function AnalyticsPanel({ externalUserId }: { externalUserId: number }) {
  const analyticsQuery = useQuery({
    queryKey: ["analytics", externalUserId],
    queryFn: () => api.getAnalytics(externalUserId),
  });

  return (
    <div className="panel-stack">
      <SectionCard title="Аналитика">
        {analyticsQuery.data ? (
          <div className="metric-grid dense">
            {[
              { label: "Пользователи", value: analyticsQuery.data.users },
              { label: "Мастера", value: analyticsQuery.data.masters },
              { label: "Сметы", value: analyticsQuery.data.estimates },
              { label: "Заказы", value: analyticsQuery.data.orders },
              { label: "Оборот", value: `${money(analyticsQuery.data.gross)} ₽` },
              { label: "Чистый доход", value: `${money(analyticsQuery.data.platform_net)} ₽` },
            ].map((metric) => (
              <div key={metric.label} className="metric-card">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Считаем..." subtitle="Собираем данные." />
        )}
      </SectionCard>
    </div>
  );
}
