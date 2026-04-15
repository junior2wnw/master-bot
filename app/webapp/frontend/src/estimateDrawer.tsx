import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { EmptyState, SectionCard, errorMessage, money, triggerBlobDownload } from "./appHelpers";
import type { EstimateDetail, EstimateQrPayload, PaneId } from "./types";

export function EstimateDrawer({
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

  const refresh = async () => {
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
    onSuccess: refresh,
  });

  const deleteItemMutation = useMutation({
    mutationFn: async (lineItemId: number) => api.deleteEstimateItem(externalUserId, estimateId as number, lineItemId),
    onSuccess: refresh,
  });

  const statusMutation = useMutation({
    mutationFn: async (body: { status: string; client_external_id?: number | null }) =>
      api.updateEstimateStatus(externalUserId, estimateId as number, body),
    onSuccess: refresh,
  });

  const discountMutation = useMutation({
    mutationFn: async (value: number) => api.requestEstimateDiscount(externalUserId, estimateId as number, value),
    onSuccess: async () => {
      setDiscountOpen(false);
      setDiscountValue("");
      await refresh();
    },
  });

  const deleteEstimateMutation = useMutation({
    mutationFn: async () => api.deleteEstimate(externalUserId, estimateId as number),
    onSuccess: async () => {
      await refresh();
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
      await refresh();
      onOpenOrder(order.id);
    },
  });

  if (estimateId === null) {
    return null;
  }

  const estimate: EstimateDetail | undefined = estimateQuery.data;
  const capabilities = estimate?.capabilities ?? {};
  const qrPayload: EstimateQrPayload | undefined = qrQuery.data;

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer wide-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>{estimate ? `Смета #${estimate.id}` : "Смета"}</h3>
            <p>{estimate ? `${estimate.status} • версия ${estimate.version}` : "Загружаем детали"}</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>

        {!estimate ? (
          <EmptyState title="Загружаем смету" subtitle="Собираем позиции, статусы и доступные действия." />
        ) : (
          <div className="panel-stack">
            <SectionCard title="Состав" subtitle="Редактирование остаётся внутри drawer и не ломает основной split-view.">
              <div className="card-list">
                {estimate.items.length ? (
                  estimate.items.map((item, index) => (
                    <article key={item.id} className="glass-card compact-card align-start">
                      <div>
                        <div className="card-topline">
                          <span className="muted">#{index + 1}</span>
                          <span className="muted">
                            {item.quantity} {item.unit} • {money(item.unit_price)} ₽
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
                            –
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
                  <EmptyState title="Смета пока пустая" subtitle="Добавьте работы через каталог, когда будете готовы." />
                )}
              </div>
              {capabilities.can_edit && estimate.status === "draft" ? (
                <div className="action-row">
                  <button className="btn btn-primary" onClick={() => onFocusPanel("top", "catalog-browser")}>
                    Открыть каталог сверху
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
                  <strong>{money(estimate.total)} ₽</strong>
                </div>
                <div className="metric-card">
                  <span>Скидка</span>
                  <strong>{money(estimate.discount)} ₽</strong>
                </div>
                <div className="metric-card">
                  <span>Итог</span>
                  <strong>{money(estimate.final)} ₽</strong>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Действия" subtitle="Только сценарии, которые реально доступны по правам и статусу.">
              <div className="action-row">
                {capabilities.can_send_to_client && estimate.status === "draft" ? (
                  <button className="btn btn-primary" onClick={() => setSendOpen((current) => !current)}>
                    Отправить клиенту
                  </button>
                ) : null}
                {capabilities.can_client_respond && estimate.status === "client_review" ? (
                  <>
                    <button className="btn btn-primary" onClick={() => void statusMutation.mutateAsync({ status: "approved" })}>
                      Согласовать
                    </button>
                    <button className="btn" onClick={() => void statusMutation.mutateAsync({ status: "draft" })}>
                      Вернуть в черновик
                    </button>
                  </>
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
                  <input className="input" placeholder="MAX ID клиента" value={clientExternalId} onChange={(event) => setClientExternalId(event.target.value)} />
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
                      Отправить смету
                    </button>
                  </div>
                </div>
              ) : null}

              {discountOpen ? (
                <div className="inline-composer">
                  <input className="input" type="number" min="0" placeholder="Скидка в процентах" value={discountValue} onChange={(event) => setDiscountValue(event.target.value)} />
                  <div className="action-row">
                    <button className="btn btn-primary" onClick={() => void discountMutation.mutateAsync(Number(discountValue || 0))}>
                      Запросить скидку
                    </button>
                  </div>
                </div>
              ) : null}

              {orderOpen ? (
                <div className="inline-composer">
                  <input className="input" placeholder="Адрес выполнения работ" value={orderForm.address} onChange={(event) => setOrderForm((state) => ({ ...state, address: event.target.value }))} />
                  <div className="row-grid">
                    <select className="input" value={orderForm.urgency} onChange={(event) => setOrderForm((state) => ({ ...state, urgency: event.target.value }))}>
                      <option value="normal">Спокойно</option>
                      <option value="urgent">Скоро</option>
                      <option value="asap">Как можно быстрее</option>
                    </select>
                    <input className="input" placeholder="Заметка" value={orderForm.notes} onChange={(event) => setOrderForm((state) => ({ ...state, notes: event.target.value }))} />
                  </div>
                  <div className="action-row">
                    <button className="btn btn-primary" onClick={() => void createOrderMutation.mutateAsync()}>
                      Создать заказ
                    </button>
                  </div>
                </div>
              ) : null}
            </SectionCard>

            {capabilities.can_export ? (
              <SectionCard title="Файлы и оплата" subtitle="Экспорт и QR доступны прямо из drawer, без разрыва сценария.">
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
                    {qrPayload?.qr_image ? <img className="qr-preview" alt="QR оплаты" src={`data:image/png;base64,${qrPayload.qr_image}`} /> : null}
                    <div className="meta-cloud">
                      {qrPayload?.recipient ? <span>{qrPayload.recipient}</span> : null}
                      {qrPayload?.bank ? <span>{qrPayload.bank}</span> : null}
                      {qrPayload?.sbp_phone ? <span>{qrPayload.sbp_phone}</span> : null}
                    </div>
                    {qrPayload?.fallback_notice ? <p className="muted">{qrPayload.fallback_notice}</p> : null}
                    {qrQuery.error ? <p className="inline-error">{errorMessage(qrQuery.error, "Не удалось сформировать QR")}</p> : null}
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

