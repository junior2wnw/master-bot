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

type ControlTab = "team" | "branches" | "invites" | "moderation" | "insights" | "flags";

const ROLE_LABELS = new Map<string, string>([
  ["client", "Клиент"],
  ["master", "Мастер"],
  ["senior_master", "Старший мастер"],
  ["admin", "Администратор"],
  ["product_owner", "Product Owner"],
]);
const BRANCH_ASSIGNABLE_ROLE_CODES = new Set(["master", "senior_master"]);

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

function money(value?: number | null): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(value ?? 0);
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

function roleLabel(roleCode: string): string {
  return ROLE_LABELS.get(roleCode) ?? roleCode;
}

function canBelongToBranch(user: ControlUser | null): boolean {
  if (!user) {
    return false;
  }
  return user.roles.some((roleCode) => BRANCH_ASSIGNABLE_ROLE_CODES.has(roleCode));
}

function controlTabs(bootstrap: ControlBootstrapResponse): Array<{ id: ControlTab; label: string }> {
  const tabs: Array<{ id: ControlTab; label: string }> = [];
  if (bootstrap.capabilities.can_view_team) {
    tabs.push({ id: "team", label: "Команда" });
  }
  if (bootstrap.branch_overview.items.length) {
    tabs.push({ id: "branches", label: "Ветки" });
  }
  if (bootstrap.capabilities.can_create_invites || bootstrap.capabilities.can_moderate_invites) {
    tabs.push({ id: "invites", label: "Инвайты" });
  }
  if (
    bootstrap.capabilities.can_moderate_invites ||
    bootstrap.capabilities.can_initiate_staffing ||
    bootstrap.capabilities.can_approve_staffing
  ) {
    tabs.push({ id: "moderation", label: "Модерация" });
  }
  if (bootstrap.insights) {
    tabs.push({ id: "insights", label: "Инсайты" });
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
  const [selectedBranchId, setSelectedBranchId] = useState<number | null>(null);
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
  const [selectedUserBranchId, setSelectedUserBranchId] = useState("");
  const [newBranchName, setNewBranchName] = useState("");

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

  const updateUserRoleMutation = useMutation({
    mutationFn: async (payload: { targetExternalUserId: number; roleCode: string; enabled: boolean }) =>
      api.updateControlUserRole(externalUserId, payload.targetExternalUserId, {
        role_code: payload.roleCode,
        enabled: payload.enabled,
      }),
    onSuccess: async (updatedUser) => {
      setSelectedUserId(updatedUser.external_user_id);
      setSelectedUserBranchId(updatedUser.branches[0]?.id ? String(updatedUser.branches[0].id) : "");
      await refreshControl();
    },
  });

  const assignUserBranchMutation = useMutation({
    mutationFn: async (payload: { targetExternalUserId: number; branchId: number | null }) =>
      api.assignControlUserBranch(externalUserId, payload.targetExternalUserId, {
        branch_id: payload.branchId,
      }),
    onSuccess: async (updatedUser) => {
      setSelectedUserId(updatedUser.external_user_id);
      setSelectedUserBranchId(updatedUser.branches[0]?.id ? String(updatedUser.branches[0].id) : "");
      await refreshControl();
    },
  });

  const createBranchMutation = useMutation({
    mutationFn: async () =>
      api.createControlBranch(externalUserId, {
        name: newBranchName,
      }),
    onSuccess: async (branch) => {
      setNewBranchName("");
      setSelectedBranchId(branch.id);
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
  const selectedBranch =
    bootstrap?.branch_overview.items.find((item) => item.id === selectedBranchId) ??
    bootstrap?.branch_overview.items[0] ??
    null;
  const canManageSelectedUser = Boolean(
    selectedUser &&
      selectedUser.can_manage &&
      (bootstrap?.capabilities.can_manage_users || bootstrap?.capabilities.can_manage_branches),
  );
  const selectedUserCanBelongToBranch = canBelongToBranch(selectedUser);

  useEffect(() => {
    if (!selectedUserId && users[0]) {
      setSelectedUserId(users[0].external_user_id);
    }
  }, [selectedUserId, users]);

  useEffect(() => {
    if (!selectedBranchId && bootstrap?.branch_overview.items[0]) {
      setSelectedBranchId(bootstrap.branch_overview.items[0].id);
    }
  }, [bootstrap, selectedBranchId]);

  useEffect(() => {
    if (!selectedUser) {
      setSelectedUserBranchId("");
      return;
    }
    const activeBranch = selectedUser.branches.find((branch) => branch.is_active) ?? selectedUser.branches[0] ?? null;
    setSelectedUserBranchId(activeBranch ? String(activeBranch.id) : "");
  }, [selectedUser]);

  if (bootstrapQuery.isPending) {
    return (
      <div className="empty-state">
        <strong>Собираем контур управления…</strong>
        <p>Подтягиваем команду, ветки и operational-сигналы.</p>
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

  const teamSection = (
    <div className="panel-stack">
      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Команда</h3>
            <p>Люди, роли и состояние сети без лишнего операционного шума.</p>
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
        {bootstrap.capabilities.can_manage_branches ? (
          <div className="stack-form">
            <div className="row-grid">
              <label>
                <span className="muted">Новая ветка</span>
                <input
                  className="input"
                  value={newBranchName}
                  onChange={(event) => setNewBranchName(event.target.value)}
                  placeholder="Например: Север, Центр, Экспресс"
                />
              </label>
              <div className="action-row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={createBranchMutation.isPending || newBranchName.trim().length < 2}
                  onClick={() => void createBranchMutation.mutateAsync()}
                >
                  {createBranchMutation.isPending ? "Создаём…" : "Создать ветку"}
                </button>
              </div>
            </div>
            {createBranchMutation.error ? (
              <p className="inline-error">{errorText(createBranchMutation.error, "Не удалось создать ветку")}</p>
            ) : null}
          </div>
        ) : null}
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
              <p>Один точный composer по выбранному человеку без прыжков между старыми callback-экранами.</p>
            </div>
            {selectedUser ? <span className="pill tone-neutral">{selectedUser.name}</span> : null}
          </header>
          {!selectedUser ? (
            <p className="muted">Выберите человека выше, чтобы открыть action composer.</p>
          ) : !selectedUser.can_manage ? (
            <p className="muted">Для выбранного человека у текущей роли нет прав на кадровые действия.</p>
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
                  placeholder="Коротко и по делу: зачем это действие нужно сейчас."
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

      {canManageSelectedUser ? (
        <section className="section-card">
          <header className="section-head">
            <div>
              <h3>Роли и ветка</h3>
              <p>Тихое управление доступом и принадлежностью без старых callback-экранов.</p>
            </div>
            {selectedUser ? <span className="pill tone-neutral">{selectedUser.name}</span> : null}
          </header>
          {!selectedUser ? (
            <p className="muted">Выберите человека из списка выше.</p>
          ) : (
            <div className="stack-form">
              {bootstrap.capabilities.can_manage_users && bootstrap.ui.role_management_options.length ? (
                <div className="stack-form">
                  <div>
                    <span className="muted">Прямые роли</span>
                    <div className="tag-row">
                      {selectedUser.roles.map((roleCode) => (
                        <span key={roleCode} className="tag">
                          {roleLabel(roleCode)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="action-row">
                    {bootstrap.ui.role_management_options.map((option) => {
                      const enabled = selectedUser.roles.includes(option.code);
                      return (
                        <button
                          key={option.code}
                          type="button"
                          className={`btn ${enabled ? "btn-primary" : ""}`}
                          disabled={updateUserRoleMutation.isPending}
                          onClick={() =>
                            void updateUserRoleMutation.mutateAsync({
                              targetExternalUserId: selectedUser.external_user_id,
                              roleCode: option.code,
                              enabled: !enabled,
                            })
                          }
                        >
                          {enabled ? `Убрать ${option.label}` : `Выдать ${option.label}`}
                        </button>
                      );
                    })}
                  </div>
                  {updateUserRoleMutation.error ? (
                    <p className="inline-error">
                      {errorText(updateUserRoleMutation.error, "Не удалось обновить роли")}
                    </p>
                  ) : null}
                </div>
              ) : null}

              {bootstrap.capabilities.can_manage_branches ? (
                !selectedUserCanBelongToBranch ? (
                  <div className="glass-card compact-card align-start">
                    <strong>Ветка недоступна</strong>
                    <p className="muted">Сначала у пользователя должна быть прямая роль мастера или старшего мастера.</p>
                  </div>
                ) : (
                  <div className="stack-form">
                    <label>
                      <span className="muted">Активная ветка</span>
                      <select
                        className="input"
                        value={selectedUserBranchId}
                        onChange={(event) => setSelectedUserBranchId(event.target.value)}
                      >
                        <option value="">Без ветки</option>
                        {bootstrap.branches.map((branch) => (
                          <option key={branch.id} value={branch.id}>
                            {branch.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="action-row">
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={assignUserBranchMutation.isPending}
                        onClick={() =>
                          void assignUserBranchMutation.mutateAsync({
                            targetExternalUserId: selectedUser.external_user_id,
                            branchId: selectedUserBranchId ? Number(selectedUserBranchId) : null,
                          })
                        }
                      >
                        {assignUserBranchMutation.isPending ? "Сохраняем…" : "Сохранить ветку"}
                      </button>
                      <button
                        type="button"
                        className="btn"
                        disabled={assignUserBranchMutation.isPending || !selectedUser.branches.length}
                        onClick={() =>
                          void assignUserBranchMutation.mutateAsync({
                            targetExternalUserId: selectedUser.external_user_id,
                            branchId: null,
                          })
                        }
                      >
                        Снять с ветки
                      </button>
                    </div>
                    {assignUserBranchMutation.error ? (
                      <p className="inline-error">
                        {errorText(assignUserBranchMutation.error, "Не удалось обновить ветку")}
                      </p>
                    ) : null}
                  </div>
                )
              ) : null}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );

  const branchesSection = (
    <div className="panel-stack">
      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Ветки</h3>
            <p>Старшие мастера и owner получают один обзор по людям, объёму и выручке.</p>
          </div>
          <span className="pill tone-neutral">{bootstrap.branch_overview.meta.count}</span>
        </header>
        <div className="card-list">
          {bootstrap.branch_overview.items.map((branch) => (
            <button
              key={branch.id}
              type="button"
              className={`metric-card task-card ${selectedBranch?.id === branch.id ? "active-card" : ""}`}
              onClick={() => setSelectedBranchId(branch.id)}
            >
              <div className="card-topline">
                <strong>{branch.name}</strong>
                <span className="pill tone-neutral">{branch.member_count} в сети</span>
              </div>
              <div className="tag-row">
                {branch.senior_name ? <span className="tag">Senior: {branch.senior_name}</span> : null}
                <span className="tag">{branch.active_master_count} мастеров</span>
                <span className="tag">{branch.completed_orders} заказов</span>
              </div>
              <p className="muted">
                {branch.estimate_count} смет · {money(branch.revenue)} ₽ оборот
              </p>
            </button>
          ))}
        </div>
      </section>

      {selectedBranch ? (
        <section className="section-card">
          <header className="section-head">
            <div>
              <h3>{selectedBranch.name}</h3>
              <p>Веточные сценарии собраны в одном месте: люди, метрики и вход в работу.</p>
            </div>
            <div className="tag-row">
              {selectedBranch.senior_name ? <span className="tag">{selectedBranch.senior_name}</span> : null}
              <span className="tag">{selectedBranch.member_count} участников</span>
            </div>
          </header>
          <div className="metric-grid dense">
            <article className="metric-card">
              <span>Мастера</span>
              <strong>{selectedBranch.active_master_count}</strong>
            </article>
            <article className="metric-card">
              <span>Сметы</span>
              <strong>{selectedBranch.estimate_count}</strong>
            </article>
            <article className="metric-card">
              <span>Заказы</span>
              <strong>{selectedBranch.completed_orders}</strong>
            </article>
            <article className="metric-card">
              <span>Оборот</span>
              <strong>{money(selectedBranch.revenue)}</strong>
            </article>
          </div>
          <div className="action-row">
            {bootstrap.capabilities.can_create_invites ? (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  setInviteBranchId(String(selectedBranch.id));
                  setTab("invites");
                }}
              >
                Инвайт в ветку
              </button>
            ) : null}
            {bootstrap.capabilities.can_view_team ? (
              <button
                type="button"
                className="btn"
                onClick={() => {
                  const firstMember = selectedBranch.members.find((member) => !member.is_senior) ?? selectedBranch.members[0];
                  if (firstMember?.external_user_id) {
                    setSelectedUserId(firstMember.external_user_id);
                  }
                  setTab("team");
                }}
              >
                Открыть команду
              </button>
            ) : null}
          </div>
          <div className="card-list">
            {selectedBranch.members.length ? (
              selectedBranch.members.map((member) => (
                <button
                  key={`${selectedBranch.id}-${member.user_id}`}
                  type="button"
                  className="glass-card compact-card align-start"
                  onClick={() => {
                    if (member.external_user_id) {
                      setSelectedUserId(member.external_user_id);
                    }
                    if (bootstrap.capabilities.can_view_team) {
                      setTab("team");
                    }
                  }}
                >
                  <div className="card-topline">
                    <strong>{member.name}</strong>
                    <span className={`pill ${member.is_active ? "tone-success" : "tone-muted"}`}>
                      {member.is_active ? "Активен" : "Неактивен"}
                    </span>
                  </div>
                  <div className="tag-row">
                    <span className="tag">{member.is_senior ? "Старший мастер" : "Мастер"}</span>
                    {member.external_user_id ? <span className="tag">ID {member.external_user_id}</span> : null}
                  </div>
                  <p className="muted">{member.completed_orders} завершённых заказов</p>
                </button>
              ))
            ) : (
              <div className="empty-state">
                <strong>Ветка пока пустая</strong>
                <p>Добавьте мастеров через инвайт или кадровое действие.</p>
              </div>
            )}
          </div>
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
              <p>Один компактный composer вместо длинной админской ветки в боте.</p>
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
                  {invite.is_expired
                    ? "Просрочен"
                    : invite.is_exhausted
                      ? "Использован"
                      : invite.requires_approval
                        ? "Через модерацию"
                        : "Активен"}
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

  const insightsSection = bootstrap.insights ? (
    <div className="panel-stack">
      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Обзор платформы</h3>
            <p>Ключевая картина по росту, экономике и состоянию сервиса без перегруженных дашбордов.</p>
          </div>
        </header>
        <div className="metric-grid dense">
          <article className="metric-card"><span>Пользователи</span><strong>{bootstrap.insights.overview.users}</strong></article>
          <article className="metric-card"><span>Мастера</span><strong>{bootstrap.insights.overview.masters}</strong></article>
          <article className="metric-card"><span>Сметы</span><strong>{bootstrap.insights.overview.estimates}</strong></article>
          <article className="metric-card"><span>Заказы</span><strong>{bootstrap.insights.overview.orders}</strong></article>
          <article className="metric-card"><span>Оборот</span><strong>{money(bootstrap.insights.overview.gross)}</strong></article>
          <article className="metric-card"><span>Net платформы</span><strong>{money(bootstrap.insights.overview.platform_net)}</strong></article>
        </div>
      </section>

      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Финансы</h3>
            <p>Вместо отдельных owner finance и commissions экранов.</p>
          </div>
        </header>
        <div className="metric-grid dense">
          <article className="metric-card"><span>Platform fee</span><strong>{money(bootstrap.insights.finance.platform_fee)}</strong></article>
          <article className="metric-card"><span>Senior share</span><strong>{money(bootstrap.insights.finance.senior_share)}</strong></article>
          <article className="metric-card"><span>Admin share</span><strong>{money(bootstrap.insights.finance.admin_share)}</strong></article>
          <article className="metric-card"><span>Master net</span><strong>{money(bootstrap.insights.finance.master_net)}</strong></article>
          <article className="metric-card"><span>Скидки</span><strong>{money(bootstrap.insights.finance.discounts_total)}</strong></article>
          <article className="metric-card"><span>Net платформы</span><strong>{money(bootstrap.insights.finance.platform_net)}</strong></article>
        </div>
        <div className="card-list">
          {bootstrap.insights.finance.recent_commissions.map((record) => (
            <article key={record.id} className="glass-card compact-card align-start">
              <div className="card-topline">
                <strong>Заказ #{record.order_id ?? "?"}</strong>
                <span className="muted">{formatAgo(record.calculated_at)}</span>
              </div>
              <div className="tag-row">
                <span className="tag">Gross {money(record.gross_total)}</span>
                <span className="tag">Fee {money(record.platform_fee)}</span>
                <span className="tag">Master {money(record.master_net)}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Воронка</h3>
            <p>Живое состояние заказов без отдельного owner funnel экрана.</p>
          </div>
        </header>
        <div className="metric-grid dense">
          {Object.entries(bootstrap.insights.funnel).map(([status, count]) => (
            <article key={status} className="metric-card">
              <span>{status}</span>
              <strong>{count}</strong>
            </article>
          ))}
        </div>
      </section>

      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Лидеры мастеров</h3>
            <p>Топ мастеров по выручке и объёму завершённых заказов.</p>
          </div>
        </header>
        <div className="card-list">
          {bootstrap.insights.masters.length ? (
            bootstrap.insights.masters.map((master, index) => (
              <article key={master.user_id} className="glass-card compact-card align-start">
                <div className="card-topline">
                  <strong>
                    {index + 1}. {master.name}
                  </strong>
                  {master.external_user_id ? <span className="tag">ID {master.external_user_id}</span> : null}
                </div>
                <p className="muted">
                  {master.order_count} заказов · {money(master.revenue)} ₽
                </p>
              </article>
            ))
          ) : (
            <div className="empty-state">
              <strong>Пока без рейтинга</strong>
              <p>Когда появятся подтверждённые выплаты, лидеры покажутся здесь.</p>
            </div>
          )}
        </div>
      </section>

      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Скидки</h3>
            <p>Сводка по discount flow без отдельного owner discounts экрана.</p>
          </div>
        </header>
        <div className="metric-grid dense">
          <article className="metric-card"><span>Всего запросов</span><strong>{bootstrap.insights.discounts.total_requests}</strong></article>
          <article className="metric-card"><span>Одобрено</span><strong>{bootstrap.insights.discounts.approved}</strong></article>
          <article className="metric-card"><span>Отклонено</span><strong>{bootstrap.insights.discounts.rejected}</strong></article>
          <article className="metric-card"><span>Ожидают</span><strong>{bootstrap.insights.discounts.pending}</strong></article>
          <article className="metric-card"><span>Сумма скидок</span><strong>{money(bootstrap.insights.discounts.total_amount)}</strong></article>
          <article className="metric-card"><span>Approval rate</span><strong>{bootstrap.insights.discounts.approval_rate}%</strong></article>
        </div>
      </section>

      <section className="section-card">
        <header className="section-head">
          <div>
            <h3>Настройки среды</h3>
            <p>Короткий owner snapshot вместо отдельного settings callback-экрана.</p>
          </div>
        </header>
        <div className="tag-row">
          <span className="tag">{bootstrap.insights.settings.platform_operator_name}</span>
          <span className="tag">{bootstrap.insights.settings.platform_name}</span>
          <span className="tag">Fee {bootstrap.insights.settings.platform_fee_pct}%</span>
          <span className="tag">Senior {bootstrap.insights.settings.senior_master_share_pct}%</span>
          <span className="tag">Admin {bootstrap.insights.settings.admin_share_pct}%</span>
          <span className="tag">{bootstrap.insights.settings.default_city}</span>
          <span className="tag">{bootstrap.insights.settings.default_region}</span>
          <span className="tag">AI: {bootstrap.insights.settings.ai_provider}</span>
          <span className="tag">Env: {bootstrap.insights.settings.app_env}</span>
        </div>
        {bootstrap.insights.settings.webapp_url ? (
          <p className="muted">Mini App URL: {bootstrap.insights.settings.webapp_url}</p>
        ) : null}
      </section>
    </div>
  ) : <div />;

  const flagsSection = (
    <section className="section-card">
      <header className="section-head">
        <div>
          <h3>Фича-флаги</h3>
          <p>Тонкая operational-настройка без погружения в сырой backend.</p>
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
            <p>Один тихий operational-слой вместо россыпи служебных бот-сценариев.</p>
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

      {tab === "team" ? teamSection : null}
      {tab === "branches" ? branchesSection : null}
      {tab === "invites" ? invitesSection : null}
      {tab === "moderation" ? moderationSection : null}
      {tab === "insights" ? insightsSection : null}
      {tab === "flags" ? flagsSection : null}
    </div>
  );
}
