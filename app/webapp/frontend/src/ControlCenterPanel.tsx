import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "./api";
import type {
  ControlBootstrapResponse,
  ControlFeatureFlag,
  ControlInvite,
  ControlInviteActivation,
  ControlStaffingAction,
  ControlUser,
  RoleOption,
} from "./types";

type ControlTab = "team" | "invites" | "moderation" | "flags";

const ROLE_FILTERS: RoleOption[] = [
  { code: "all", label: "Все роли" },
  { code: "master", label: "Мастер" },
  { code: "senior_master", label: "Старший мастер" },
  { code: "admin", label: "Администратор" },
  { code: "product_owner", label: "Product Owner" },
  { code: "client", label: "Клиент" },
];

const USER_STATUS_FILTERS: RoleOption[] = [
  { code: "active", label: "Активные" },
  { code: "inactive", label: "Неактивные" },
  { code: "all", label: "Все" },
];

function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function formatAgo(value?: string | null): string {
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

function toneForInvite(invite: ControlInvite): string {
  if (invite.is_expired || invite.is_exhausted || !invite.is_active) {
    return "tone-muted";
  }
  if (invite.requires_approval) {
    return "tone-warn";
  }
  return "tone-success";
}

function toneForUser(user: ControlUser): string {
  return user.is_active ? "tone-success" : "tone-muted";
}

function toneForStaffing(action: ControlStaffingAction): string {
  if (action.status === "pending") {
    return "tone-warn";
  }
  if (action.status === "executed") {
    return "tone-success";
  }
  return "tone-muted";
}

function toneForFlag(flag: ControlFeatureFlag): string {
  return flag.enabled ? "tone-success" : "tone-muted";
}

function controlTabs(bootstrap: ControlBootstrapResponse): Array<{ id: ControlTab; label: string }> {
  const tabs: Array<{ id: ControlTab; label: string }> = [];
  if (bootstrap.capabilities.can_view_team) {
    tabs.push({ id: "team", label: "Команда" });
  }
  if (bootstrap.capabilities.can_create_invites || bootstrap.capabilities.can_moderate_invites) {
    tabs.push({ id: "invites", label: "Инвайты" });
  }
  if (bootstrap.capabilities.can_moderate_invites || bootstrap.capabilities.can_initiate_staffing || bootstrap.capabilities.can_approve_staffing) {
    tabs.push({ id: "moderation", label: "Модерация" });
  }
  if (bootstrap.capabilities.can_manage_flags) {
    tabs.push({ id: "flags", label: "Флаги" });
  }
  return tabs;
}

export function ControlCenterPanel({ externalUserId }: { externalUserId: number }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<ControlTab>("team");
  const [userQuery, setUserQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [userStatus, setUserStatus] = useState("active");
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [inviteRoleCode, setInviteRoleCode] = useState("");
  const [inviteBranchId, setInviteBranchId] = useState("");
  const [inviteUses, setInviteUses] = useState("1");
  const [inviteExpiryDays, setInviteExpiryDays] = useState("14");
  const [inviteRequiresApproval, setInviteRequiresApproval] = useState(false);
  const [copiedInviteId, setCopiedInviteId] = useState<number | null>(null);
  const [staffingActionType, setStaffingActionType] = useState("suspend");
  const [staffingReason, setStaffingReason] = useState("");
  const [staffingRoleCode, setStaffingRoleCode] = useState("master");
  const [staffingBranchId, setStaffingBranchId] = useState("");

  const deferredQuery = useDeferredValue(userQuery.trim());

  const bootstrapQuery = useQuery({
    queryKey: ["control-bootstrap", externalUserId],
    queryFn: () => api.getControlBootstrap(externalUserId),
  });

  const tabs = useMemo(
    () => (bootstrapQuery.data ? controlTabs(bootstrapQuery.data) : []),
    [bootstrapQuery.data],
  );

  useEffect(() => {
    if (!tabs.length) {
      return;
    }
    if (!tabs.some((item) => item.id === tab)) {
      setTab(tabs[0].id);
    }
  }, [tab, tabs]);

  useEffect(() => {
    if (!bootstrapQuery.data) {
      return;
    }
    if (!inviteRoleCode) {
      setInviteRoleCode(bootstrapQuery.data.ui.invite_role_options[0]?.code ?? "master");
    }
    if (!staffingActionType) {
      setStaffingActionType(bootstrapQuery.data.ui.staffing_action_options[0]?.code ?? "suspend");
    }
  }, [bootstrapQuery.data, inviteRoleCode, staffingActionType]);

  const usersQuery = useQuery({
    queryKey: ["control-users", externalUserId, deferredQuery, roleFilter, userStatus],
    queryFn: () =>
      api.listControlUsers(externalUserId, {
        q: deferredQuery || undefined,
        role: roleFilter !== "all" ? roleFilter : undefined,
        status: userStatus,
        limit: 24,
      }),
    enabled: Boolean(bootstrapQuery.data?.capabilities.can_view_team),
    initialData: bootstrapQuery.data?.users,
  });

  const refreshControl = async () => {
    await queryClient.invalidateQueries({ queryKey: ["control-bootstrap", externalUserId] });
    await queryClient.invalidateQueries({ queryKey: ["control-users", externalUserId] });
  };

  const createInviteMutation = useMutation({
    mutationFn: async () =>
      api.createControlInvite(externalUserId, {
        role_code: inviteRoleCode,
        branch_id: inviteBranchId ? Number(inviteBranchId) : null,
        max_uses: Number(inviteUses) || 1,
        requires_approval: inviteRequiresApproval,
        expires_in_days: inviteExpiryDays ? Number(inviteExpiryDays) : null,
      }),
    onSuccess: async () => {
      setCopiedInviteId(null);
      await refreshControl();
    },
  });

  const moderateInviteMutation = useMutation({
    mutationFn: async (payload: { activationId: number; action: "approve" | "reject" }) =>
      api.moderateControlInviteActivation(externalUserId, payload.activationId, payload.action),
    onSuccess: refreshControl,
  });

  const createStaffingMutation = useMutation({
    mutationFn: async () => {
      if (!selectedUserId) {
        throw new Error("Сначала выберите человека из команды");
      }
      return api.createControlStaffingAction(externalUserId, {
        external_user_id: selectedUserId,
        action_type: staffingActionType,
        reason: staffingReason,
        role_code: staffingActionType === "revoke_role" ? staffingRoleCode : null,
        new_branch_id: staffingActionType === "transfer" && staffingBranchId ? Number(staffingBranchId) : null,
      });
    },
    onSuccess: async () => {
      setStaffingReason("");
      await refreshControl();
    },
  });

  const moderateStaffingMutation = useMutation({
    mutationFn: async (payload: { actionId: number; action: "approve" | "reject" }) =>
      api.moderateControlStaffingAction(externalUserId, payload.actionId, {
        action: payload.action,
      }),
    onSuccess: refreshControl,
  });

  const toggleFlagMutation = useMutation({
    mutationFn: async (payload: { code: string; enabled: boolean }) =>
      api.toggleControlFlag(externalUserId, payload.code, payload.enabled),
    onSuccess: refreshControl,
  });

  const bootstrap = bootstrapQuery.data;
  const users = usersQuery.data?.items ?? [];
  const selectedUser =
    users.find((item) => item.external_user_id === selectedUserId) ??
    bootstrap?.users.items.find((item) => item.external_user_id === selectedUserId) ??
    null;

  useEffect(() => {
    if (!selectedUserId && users[0]) {
      setSelectedUserId(users[0].external_user_id);
    }
  }, [selectedUserId, users]);

  if (bootstrapQuery.isPending) {
    return (
      <div className="empty-state">
        <strong>Собираем контур управления…</strong>
        <p>Подтягиваем команду, инвайты и operational-сигналы.</p>
      </div>
    );
  }

  if (bootstrapQuery.error || !bootstrap) {
    return (
      <div className="empty-state">
        <strong>Control Center пока недоступен</strong>
        <p>{errorText(bootstrapQuery.error, "Не удалось загрузить operational-данные.")}</p>
      </div>
    );
  }

  const userSection = (
    <div className="panel-stack">
      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Команда</h3>
            <p>Быстрый обзор по людям, ролям и веткам без перегрузки лишними настройками.</p>
          </div>
          <span className="pill tone-neutral">{usersQuery.data?.meta.count ?? users.length}</span>
        </header>
        <div className="stack-form">
          <div className="row-grid">
            <label>
              <span className="muted">Поиск</span>
              <input
                className="input"
                value={userQuery}
                onChange={(event) => setUserQuery(event.target.value)}
                placeholder="Имя, username или внешний ID"
              />
            </label>
            <label>
              <span className="muted">Роль</span>
              <select className="input" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
                {ROLE_FILTERS.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            <span className="muted">Статус</span>
            <select className="input" value={userStatus} onChange={(event) => setUserStatus(event.target.value)}>
              {USER_STATUS_FILTERS.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {usersQuery.error ? <p className="inline-error">{errorText(usersQuery.error, "Не удалось загрузить команду")}</p> : null}
        <div className="card-list">
          {users.map((user) => (
            <button
              key={user.external_user_id}
              type="button"
              className={`metric-card task-card control-user-card ${selectedUserId === user.external_user_id ? "active-card" : ""}`}
              onClick={() => setSelectedUserId(user.external_user_id)}
            >
              <div className="card-topline">
                <strong>{user.name}</strong>
                <span className={`pill ${toneForUser(user)}`}>{user.is_active ? "Активен" : "Неактивен"}</span>
              </div>
              <div className="tag-row">
                <span className="tag">{user.active_role_label}</span>
                {user.max_role_label !== user.active_role_label ? <span className="tag">{user.max_role_label}</span> : null}
                <span className="tag">ID {user.external_user_id}</span>
              </div>
              {user.branches.length ? (
                <p className="muted">
                  {user.branches
                    .map((branch) => `${branch.name}${branch.is_senior ? " · senior" : ""}`)
                    .join(", ")}
                </p>
              ) : (
                <p className="muted">Без активной ветки</p>
              )}
            </button>
          ))}
        </div>
      </section>

      {bootstrap.capabilities.can_initiate_staffing ? (
        <section className="section-card">
          <header className="section-head">
            <div>
              <h3>Кадровое действие</h3>
              <p>Точный action flow по выбранному человеку, без лишних экранов и hidden-состояний.</p>
            </div>
            {selectedUser ? <span className="pill tone-neutral">{selectedUser.name}</span> : null}
          </header>
          {!selectedUser ? (
            <p className="muted">Выберите человека выше, чтобы открыть компактный action composer.</p>
          ) : !selectedUser.can_manage ? (
            <p className="muted">Для выбранного человека у текущей роли нет права на кадровое действие.</p>
          ) : (
            <div className="stack-form">
              <div className="row-grid">
                <label>
                  <span className="muted">Действие</span>
                  <select
                    className="input"
                    value={staffingActionType}
                    onChange={(event) => setStaffingActionType(event.target.value)}
                  >
                    {bootstrap.ui.staffing_action_options.map((option) => (
                      <option key={option.code} value={option.code}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                {staffingActionType === "transfer" ? (
                  <label>
                    <span className="muted">Целевая ветка</span>
                    <select className="input" value={staffingBranchId} onChange={(event) => setStaffingBranchId(event.target.value)}>
                      <option value="">Выберите ветку</option>
                      {bootstrap.branches.map((branch) => (
                        <option key={branch.id} value={branch.id}>
                          {branch.name}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : staffingActionType === "revoke_role" ? (
                  <label>
                    <span className="muted">Роль для отзыва</span>
                    <select className="input" value={staffingRoleCode} onChange={(event) => setStaffingRoleCode(event.target.value)}>
                      {selectedUser.roles.map((roleCode) => (
                        <option key={roleCode} value={roleCode}>
                          {roleCode}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <div className="glass-card compact-card align-start">
                    <div>
                      <strong>{selectedUser.name}</strong>
                      <p className="muted">Действие будет создано для внешнего ID {selectedUser.external_user_id}.</p>
                    </div>
                  </div>
                )}
              </div>
              <label>
                <span className="muted">Причина</span>
                <textarea
                  className="textarea compact"
                  value={staffingReason}
                  onChange={(event) => setStaffingReason(event.target.value)}
                  placeholder="Коротко и по делу: почему это действие нужно сейчас."
                />
              </label>
              <div className="action-row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={createStaffingMutation.isPending || !staffingReason.trim()}
                  onClick={() => void createStaffingMutation.mutateAsync()}
                >
                  {createStaffingMutation.isPending ? "Отправляем…" : "Создать действие"}
                </button>
              </div>
              {createStaffingMutation.error ? (
                <p className="inline-error">{errorText(createStaffingMutation.error, "Не удалось создать кадровое действие")}</p>
              ) : null}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );

  const invitesSection = (
    <div className="panel-stack">
      {bootstrap.capabilities.can_create_invites ? (
        <section className="section-card">
          <header className="section-head">
            <div>
              <h3>Новый инвайт</h3>
              <p>Один лёгкий composer вместо длинной админской ветки в боте.</p>
            </div>
          </header>
          <div className="stack-form">
            <div className="row-grid">
              <label>
                <span className="muted">Роль</span>
                <select className="input" value={inviteRoleCode} onChange={(event) => setInviteRoleCode(event.target.value)}>
                  {bootstrap.ui.invite_role_options.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="muted">Ветка</span>
                <select className="input" value={inviteBranchId} onChange={(event) => setInviteBranchId(event.target.value)}>
                  <option value="">Без привязки</option>
                  {bootstrap.branches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="row-grid">
              <label>
                <span className="muted">Использований</span>
                <input className="input" value={inviteUses} onChange={(event) => setInviteUses(event.target.value)} />
              </label>
              <label>
                <span className="muted">Срок, дней</span>
                <input
                  className="input"
                  value={inviteExpiryDays}
                  onChange={(event) => setInviteExpiryDays(event.target.value)}
                  placeholder="14"
                />
              </label>
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                checked={inviteRequiresApproval}
                onChange={(event) => setInviteRequiresApproval(event.target.checked)}
              />
              <span>Подключать через модерацию</span>
            </label>
            <div className="action-row">
              <button type="button" className="btn btn-primary" onClick={() => void createInviteMutation.mutateAsync()}>
                {createInviteMutation.isPending ? "Готовим…" : "Создать инвайт"}
              </button>
            </div>
            {createInviteMutation.error ? (
              <p className="inline-error">{errorText(createInviteMutation.error, "Не удалось создать инвайт")}</p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Последние инвайты</h3>
            <p>Живые коды, статус использования и быстрый copy flow.</p>
          </div>
          <span className="pill tone-neutral">{bootstrap.invites.meta.count}</span>
        </header>
        <div className="card-list">
          {bootstrap.invites.items.map((invite) => (
            <article key={invite.id} className="glass-card">
              <div className="card-topline">
                <strong className="mono-code">{invite.code}</strong>
                <span className={`pill ${toneForInvite(invite)}`}>
                  {invite.is_expired ? "Просрочен" : invite.is_exhausted ? "Использован" : invite.requires_approval ? "Через модерацию" : "Активен"}
                </span>
              </div>
              <div className="tag-row">
                <span className="tag">{invite.role_code}</span>
                {invite.branch_name ? <span className="tag">{invite.branch_name}</span> : null}
                <span className="tag">
                  {invite.used_count}/{invite.max_uses}
                </span>
              </div>
              <p className="muted">
                Создан {formatAgo(invite.created_at)}
                {invite.expires_at ? ` · истекает ${formatAgo(invite.expires_at)}` : ""}
              </p>
              <div className="action-row">
                <button
                  type="button"
                  className="btn"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(invite.code);
                      setCopiedInviteId(invite.id);
                      window.setTimeout(
                        () => setCopiedInviteId((current) => (current === invite.id ? null : current)),
                        1800,
                      );
                    } catch {
                      window.prompt("Скопируйте код инвайта вручную", invite.code);
                    }
                  }}
                >
                  {copiedInviteId === invite.id ? "Скопировано" : "Копировать код"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );

  const moderationSection = (
    <div className="panel-stack">
      {bootstrap.capabilities.can_moderate_invites ? (
        <section className="section-card">
          <header className="section-head">
            <div>
              <h3>Ожидающие подключения</h3>
              <p>Модерация новых входов в сеть мастеров без скачков между ботом и админкой.</p>
            </div>
            <span className="pill tone-warn">{bootstrap.invite_activations.meta.count}</span>
          </header>
          <div className="card-list">
            {bootstrap.invite_activations.items.map((activation: ControlInviteActivation) => (
              <article key={activation.id} className="glass-card">
                <div className="card-topline">
                  <strong>{activation.user?.name ?? `Пользователь #${activation.id}`}</strong>
                  <span className="pill tone-warn">{activation.status}</span>
                </div>
                <div className="tag-row">
                  {activation.invite?.role_code ? <span className="tag">{activation.invite.role_code}</span> : null}
                  {activation.invite?.branch_name ? <span className="tag">{activation.invite.branch_name}</span> : null}
                  {activation.user?.external_user_id ? <span className="tag">ID {activation.user.external_user_id}</span> : null}
                </div>
                <p className="muted">Активировано {formatAgo(activation.activated_at)}</p>
                <div className="action-row">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void moderateInviteMutation.mutateAsync({ activationId: activation.id, action: "approve" })}
                  >
                    Одобрить
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void moderateInviteMutation.mutateAsync({ activationId: activation.id, action: "reject" })}
                  >
                    Отклонить
                  </button>
                </div>
              </article>
            ))}
          </div>
          {moderateInviteMutation.error ? (
            <p className="inline-error">{errorText(moderateInviteMutation.error, "Не удалось обработать активацию")}</p>
          ) : null}
        </section>
      ) : null}

      {(bootstrap.capabilities.can_initiate_staffing || bootstrap.capabilities.can_approve_staffing) ? (
        <section className="section-card">
          <header className="section-head">
            <div>
              <h3>Кадровые действия</h3>
              <p>Очередь operational-решений по команде и веткам.</p>
            </div>
            <span className="pill tone-neutral">{bootstrap.staffing.meta.count}</span>
          </header>
          <div className="card-list">
            {bootstrap.staffing.items.map((item: ControlStaffingAction) => (
              <article key={item.id} className="glass-card">
                <div className="card-topline">
                  <strong>
                    {item.target?.name ?? "Неизвестный человек"} · {item.action_type}
                  </strong>
                  <span className={`pill ${toneForStaffing(item)}`}>{item.status_label}</span>
                </div>
                <p>{item.reason}</p>
                <div className="tag-row">
                  {item.initiator?.name ? <span className="tag">Инициатор: {item.initiator.name}</span> : null}
                  {item.target?.external_user_id ? <span className="tag">ID {item.target.external_user_id}</span> : null}
                </div>
                <p className="muted">Создано {formatAgo(item.created_at)}</p>
                {item.status === "pending" && bootstrap.capabilities.can_approve_staffing ? (
                  <div className="action-row">
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void moderateStaffingMutation.mutateAsync({ actionId: item.id, action: "approve" })}
                    >
                      Подтвердить
                    </button>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => void moderateStaffingMutation.mutateAsync({ actionId: item.id, action: "reject" })}
                    >
                      Отклонить
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
          {moderateStaffingMutation.error ? (
            <p className="inline-error">{errorText(moderateStaffingMutation.error, "Не удалось обработать кадровое действие")}</p>
          ) : null}
        </section>
      ) : null}
    </div>
  );

  const flagsSection = (
    <section className="section-card">
      <header className="section-head">
        <div>
          <h3>Фича-флаги</h3>
          <p>Тонкая операционная настройка без погружения в сырой backend.</p>
        </div>
      </header>
      <div className="card-list">
        {bootstrap.flags.map((flag) => (
          <label key={flag.code} className="glass-card flag-item">
            <div>
              <div className="card-topline">
                <strong>{flag.name}</strong>
                <span className={`pill ${toneForFlag(flag)}`}>{flag.enabled ? "Включено" : "Выключено"}</span>
              </div>
              <div className="tag-row">
                {flag.module ? <span className="tag">{flag.module}</span> : null}
                <span className="tag mono-code">{flag.code}</span>
              </div>
              {flag.description ? <p className="muted">{flag.description}</p> : null}
            </div>
            <input
              type="checkbox"
              checked={flag.enabled}
              onChange={(event) =>
                void toggleFlagMutation.mutateAsync({
                  code: flag.code,
                  enabled: event.target.checked,
                })
              }
            />
          </label>
        ))}
      </div>
      {toggleFlagMutation.error ? (
        <p className="inline-error">{errorText(toggleFlagMutation.error, "Не удалось переключить флаг")}</p>
      ) : null}
    </section>
  );

  return (
    <div className="panel-stack">
      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Control Center</h3>
            <p>Один тихий operational-слой вместо тяжёлой россыпи служебных экранов.</p>
          </div>
        </header>
        <div className="metric-grid dense">
          <article className="metric-card">
            <span>Ветки</span>
            <strong>{bootstrap.branches.length}</strong>
          </article>
          <article className="metric-card">
            <span>Люди</span>
            <strong>{bootstrap.users.meta.count}</strong>
          </article>
          <article className="metric-card">
            <span>Инвайты</span>
            <strong>{bootstrap.invites.meta.count}</strong>
          </article>
          <article className="metric-card">
            <span>Модерация</span>
            <strong>{bootstrap.invite_activations.meta.count + bootstrap.staffing.meta.count}</strong>
          </article>
        </div>
        <div className="segmented control-tabs">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`segment ${item.id === tab ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      {tab === "team" ? userSection : null}
      {tab === "invites" ? invitesSection : null}
      {tab === "moderation" ? moderationSection : null}
      {tab === "flags" ? flagsSection : null}
    </div>
  );
}
