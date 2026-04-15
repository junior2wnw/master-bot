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
import { ControlCenterPanel } from "./ControlCenterPanel";
import { EstimateDrawer } from "./estimateDrawer";
import { BoardResponsesDrawer, MasterDrawer, RoleModeDrawer } from "./marketDrawers";
import { BoardPanel, NetworkPanel } from "./marketPanels";
import { OrderDrawer } from "./orderDrawer";
import { ProfilePanel } from "./profilePanel";
import { useWorkspaceStore } from "./store";
import type { BootstrapResponse, LayoutPayload, PaneId, PanelMeta, RoleModeResponse } from "./types";
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
  const [selectedMasterId, setSelectedMasterId] = useState<number | null>(null);
  const [selectedEstimateId, setSelectedEstimateId] = useState<number | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [selectedBoardPostId, setSelectedBoardPostId] = useState<number | null>(null);
  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
  const [paletteMode, setPaletteMode] = useState<PaletteMode>("open");
  const [activeCompactWindowId, setActiveCompactWindowId] = useState<string>("");
  const layoutSaveRef = useRef<string | null>(null);

  useEffect(() => {
    hydrateFromBootstrap(bootstrap);
    layoutSaveRef.current = JSON.stringify(ensureComposerLayout(bootstrap.layout, bootstrap.panels));
  }, [bootstrap, hydrateFromBootstrap]);

  const presetMutation = useMutation({
    mutationFn: async (presetId: string) => api.getLayout(externalUserId, presetId),
    onSuccess: (nextLayout) => {
      const normalized = ensureComposerLayout(nextLayout, panels.length ? panels : bootstrap.panels);
      layoutSaveRef.current = JSON.stringify(normalized);
      replaceLayout(normalized);
    },
  });

  const saveLayoutMutation = useMutation({
    mutationFn: async (nextLayout: LayoutPayload) => api.saveLayout(externalUserId, nextLayout.preset, nextLayout),
    onSuccess: (savedLayout) => {
      const normalized = ensureComposerLayout(savedLayout, panels.length ? panels : bootstrap.panels);
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

  if (!layout || !bootState) {
    return null;
  }

  const currentLayout = ensureComposerLayout(layout, panels);
  const composer = currentLayout.composer!;
  const activeRoleLabel = roleModeQuery.data?.active_role_label || bootState.workspace.active_role_label;
  const maxRoleLabel = roleModeQuery.data?.max_role_label || bootState.workspace.max_role_label;
  const canSwitchRole = roleModeQuery.data?.can_switch_role || bootState.workspace.can_switch_role;

  const commitLayout = (nextLayout: LayoutPayload) => {
    replaceLayout(nextLayout);
    if (nextLayout.composer?.focus_window_id) {
      setActiveCompactWindowId(nextLayout.composer.focus_window_id);
    }
  };

  const openPanel = (panelId: string, mode: "focus-or-add" | "replace" = "focus-or-add") => {
    commitLayout(
      openPanelInComposer(currentLayout, panels, {
        panelId,
        targetWindowId: composer.focus_window_id,
        axis: compactLayout ? "vertical" : splitDirection,
        mode,
      }),
    );
  };

  const focusWindow = (windowId: string) => {
    commitLayout(focusComposerWindow(currentLayout, panels, windowId));
  };

  const changeWindowPanel = (windowId: string, panelId: string) => {
    commitLayout(replaceWindowPanel(currentLayout, panels, windowId, panelId));
  };

  const closeWindow = (windowId: string) => {
    commitLayout(closeComposerWindow(currentLayout, panels, windowId));
  };

  const toggleSpotlight = (windowId: string) => {
    commitLayout(toggleSpotlightWindow(currentLayout, panels, windowId));
  };

  const resizeSplit = (splitId: string, sizes: number[]) => {
    replaceLayout(resizeComposerSplit(currentLayout, panels, splitId, sizes));
  };

  const focusPanel = (_pane: PaneId, panelId: string) => {
    openPanel(panelId);
  };

  const openEstimate = (estimateId: number) => {
    openPanel("estimates-list");
    setSelectedEstimateId(estimateId);
    setSelectedOrderId(null);
  };

  const openOrder = (orderId: number) => {
    openPanel("orders-list");
    setSelectedEstimateId(null);
    setSelectedOrderId(orderId);
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
        if (parsed.id !== null) {
          openEstimate(parsed.id);
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
          openOrder(parsed.id);
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
        openPanel("profile-card");
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
        return <BoardPanel externalUserId={externalUserId} bootstrap={bootState} onOpenResponses={setSelectedBoardPostId} />;
      case "network-directory":
        return (
          <NetworkPanel
            externalUserId={externalUserId}
            bootstrap={bootState}
            onOpenMaster={setSelectedMasterId}
            onOpenProfile={() => openPanel("profile-card")}
          />
        );
      case "workspace-overview":
        return <WorkspacePanel bootstrap={bootState} onFocusPanel={focusPanel} onOpenWorkflow={handleWorkflowTarget} />;
      case "catalog-browser":
        return <CatalogPanel externalUserId={externalUserId} canCreateEstimate={bootState.capabilities.can_create_estimate} onOpenEstimate={openEstimate} />;
      case "estimates-list":
        return <EstimatesPanel externalUserId={externalUserId} canCreateEstimate={bootState.capabilities.can_create_estimate} onOpenEstimate={openEstimate} />;
      case "orders-list":
        return <OrdersPanel externalUserId={externalUserId} onOpenOrder={openOrder} />;
      case "notifications-list":
        return <NotificationsPanel externalUserId={externalUserId} onOpenTarget={handleWorkflowTarget} />;
      case "profile-card":
        return <ProfilePanel externalUserId={externalUserId} canPublishMasterProfile={bootState.capabilities.can_publish_master_profile} />;
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
    void presetMutation.mutateAsync(presetId);
  };

  const openPalette = (mode: PaletteMode) => {
    setPaletteMode(mode);
    setCommandOpen(true);
  };

  const handleOpenProfile = () => {
    openPanel("profile-card");
  };

  return (
    <div className="app-shell" data-testid="superapp-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <SpotlightHero
        auth={auth}
        bootstrap={bootState}
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
          <div>
            <strong>Живой composer</strong>
            <p>Обычный тап переключает режим, удержание добавляет новое окно рядом, двойной тап по заголовку окна включает фокус.</p>
          </div>
          <button className="btn" type="button" onClick={() => openPalette("open")}>
            Добавить модуль
          </button>
        </section>

        <WindowComposer
          layout={currentLayout}
          panels={panels}
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
        panels={panels}
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
        onClose={() => setSelectedEstimateId(null)}
        onFocusPanel={focusPanel}
        onOpenOrder={openOrder}
      />
      <OrderDrawer externalUserId={externalUserId} orderId={selectedOrderId} onClose={() => setSelectedOrderId(null)} />
    </div>
  );
}
