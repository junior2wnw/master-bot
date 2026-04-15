import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Group, Panel, Separator } from "react-resizable-panels";

import { ControlCenterPanel } from "./ControlCenterPanel";
import { useWorkspaceStore } from "./store";
import { BoardPanel, NetworkPanel } from "./marketPanels";
import { WorkspacePanel, CatalogPanel, EstimatesPanel, OrdersPanel, NotificationsPanel, ApprovalsPanel, AnalyticsPanel } from "./workPanels";
import { ProfilePanel } from "./profilePanel";
import { BoardResponsesDrawer, MasterDrawer, RoleModeDrawer } from "./marketDrawers";
import { EstimateDrawer } from "./estimateDrawer";
import { OrderDrawer } from "./orderDrawer";
import {
  EmptyState,
  Glyph,
  PanelPicker,
  SpotlightHero,
  errorMessage,
  paneLabel,
  parseWorkflowCallback,
  useSplitDirection,
} from "./appHelpers";
import { api } from "./api";
import type { BootstrapResponse, PaneId, PanelMeta, RoleModeResponse } from "./types";

function CommandPalette({
  open,
  panels,
  onClose,
  onSelect,
}: {
  open: boolean;
  panels: PanelMeta[];
  onClose: () => void;
  onSelect: (pane: PaneId, panelId: string) => void;
}) {
  const [targetPane, setTargetPane] = useState<PaneId>("top");
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
            <h3>Рабочие модули</h3>
            <p>Подключайте нужные функции в нужную половину экрана, не теряя общий контекст.</p>
          </div>
          <button className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <div className="segmented">
          <button className={`segment ${targetPane === "top" ? "active" : ""}`} onClick={() => setTargetPane("top")}>
            Верхняя половина
          </button>
          <button className={`segment ${targetPane === "bottom" ? "active" : ""}`} onClick={() => setTargetPane("bottom")}>
            Нижняя половина
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
                      onSelect(targetPane, item.id);
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

function PaneSurface({
  paneId,
  panelId,
  title,
  icon,
  direction,
  panels,
  onChange,
  children,
}: {
  paneId: PaneId;
  panelId: string;
  title: string;
  icon: string;
  direction: "horizontal" | "vertical";
  panels: PanelMeta[];
  onChange: (pane: PaneId, panelId: string) => void;
  children: ReactNode;
}) {
  return (
    <section className="pane-surface" data-testid={`pane-surface-${paneId}`} data-panel-id={panelId}>
      <header className="pane-head">
        <div className="pane-title">
          <span className="glyph-shell">
            <Glyph name={icon} />
          </span>
          <div>
            <span className="pane-label">{paneLabel(paneId, direction)}</span>
            <h2>{title}</h2>
          </div>
        </div>
        <PanelPicker value={panelId} options={panels} onChange={(next) => onChange(paneId, next)} />
      </header>
      <div className="pane-content">{children}</div>
    </section>
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
  const {
    layout,
    panels,
    presets,
    bootstrap: bootState,
    commandOpen,
    hydrateFromBootstrap,
    replaceLayout,
    setPanePanel,
    setRatio,
    setCommandOpen,
  } = useWorkspaceStore();
  const [selectedMasterId, setSelectedMasterId] = useState<number | null>(null);
  const [selectedEstimateId, setSelectedEstimateId] = useState<number | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [selectedBoardPostId, setSelectedBoardPostId] = useState<number | null>(null);
  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
  const layoutSaveRef = useRef<string | null>(null);
  const panelLookup = useMemo(() => new Map(panels.map((panel) => [panel.id, panel])), [panels]);

  useEffect(() => {
    hydrateFromBootstrap(bootstrap);
    layoutSaveRef.current = JSON.stringify(bootstrap.layout);
  }, [bootstrap, hydrateFromBootstrap]);

  const presetMutation = useMutation({
    mutationFn: async (presetId: string) => api.getLayout(externalUserId, presetId),
    onSuccess: (nextLayout) => {
      layoutSaveRef.current = JSON.stringify(nextLayout);
      replaceLayout(nextLayout);
    },
  });

  const saveLayoutMutation = useMutation({
    mutationFn: async (nextLayout: NonNullable<typeof layout>) => api.saveLayout(externalUserId, nextLayout.preset, nextLayout),
    onSuccess: (savedLayout) => {
      layoutSaveRef.current = JSON.stringify(savedLayout);
      replaceLayout(savedLayout);
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

  if (!layout || !bootState) {
    return null;
  }

  const openEstimate = (estimateId: number) => {
    setSelectedEstimateId(estimateId);
    setSelectedOrderId(null);
  };

  const openOrder = (orderId: number) => {
    setSelectedEstimateId(null);
    setSelectedOrderId(orderId);
  };

  const focusPanelByCallback = (pane: PaneId, panelId: string) => {
    setPanePanel(pane, panelId);
    setCommandOpen(false);
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
        focusPanelByCallback("top", "estimates-list");
        if (parsed.id !== null) {
          openEstimate(parsed.id);
        }
        return;
      case "order_view":
      case "order_submit":
      case "order_assign":
      case "order_start":
      case "order_complete":
      case "order_pay":
      case "order_cancel":
        focusPanelByCallback("top", "orders-list");
        if (parsed.id !== null) {
          openOrder(parsed.id);
        }
        return;
      case "disc_detail":
      case "approvals":
        focusPanelByCallback("top", "approvals-queue");
        return;
      case "notif_open":
        focusPanelByCallback("top", "notifications-list");
        return;
      case "profile":
      case "profile_edit":
      case "profile_requisites":
        focusPanelByCallback("bottom", "profile-card");
        return;
      case "profile_role_mode":
        setRoleDrawerOpen(true);
        return;
      case "catalog":
      case "search":
      case "popular":
        focusPanelByCallback("top", "catalog-browser");
        return;
      case "my_estimates":
        focusPanelByCallback("top", "estimates-list");
        return;
      case "my_orders":
        focusPanelByCallback("top", "orders-list");
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
        focusPanelByCallback("top", "control-center");
        return;
      default:
        focusPanelByCallback("top", "workspace-overview");
    }
  };

  const renderPanel = (panelId: string) => {
    switch (panelId) {
      case "board-feed":
        return <BoardPanel externalUserId={externalUserId} bootstrap={bootState} onOpenResponses={setSelectedBoardPostId} />;
      case "network-directory":
        return (
          <NetworkPanel
            externalUserId={externalUserId}
            bootstrap={bootState}
            onOpenMaster={setSelectedMasterId}
            onOpenProfile={() => setPanePanel("bottom", "profile-card")}
          />
        );
      case "workspace-overview":
        return <WorkspacePanel bootstrap={bootState} onFocusPanel={setPanePanel} onOpenWorkflow={handleWorkflowTarget} />;
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

  const topMeta = panelLookup.get(layout.panes.top) ?? panels[0];
  const bottomMeta = panelLookup.get(layout.panes.bottom) ?? panels[0];
  const activeRoleLabel = roleModeQuery.data?.active_role_label || bootState.workspace.active_role_label;
  const maxRoleLabel = roleModeQuery.data?.max_role_label || bootState.workspace.max_role_label;
  const canSwitchRole = roleModeQuery.data?.can_switch_role || bootState.workspace.can_switch_role;

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
        onOpenRoleMode={() => setRoleDrawerOpen(true)}
        onSelectPreset={(presetId) => void presetMutation.mutateAsync(presetId)}
        onOpenModules={() => setCommandOpen(true)}
        onOpenProfile={() => setPanePanel("bottom", "profile-card")}
      />

      <main className="workspace-frame" data-testid="workspace-frame">
        <Group
          orientation={splitDirection}
          onLayout={(sizes) => {
            if (sizes[0]) {
              setRatio(Number(sizes[0].toFixed(1)));
            }
          }}
        >
          <Panel defaultSize={layout.ratio} minSize={splitDirection === "horizontal" ? 32 : 34}>
            <PaneSurface
              paneId="top"
              panelId={layout.panes.top}
              title={topMeta?.title || "Панель"}
              icon={topMeta?.icon || "layers"}
              direction={splitDirection}
              panels={panels}
              onChange={setPanePanel}
            >
              {renderPanel(layout.panes.top)}
            </PaneSurface>
          </Panel>
          <Separator className="resize-handle">
            <div className="handle-core" />
          </Separator>
          <Panel defaultSize={100 - layout.ratio} minSize={splitDirection === "horizontal" ? 30 : 28}>
            <PaneSurface
              paneId="bottom"
              panelId={layout.panes.bottom}
              title={bottomMeta?.title || "Панель"}
              icon={bottomMeta?.icon || "users"}
              direction={splitDirection}
              panels={panels}
              onChange={setPanePanel}
            >
              {renderPanel(layout.panes.bottom)}
            </PaneSurface>
          </Panel>
        </Group>
      </main>

      <footer className="dock" data-testid="workspace-dock">
        <button data-testid="dock-market" className={`dock-btn ${layout.preset === "market" ? "strong" : ""}`} onClick={() => void presetMutation.mutateAsync("market")}>
          Рынок
        </button>
        <button data-testid="dock-workbench" className={`dock-btn ${layout.preset === "workbench" ? "strong" : ""}`} onClick={() => void presetMutation.mutateAsync("workbench")}>
          Работа
        </button>
        {presets.some((item) => item.id === "control") ? (
          <button data-testid="dock-control" className={`dock-btn ${layout.preset === "control" ? "strong" : ""}`} onClick={() => void presetMutation.mutateAsync("control")}>
            Операции
          </button>
        ) : null}
        <button data-testid="dock-profile" className="dock-btn" onClick={() => setPanePanel("bottom", "profile-card")}>
          Профиль
        </button>
        <button data-testid="dock-modules" className="dock-btn strong" onClick={() => setCommandOpen(true)}>
          Все модули
        </button>
      </footer>

      <CommandPalette open={commandOpen} panels={panels} onClose={() => setCommandOpen(false)} onSelect={setPanePanel} />
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
      <EstimateDrawer externalUserId={externalUserId} estimateId={selectedEstimateId} onClose={() => setSelectedEstimateId(null)} onFocusPanel={setPanePanel} onOpenOrder={openOrder} />
      <OrderDrawer externalUserId={externalUserId} orderId={selectedOrderId} onClose={() => setSelectedOrderId(null)} />
    </div>
  );
}
