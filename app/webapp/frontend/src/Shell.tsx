import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import {
  EmptyState,
  SpotlightHero,
  errorMessage,
  parseWorkflowCallback,
  useCompactLayout,
  useSplitDirection,
} from "./appHelpers";
import {
  buildEstimateIntent,
  buildGeneralIntent,
  buildNotificationIntent,
  buildOrderIntent,
  buildProfileIntent,
  type ComposerRecommendation,
  type ComposerIntentSurface,
} from "./composerIntents";
import { ControlCenterPanel } from "./ControlCenterPanel";
import { EstimateDrawer } from "./estimateDrawer";
import { BoardResponsesDrawer, MasterDrawer, RoleModeDrawer } from "./marketDrawers";
import { BoardPanel, NetworkPanel } from "./marketPanels";
import { OrderDrawer } from "./orderDrawer";
import { ProfilePanel } from "./profilePanel";
import { useWorkspaceStore } from "./store";
import type {
  BootstrapResponse,
  EstimateDetail,
  LayoutPayload,
  NotificationItem,
  OrderDetail,
  PaneId,
  PanelMeta,
  ProfileResponse,
  RoleModeResponse,
} from "./types";
import { WindowComposer } from "./windowComposer";
import {
  closeComposerWindow,
  ensureComposerLayout,
  focusComposerWindow,
  listComposerWindows,
  openPanelInComposer,
  replaceWindowPanel,
  resizeComposerSplit,
  toggleSpotlightWindow,
} from "./windowLayout";
import {
  AnalyticsPanel,
  ApprovalsPanel,
  CatalogPanel,
  EstimatesPanel,
  NotificationsPanel,
  OrdersPanel,
  WorkspacePanel,
} from "./workPanels";

type PaletteMode = "open" | "replace";

function CommandPalette({
  open,
  panels,
  compact,
  mode,
  onModeChange,
  onClose,
  onSelect,
}: {
  open: boolean;
  panels: PanelMeta[];
  compact: boolean;
  mode: PaletteMode;
  onModeChange: (mode: PaletteMode) => void;
  onClose: () => void;
  onSelect: (panelId: string, mode: PaletteMode) => void;
}) {
  const grouped = useMemo(
    () =>
      panels.reduce<Record<string, PanelMeta[]>>((acc, panel) => {
        acc[panel.group] = acc[panel.group] || [];
        acc[panel.group].push(panel);
        return acc;
      }, {}),
    [panels],
  );

  if (!open) {
    return null;
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="palette" data-testid="command-palette" onClick={(event) => event.stopPropagation()}>
        <div className="palette-head">
          <div>
            <h3>Сборка пространства</h3>
            <p>
              {compact
                ? "Откройте модуль в текущем фокусе или замените активный экран без лишнего меню."
                : "Откройте модуль как новое окно в composer или замените активное окно, если нужен быстрый поворот контекста."}
            </p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <div className="segmented">
          <button className={`segment ${mode === "open" ? "active" : ""}`} onClick={() => onModeChange("open")}>
            {compact ? "Открыть" : "Открыть окном"}
          </button>
          <button className={`segment ${mode === "replace" ? "active" : ""}`} onClick={() => onModeChange("replace")}>
            Заменить фокус
          </button>
        </div>
        <div className="palette-groups">
          {Object.entries(grouped).map(([group, items]) => (
            <section key={group} className="palette-group">
              <div className="section-head">
                <div>
                  <h3>{group}</h3>
                  <p>Модули группы {group}</p>
                </div>
              </div>
              <div className="card-list">
                {items.map((item) => (
                  <button
                    key={item.id}
                    className="glass-card compact-card card-button align-start"
                    onClick={() => {
                      onSelect(item.id, mode);
                      onClose();
                    }}
                  >
                    <div>
                      <div className="card-topline">
                        <span className="pill tone-neutral">{item.group}</span>
                      </div>
                      <h4>{item.title}</h4>
                      <p>{item.subtitle}</p>
                    </div>
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

function DockActionButton({
  testId,
  label,
  strong,
  onTap,
  onHold,
}: {
  testId: string;
  label: string;
  strong?: boolean;
  onTap: () => void;
  onHold?: () => void;
}) {
  const timerRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const handlePointerDown = () => {
    holdTriggeredRef.current = false;
    if (!onHold) {
      return;
    }
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      holdTriggeredRef.current = true;
      onHold();
    }, 380);
  };

  const handlePointerUp = () => {
    clearTimer();
    if (holdTriggeredRef.current) {
      holdTriggeredRef.current = false;
      return;
    }
    onTap();
  };

  return (
    <button
      type="button"
      data-testid={testId}
      className={`dock-btn ${strong ? "strong" : ""}`}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerLeave={clearTimer}
      onPointerCancel={clearTimer}
      onContextMenu={(event) => event.preventDefault()}
    >
      {label}
    </button>
  );
}

export function Shell({
  auth,
  bootstrap,
}: {
  auth: { telegram_id: number; name: string };
  bootstrap: BootstrapResponse;
}) {
  const externalUserId = auth.telegram_id;
  const queryClient = useQueryClient();
  const splitDirection = useSplitDirection();
  const compactLayout = useCompactLayout();
  const { layout, panels, presets, bootstrap: bootState, commandOpen, hydrateFromBootstrap, replaceLayout, setCommandOpen } = useWorkspaceStore();
  const panelRegistry = panels.length ? panels : bootstrap.panels;
  const shellBootstrap = bootState ?? bootstrap;
  const [selectedMasterId, setSelectedMasterId] = useState<number | null>(null);
  const [selectedEstimateId, setSelectedEstimateId] = useState<number | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [selectedBoardPostId, setSelectedBoardPostId] = useState<number | null>(null);
  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
  const [paletteMode, setPaletteMode] = useState<PaletteMode>("open");
  const [activeCompactWindowId, setActiveCompactWindowId] = useState<string>("");
  const [intentContext, setIntentContext] = useState<
    | { kind: "estimate"; detail: EstimateDetail }
    | { kind: "order"; detail: OrderDetail }
    | { kind: "profile"; detail: Pick<ProfileResponse, "phone" | "specialization"> | null }
    | { kind: "notification"; detail: NotificationItem }
    | null
  >(null);
  const layoutSaveRef = useRef<string | null>(null);

  useEffect(() => {
    hydrateFromBootstrap(bootstrap);
    layoutSaveRef.current = JSON.stringify(ensureComposerLayout(bootstrap.layout, bootstrap.panels));
  }, [bootstrap, hydrateFromBootstrap]);

  const presetMutation = useMutation({
    mutationFn: async (presetId: string) => api.getLayout(externalUserId, presetId),
    onSuccess: (nextLayout) => {
      const normalized = ensureComposerLayout(nextLayout, panelRegistry);
      layoutSaveRef.current = JSON.stringify(normalized);
      replaceLayout(normalized);
    },
  });

  const saveLayoutMutation = useMutation({
    mutationFn: async (nextLayout: LayoutPayload) => api.saveLayout(externalUserId, nextLayout.preset, nextLayout),
    onSuccess: (savedLayout) => {
      const normalized = ensureComposerLayout(savedLayout, panelRegistry);
      layoutSaveRef.current = JSON.stringify(normalized);
      replaceLayout(normalized);
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
      setSelectedBoardPostId(null);
      setIntentContext(null);
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

  useEffect(() => {
    if (!layout?.composer) {
      return;
    }
    const currentWindows = listComposerWindows(layout.composer.root);
    if (!currentWindows.some((window) => window.id === activeCompactWindowId)) {
      setActiveCompactWindowId(layout.composer.focus_window_id);
    }
  }, [activeCompactWindowId, layout]);

  const currentLayout = useMemo(() => {
    if (!layout) {
      return null;
    }
    return ensureComposerLayout(layout, panelRegistry);
  }, [layout, panelRegistry]);

  const intentSurface = useMemo<ComposerIntentSurface | null>(() => {
    if (!currentLayout) {
      return null;
    }
    const intentCtx = {
      layout: currentLayout,
      panels: panelRegistry,
      bootstrap: shellBootstrap,
      splitAxis: compactLayout ? "vertical" : splitDirection,
    } as const;
    if (!intentContext) {
      return buildGeneralIntent(intentCtx);
    }
    switch (intentContext.kind) {
      case "estimate":
        return buildEstimateIntent(intentCtx, intentContext.detail);
      case "order":
        return buildOrderIntent(intentCtx, intentContext.detail);
      case "profile":
        return buildProfileIntent(intentCtx, intentContext.detail);
      case "notification":
        return buildNotificationIntent(intentCtx, intentContext.detail);
      default:
        return buildGeneralIntent(intentCtx);
    }
  }, [compactLayout, currentLayout, intentContext, panelRegistry, shellBootstrap, splitDirection]);

  if (!currentLayout || !intentSurface) {
    return null;
  }

  const composer = currentLayout.composer!;
  const activeRoleLabel = roleModeQuery.data?.active_role_label ?? shellBootstrap.workspace.active_role_label;
  const maxRoleLabel = roleModeQuery.data?.max_role_label ?? shellBootstrap.workspace.max_role_label;
  const canSwitchRole = roleModeQuery.data?.can_switch_role ?? shellBootstrap.workspace.can_switch_role;

  const commitLayout = (nextLayout: LayoutPayload) => {
    replaceLayout(nextLayout);
    if (nextLayout.composer?.focus_window_id) {
      setActiveCompactWindowId(nextLayout.composer.focus_window_id);
    }
  };

  const openPanel = (panelId: string, mode: "focus-or-add" | "replace" = "focus-or-add") => {
    commitLayout(
      openPanelInComposer(currentLayout, panelRegistry, {
        panelId,
        targetWindowId: composer.focus_window_id,
        axis: compactLayout ? "vertical" : splitDirection,
        mode,
      }),
    );
  };

  const focusWindow = (windowId: string) => {
    commitLayout(focusComposerWindow(currentLayout, panelRegistry, windowId));
  };

  const changeWindowPanel = (windowId: string, panelId: string) => {
    commitLayout(replaceWindowPanel(currentLayout, panelRegistry, windowId, panelId));
  };

  const closeWindow = (windowId: string) => {
    commitLayout(closeComposerWindow(currentLayout, panelRegistry, windowId));
  };

  const toggleSpotlight = (windowId: string) => {
    commitLayout(toggleSpotlightWindow(currentLayout, panelRegistry, windowId));
  };

  const resizeSplit = (splitId: string, sizes: number[]) => {
    replaceLayout(resizeComposerSplit(currentLayout, panelRegistry, splitId, sizes));
  };

  const focusPanel = (_pane: PaneId, panelId: string) => {
    openPanel(panelId);
  };

  const openEstimate = async (estimateId: number, baseLayout?: LayoutPayload) => {
    let nextLayout = baseLayout ?? currentLayout;
    nextLayout = openPanelInComposer(nextLayout, panelRegistry, {
      panelId: "estimates-list",
      targetWindowId: nextLayout.composer?.focus_window_id,
      axis: compactLayout ? "vertical" : splitDirection,
    });
    commitLayout(nextLayout);
    setSelectedEstimateId(estimateId);
    setSelectedOrderId(null);
    setSelectedMasterId(null);
    setSelectedBoardPostId(null);
    try {
      const detail = await queryClient.fetchQuery({
        queryKey: ["estimate-detail", externalUserId, estimateId],
        queryFn: () => api.getEstimate(externalUserId, estimateId),
        staleTime: 15_000,
      });
      let enriched = nextLayout;
      if (detail.status === "draft" && detail.capabilities.can_edit) {
        enriched = openPanelInComposer(enriched, panelRegistry, {
          panelId: "catalog-browser",
          targetWindowId: enriched.composer?.focus_window_id,
          axis: compactLayout ? "vertical" : splitDirection,
        });
      }
      if (detail.status === "approved" && shellBootstrap.capabilities.can_create_order) {
        enriched = openPanelInComposer(enriched, panelRegistry, {
          panelId: "orders-list",
          targetWindowId: enriched.composer?.focus_window_id,
          axis: compactLayout ? "vertical" : splitDirection,
        });
      }
      if (detail.status === "client_review" && shellBootstrap.notifications.unread > 0) {
        enriched = openPanelInComposer(enriched, panelRegistry, {
          panelId: "notifications-list",
          targetWindowId: enriched.composer?.focus_window_id,
          axis: compactLayout ? "vertical" : splitDirection,
        });
      }
      commitLayout(enriched);
      setIntentContext({ kind: "estimate", detail });
    } catch {
      setIntentContext(null);
    }
  };

  const openOrder = async (orderId: number, baseLayout?: LayoutPayload) => {
    let nextLayout = baseLayout ?? currentLayout;
    nextLayout = openPanelInComposer(nextLayout, panelRegistry, {
      panelId: "orders-list",
      targetWindowId: nextLayout.composer?.focus_window_id,
      axis: compactLayout ? "vertical" : splitDirection,
    });
    commitLayout(nextLayout);
    setSelectedEstimateId(null);
    setSelectedOrderId(orderId);
    setSelectedMasterId(null);
    setSelectedBoardPostId(null);
    try {
      const detail = await queryClient.fetchQuery({
        queryKey: ["order-detail", externalUserId, orderId],
        queryFn: () => api.getOrder(externalUserId, orderId),
        staleTime: 15_000,
      });
      let enriched = nextLayout;
      if (detail.estimate?.id) {
        enriched = openPanelInComposer(enriched, panelRegistry, {
          panelId: "estimates-list",
          targetWindowId: enriched.composer?.focus_window_id,
          axis: compactLayout ? "vertical" : splitDirection,
        });
      }
      if (shellBootstrap.notifications.unread > 0) {
        enriched = openPanelInComposer(enriched, panelRegistry, {
          panelId: "notifications-list",
          targetWindowId: enriched.composer?.focus_window_id,
          axis: compactLayout ? "vertical" : splitDirection,
        });
      }
      commitLayout(enriched);
      setIntentContext({ kind: "order", detail });
    } catch {
      setIntentContext(null);
    }
  };

  const openProfileScenario = async () => {
    let nextLayout = currentLayout;
    nextLayout = openPanelInComposer(nextLayout, panelRegistry, {
      panelId: "profile-card",
      targetWindowId: nextLayout.composer?.focus_window_id,
      axis: compactLayout ? "vertical" : splitDirection,
    });
    if (shellBootstrap.capabilities.can_publish_master_profile) {
      nextLayout = openPanelInComposer(nextLayout, panelRegistry, {
        panelId: "network-directory",
        targetWindowId: nextLayout.composer?.focus_window_id,
        axis: compactLayout ? "vertical" : splitDirection,
      });
    }
    commitLayout(nextLayout);
    setSelectedEstimateId(null);
    setSelectedOrderId(null);
    setSelectedMasterId(null);
    setSelectedBoardPostId(null);
    try {
      const profile = await queryClient.fetchQuery({
        queryKey: ["profile", externalUserId],
        queryFn: () => api.getProfile(externalUserId),
        staleTime: 15_000,
      });
      setIntentContext({ kind: "profile", detail: profile });
    } catch {
      setIntentContext({ kind: "profile", detail: null });
    }
  };

  const handleWorkflowTarget = async (callback?: string | null, options?: { fromNotification?: NotificationItem }) => {
    const parsed = parseWorkflowCallback(callback);
    if (!parsed) {
      return;
    }
    let baseLayout = currentLayout;
    if (options?.fromNotification) {
      baseLayout = openPanelInComposer(baseLayout, panelRegistry, {
        panelId: "notifications-list",
        targetWindowId: baseLayout.composer?.focus_window_id,
        axis: compactLayout ? "vertical" : splitDirection,
      });
      commitLayout(baseLayout);
      setIntentContext({ kind: "notification", detail: options.fromNotification });
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
        if (parsed.id !== null) {
          await openEstimate(parsed.id, baseLayout);
        } else {
          openPanel("estimates-list");
        }
        return;
      case "order_view":
      case "order_submit":
      case "order_assign":
      case "order_start":
      case "order_complete":
      case "order_pay":
      case "order_cancel":
        if (parsed.id !== null) {
          await openOrder(parsed.id, baseLayout);
        } else {
          openPanel("orders-list");
        }
        return;
      case "disc_detail":
      case "approvals":
        openPanel("approvals-queue");
        return;
      case "notif_open":
        openPanel("notifications-list");
        return;
      case "profile":
      case "profile_edit":
      case "profile_requisites":
        await openProfileScenario();
        return;
      case "profile_role_mode":
        setRoleDrawerOpen(true);
        return;
      case "catalog":
      case "search":
      case "popular":
        openPanel("catalog-browser");
        return;
      case "my_estimates":
        openPanel("estimates-list");
        return;
      case "my_orders":
        openPanel("orders-list");
        return;
      case "my_branch":
      case "br_view":
      case "br_stats":
      case "br_members":
      case "inv_pending":
      case "adm_staffing":
      case "admin_panel":
      case "owner_panel":
      case "adm_flags":
      case "own_finance":
      case "own_funnel":
      case "own_masters":
      case "own_branches":
      case "own_discounts":
      case "own_settings":
      case "adm_audit":
        openPanel("control-center");
        return;
      default:
        openPanel("workspace-overview");
    }
  };

  const renderPanel = (panelId: string): ReactNode => {
      switch (panelId) {
      case "board-feed":
        return <BoardPanel externalUserId={externalUserId} bootstrap={shellBootstrap} onOpenResponses={setSelectedBoardPostId} />;
      case "network-directory":
        return (
          <NetworkPanel
            externalUserId={externalUserId}
            bootstrap={shellBootstrap}
            onOpenMaster={setSelectedMasterId}
            onOpenProfile={() => void openProfileScenario()}
          />
        );
      case "workspace-overview":
        return <WorkspacePanel bootstrap={shellBootstrap} onFocusPanel={focusPanel} onOpenWorkflow={handleWorkflowTarget} />;
      case "catalog-browser":
        return <CatalogPanel externalUserId={externalUserId} canCreateEstimate={shellBootstrap.capabilities.can_create_estimate} onOpenEstimate={openEstimate} />;
      case "estimates-list":
        return <EstimatesPanel externalUserId={externalUserId} canCreateEstimate={shellBootstrap.capabilities.can_create_estimate} onOpenEstimate={openEstimate} />;
      case "orders-list":
        return <OrdersPanel externalUserId={externalUserId} onOpenOrder={openOrder} />;
      case "notifications-list":
        return <NotificationsPanel externalUserId={externalUserId} onOpenTarget={(notification) => void handleWorkflowTarget(notification.target_callback, { fromNotification: notification })} />;
      case "profile-card":
        return <ProfilePanel externalUserId={externalUserId} canPublishMasterProfile={shellBootstrap.capabilities.can_publish_master_profile} />;
      case "control-center":
        return <ControlCenterPanel externalUserId={externalUserId} />;
      case "approvals-queue":
        return <ApprovalsPanel externalUserId={externalUserId} />;
      case "analytics-overview":
        return <AnalyticsPanel externalUserId={externalUserId} />;
      default:
        return <EmptyState title="Панель ещё не подключена" subtitle="Этот модуль скоро будет доступен в новом shell." />;
    }
  };

  const handlePresetSelect = (presetId: string) => {
    setIntentContext(null);
    setSelectedEstimateId(null);
    setSelectedOrderId(null);
    setSelectedMasterId(null);
    setSelectedBoardPostId(null);
    void presetMutation.mutateAsync(presetId);
  };

  const openPalette = (mode: PaletteMode) => {
    setPaletteMode(mode);
    setCommandOpen(true);
  };

  const handleOpenProfile = () => {
    void openProfileScenario();
  };

  const handleIntentRecommendation = (recommendation: ComposerRecommendation) => {
    if (recommendation.workflowCallback) {
      void handleWorkflowTarget(recommendation.workflowCallback);
      return;
    }
    if (typeof recommendation.orderId === "number") {
      void openOrder(recommendation.orderId);
      return;
    }
    if (typeof recommendation.estimateId === "number") {
      void openEstimate(recommendation.estimateId);
      return;
    }
    if (recommendation.profileScenario) {
      void openProfileScenario();
      return;
    }
    openPanel(recommendation.panelId, recommendation.mode ?? "focus-or-add");
  };

  const handleCloseEstimate = () => {
    setSelectedEstimateId(null);
    setIntentContext((current) => (current?.kind === "estimate" ? null : current));
  };

  const handleCloseOrder = () => {
    setSelectedOrderId(null);
    setIntentContext((current) => (current?.kind === "order" ? null : current));
  };

  return (
    <div className="app-shell" data-testid="superapp-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <SpotlightHero
        auth={auth}
        bootstrap={shellBootstrap}
        activeRoleLabel={activeRoleLabel}
        maxRoleLabel={maxRoleLabel}
        canSwitchRole={canSwitchRole}
        compact={compactLayout}
        onOpenRoleMode={() => setRoleDrawerOpen(true)}
        onSelectPreset={handlePresetSelect}
        onOpenModules={() => openPalette("open")}
        onOpenProfile={handleOpenProfile}
      />

      <main className={`workspace-frame composer-frame ${compactLayout ? "compact-workspace" : ""}`} data-testid="workspace-frame">
        <section className="workspace-intent glass-card">
          <div className="workspace-intent-copy">
            <strong>{intentSurface.title}</strong>
            <p>{intentSurface.body}</p>
          </div>
          <div className="workspace-intent-actions">
            {intentSurface.recommendations.map((recommendation) => (
              <button
                key={recommendation.id}
                className={`btn ${intentSurface.recommendations[0]?.id === recommendation.id ? "btn-primary" : ""}`}
                type="button"
                title={recommendation.title}
                onClick={() => handleIntentRecommendation(recommendation)}
              >
                {recommendation.label}
              </button>
            ))}
            <button className="btn" type="button" onClick={() => openPalette("open")}>
              Добавить модуль
            </button>
          </div>
        </section>

        <WindowComposer
          layout={currentLayout}
          panels={panelRegistry}
          compact={compactLayout}
          activeCompactWindowId={activeCompactWindowId || composer.focus_window_id}
          onSelectCompactWindow={setActiveCompactWindowId}
          onFocusWindow={focusWindow}
          onChangeWindowPanel={changeWindowPanel}
          onCloseWindow={closeWindow}
          onToggleSpotlight={toggleSpotlight}
          onResizeSplit={resizeSplit}
          renderPanel={renderPanel}
        />
      </main>

      <footer className="dock" data-testid="workspace-dock">
        <DockActionButton
          testId="dock-market"
          label="Рынок"
          strong={currentLayout.preset === "market"}
          onTap={() => handlePresetSelect("market")}
          onHold={() => openPanel("board-feed")}
        />
        <DockActionButton
          testId="dock-workbench"
          label="Работа"
          strong={currentLayout.preset === "workbench"}
          onTap={() => handlePresetSelect("workbench")}
          onHold={() => openPanel("workspace-overview")}
        />
        {presets.some((item) => item.id === "control") ? (
          <DockActionButton
            testId="dock-control"
            label="Операции"
            strong={currentLayout.preset === "control"}
            onTap={() => handlePresetSelect("control")}
            onHold={() => openPanel("control-center")}
          />
        ) : null}
        <DockActionButton
          testId="dock-profile"
          label="Профиль"
          onTap={handleOpenProfile}
          onHold={() => setRoleDrawerOpen(true)}
        />
        <DockActionButton
          testId="dock-modules"
          label={compactLayout ? "Ещё" : "Модули"}
          strong
          onTap={() => openPalette("open")}
          onHold={() => openPalette("replace")}
        />
      </footer>

      <CommandPalette
        open={commandOpen}
        panels={panelRegistry}
        compact={compactLayout}
        mode={paletteMode}
        onModeChange={setPaletteMode}
        onClose={() => setCommandOpen(false)}
        onSelect={(panelId, mode) => openPanel(panelId, mode === "replace" ? "replace" : "focus-or-add")}
      />
      <BoardResponsesDrawer externalUserId={externalUserId} postId={selectedBoardPostId} onClose={() => setSelectedBoardPostId(null)} />
      <MasterDrawer externalUserId={externalUserId} selectedMasterId={selectedMasterId} onClose={() => setSelectedMasterId(null)} />
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
        onClose={handleCloseEstimate}
        onFocusPanel={focusPanel}
        onOpenOrder={openOrder}
      />
      <OrderDrawer externalUserId={externalUserId} orderId={selectedOrderId} onClose={handleCloseOrder} />
    </div>
  );
}
