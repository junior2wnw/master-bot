import { Fragment, type ReactNode, useMemo } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { Glyph, PanelPicker } from "./appHelpers";
import type { ComposerNode, ComposerWindowNode, LayoutPayload, PanelMeta } from "./types";
import { ensureComposerLayout, listComposerWindows } from "./windowLayout";

function WindowRail({
  windows,
  panelLookup,
  activeWindowId,
  compact,
  onSelect,
}: {
  windows: ComposerWindowNode[];
  panelLookup: Map<string, PanelMeta>;
  activeWindowId: string;
  compact: boolean;
  onSelect: (windowId: string) => void;
}) {
  return (
    <div className={`window-rail ${compact ? "window-rail-compact" : ""}`} data-testid="window-rail">
      {windows.map((window) => {
        const meta = panelLookup.get(window.panel_id);
        return (
          <button
            key={window.id}
            type="button"
            className={`window-pill ${window.id === activeWindowId ? "active" : ""}`}
            data-testid={`window-pill-${window.id}`}
            onClick={() => onSelect(window.id)}
          >
            <span className="window-pill-mark">
              <Glyph name={meta?.icon || "spark"} />
            </span>
            <strong>{meta?.title || "Окно"}</strong>
          </button>
        );
      })}
    </div>
  );
}

function WindowCard({
  window,
  panelLookup,
  compact,
  active,
  spotlight,
  availablePanels,
  onFocus,
  onChangePanel,
  onClose,
  onToggleSpotlight,
  children,
}: {
  window: ComposerWindowNode;
  panelLookup: Map<string, PanelMeta>;
  compact: boolean;
  active: boolean;
  spotlight: boolean;
  availablePanels: PanelMeta[];
  onFocus: () => void;
  onChangePanel: (panelId: string) => void;
  onClose: () => void;
  onToggleSpotlight: () => void;
  children: ReactNode;
}) {
  const meta = panelLookup.get(window.panel_id);

  return (
    <section
      className={`window-card ${active ? "active" : ""} ${spotlight ? "spotlight" : ""} ${compact ? "compact" : ""}`}
      data-testid={`window-card-${window.id}`}
      onClick={onFocus}
    >
      <header className="window-card-head" onDoubleClick={onToggleSpotlight}>
        <div className="window-card-title">
          <span className="window-pill-mark">
            <Glyph name={meta?.icon || "spark"} />
          </span>
          <div>
            <strong>{meta?.title || "Окно"}</strong>
            <span>{meta?.subtitle || "Рабочий модуль"}</span>
          </div>
        </div>
        <div className="window-card-actions">
          {active ? <PanelPicker value={window.panel_id} options={availablePanels} onChange={onChangePanel} /> : null}
          <button
            type="button"
            className="window-icon-btn"
            aria-label={spotlight ? "Вернуть обычный вид" : "Включить фокус"}
            onClick={(event) => {
              event.stopPropagation();
              onToggleSpotlight();
            }}
          >
            {spotlight ? "Сетка" : "Фокус"}
          </button>
          <button
            type="button"
            className="window-icon-btn"
            aria-label="Закрыть окно"
            onClick={(event) => {
              event.stopPropagation();
              onClose();
            }}
          >
            Закрыть
          </button>
        </div>
      </header>
      <div className="window-card-body">{children}</div>
    </section>
  );
}

function ComposerNodeView({
  node,
  compact,
  panelLookup,
  availablePanels,
  activeWindowId,
  spotlightWindowId,
  onFocusWindow,
  onChangePanel,
  onCloseWindow,
  onToggleSpotlight,
  onResizeSplit,
  renderPanel,
}: {
  node: ComposerNode;
  compact: boolean;
  panelLookup: Map<string, PanelMeta>;
  availablePanels: PanelMeta[];
  activeWindowId: string;
  spotlightWindowId: string | null;
  onFocusWindow: (windowId: string) => void;
  onChangePanel: (windowId: string, panelId: string) => void;
  onCloseWindow: (windowId: string) => void;
  onToggleSpotlight: (windowId: string) => void;
  onResizeSplit: (splitId: string, sizes: number[]) => void;
  renderPanel: (panelId: string) => ReactNode;
}) {
  if (node.kind === "window") {
    return (
      <WindowCard
        window={node}
        panelLookup={panelLookup}
        compact={compact}
        active={activeWindowId === node.id}
        spotlight={spotlightWindowId === node.id}
        availablePanels={availablePanels}
        onFocus={() => onFocusWindow(node.id)}
        onChangePanel={(panelId) => onChangePanel(node.id, panelId)}
        onClose={() => onCloseWindow(node.id)}
        onToggleSpotlight={() => onToggleSpotlight(node.id)}
      >
        {renderPanel(node.panel_id)}
      </WindowCard>
    );
  }

  return (
    <div className={`window-split window-split-${node.axis}`} data-testid={`window-split-${node.id}`}>
      <Group orientation={node.axis} onLayout={(sizes) => onResizeSplit(node.id, sizes)}>
        {node.children.map((child, index) => (
          <Fragment key={child.id}>
            <Panel defaultSize={node.sizes[index] ?? Math.round(100 / node.children.length)}>
              <ComposerNodeView
                node={child}
                compact={compact}
                panelLookup={panelLookup}
                availablePanels={availablePanels}
                activeWindowId={activeWindowId}
                spotlightWindowId={spotlightWindowId}
                onFocusWindow={onFocusWindow}
                onChangePanel={onChangePanel}
                onCloseWindow={onCloseWindow}
                onToggleSpotlight={onToggleSpotlight}
                onResizeSplit={onResizeSplit}
                renderPanel={renderPanel}
              />
            </Panel>
            {index < node.children.length - 1 ? (
              <Separator className="resize-handle">
                <div className="handle-core" />
              </Separator>
            ) : null}
          </Fragment>
        ))}
      </Group>
    </div>
  );
}

export function WindowComposer({
  layout,
  panels,
  compact,
  activeCompactWindowId,
  onSelectCompactWindow,
  onFocusWindow,
  onChangeWindowPanel,
  onCloseWindow,
  onToggleSpotlight,
  onResizeSplit,
  renderPanel,
}: {
  layout: LayoutPayload;
  panels: PanelMeta[];
  compact: boolean;
  activeCompactWindowId: string;
  onSelectCompactWindow: (windowId: string) => void;
  onFocusWindow: (windowId: string) => void;
  onChangeWindowPanel: (windowId: string, panelId: string) => void;
  onCloseWindow: (windowId: string) => void;
  onToggleSpotlight: (windowId: string) => void;
  onResizeSplit: (splitId: string, sizes: number[]) => void;
  renderPanel: (panelId: string) => ReactNode;
}) {
  const nextLayout = ensureComposerLayout(layout, panels);
  const composer = nextLayout.composer!;
  const windowNodes = listComposerWindows(composer.root);
  const panelLookup = useMemo(() => new Map(panels.map((panel) => [panel.id, panel])), [panels]);
  const spotlightWindow = composer.spotlight_window_id
    ? windowNodes.find((window) => window.id === composer.spotlight_window_id) ?? null
    : null;
  const compactWindow = windowNodes.find((window) => window.id === activeCompactWindowId) ?? windowNodes[0];

  return (
    <div className={`window-composer ${compact ? "compact" : ""}`} data-testid="window-composer">
      <WindowRail
        windows={windowNodes}
        panelLookup={panelLookup}
        activeWindowId={compact ? compactWindow.id : composer.focus_window_id}
        compact={compact}
        onSelect={(windowId) => {
          if (compact) {
            onSelectCompactWindow(windowId);
          }
          onFocusWindow(windowId);
        }}
      />
      {compact ? (
        <div className="window-composer-compact-stage" data-testid="window-composer-compact-stage">
          <ComposerNodeView
            node={compactWindow}
            compact
            panelLookup={panelLookup}
            availablePanels={panels}
            activeWindowId={compactWindow.id}
            spotlightWindowId={composer.spotlight_window_id}
            onFocusWindow={onFocusWindow}
            onChangePanel={onChangeWindowPanel}
            onCloseWindow={onCloseWindow}
            onToggleSpotlight={onToggleSpotlight}
            onResizeSplit={onResizeSplit}
            renderPanel={renderPanel}
          />
        </div>
      ) : spotlightWindow ? (
        <div className="window-spotlight-stage" data-testid="window-spotlight-stage">
          <ComposerNodeView
            node={spotlightWindow}
            compact={false}
            panelLookup={panelLookup}
            availablePanels={panels}
            activeWindowId={composer.focus_window_id}
            spotlightWindowId={composer.spotlight_window_id}
            onFocusWindow={onFocusWindow}
            onChangePanel={onChangeWindowPanel}
            onCloseWindow={onCloseWindow}
            onToggleSpotlight={onToggleSpotlight}
            onResizeSplit={onResizeSplit}
            renderPanel={renderPanel}
          />
        </div>
      ) : (
        <div className="window-canvas-stage" data-testid="window-canvas-stage">
          <ComposerNodeView
            node={composer.root}
            compact={false}
            panelLookup={panelLookup}
            availablePanels={panels}
            activeWindowId={composer.focus_window_id}
            spotlightWindowId={composer.spotlight_window_id}
            onFocusWindow={onFocusWindow}
            onChangePanel={onChangeWindowPanel}
            onCloseWindow={onCloseWindow}
            onToggleSpotlight={onToggleSpotlight}
            onResizeSplit={onResizeSplit}
            renderPanel={renderPanel}
          />
        </div>
      )}
    </div>
  );
}
