import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { EmptyState, ReviewCard, SectionCard, errorMessage, formatAgo, money, statusLabel, toneClass } from "./appHelpers";
import type { OrderDetail } from "./types";

export function OrderDrawer({
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

  const refresh = async () => {
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
    onSuccess: refresh,
  });

  const assignMutation = useMutation({
    mutationFn: async () => api.assignOrderToSelf(externalUserId, orderId as number),
    onSuccess: refresh,
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
      await refresh();
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
                          {item.quantity} × {money(item.unit_price)} ₽
                        </p>
                      </div>
                      <strong>{money(item.subtotal)} ₽</strong>
                    </article>
                  ))}
                </div>
                <div className="metric-grid dense">
                  <div className="metric-card">
                    <span>Сумма</span>
                    <strong>{money(order.estimate.total)} ₽</strong>
                  </div>
                  <div className="metric-card">
                    <span>Итог</span>
                    <strong>{money(order.estimate.final)} ₽</strong>
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
                    <select className="input" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)}>
                      <option value="">Причина отмены</option>
                      {order.cancel_reasons.map((option) => (
                        <option key={option.code} value={option.code}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input className="input" placeholder="Причина отмены" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} />
                  )}
                  <div className="action-row">
                    <button className="btn" onClick={() => void statusMutation.mutateAsync({ status: "cancelled", reason: cancelReason || null })}>
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
                          <strong>{money(paymentQuery.data.amount)} ₽</strong>
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
                        <button className="btn btn-primary" onClick={() => void statusMutation.mutateAsync({ status: "paid" })}>
                          Отметить оплаченным
                        </button>
                      </div>
                    </>
                  ) : null}
                  {paymentQuery.error ? <p className="inline-error">{errorMessage(paymentQuery.error, "Не удалось получить реквизиты")}</p> : null}
                </div>
              ) : null}

              {statusMutation.error ? <p className="inline-error">{errorMessage(statusMutation.error, "Не удалось обновить заказ")}</p> : null}
              {assignMutation.error ? <p className="inline-error">{errorMessage(assignMutation.error, "Не удалось назначить заказ")}</p> : null}
            </SectionCard>

            {order.review.item || order.review.can_create ? (
              <SectionCard title="Отзыв о мастере" subtitle="Оценка создаётся прямо из завершённой сделки, путь остаётся коротким и понятным.">
                {order.review.item ? <ReviewCard review={order.review.item} /> : null}
                {order.review.can_create ? (
                  <div className="inline-composer">
                    <div className="review-rating-picker">
                      {[1, 2, 3, 4, 5].map((value) => (
                        <button key={value} className={`star-btn ${reviewRating >= value ? "active" : ""}`} onClick={() => setReviewRating(value)}>
                          ★
                        </button>
                      ))}
                      <span className="muted">{reviewRating} из 5</span>
                    </div>
                    <input className="input" placeholder="Короткий заголовок отзыва" value={reviewHeadline} onChange={(event) => setReviewHeadline(event.target.value)} />
                    <textarea className="textarea compact" placeholder="Что особенно понравилось в работе мастера" value={reviewBody} onChange={(event) => setReviewBody(event.target.value)} />
                    <label className="toggle">
                      <input type="checkbox" checked={reviewIsPublic} onChange={(event) => setReviewIsPublic(event.target.checked)} />
                      <span>Показывать отзыв в публичном профиле мастера</span>
                    </label>
                    <div className="action-row">
                      <button className="btn btn-primary" onClick={() => void reviewMutation.mutateAsync()}>
                        {reviewMutation.isPending ? "Сохраняем..." : "Оставить отзыв"}
                      </button>
                    </div>
                    {reviewMutation.error ? <p className="inline-error">{errorMessage(reviewMutation.error, "Не удалось сохранить отзыв")}</p> : null}
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

