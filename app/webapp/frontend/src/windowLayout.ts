import type {
  ComposerAxis,
  ComposerLayout,
  ComposerNode,
  ComposerSplitNode,
  ComposerWindowNode,
  LayoutPayload,
  PanelMeta,
} from "./types";

const MIN_RATIO = 34;
const MAX_RATIO = 70;
const MIN_SPLIT_SIZE = 16;

function roundSize(value: number): number {
  return Math.round(value * 10) / 10;
}

function nextNodeId(prefix: "window" | "split"): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeSizes(values: number[] | undefined, count: number): number[] {
  if (count <= 0) {
    return [];
  }
  const source = Array.isArray(values) ? values.slice(0, count) : [];
  if (source.length !== count) {
    return Array.from({ length: count }, () => roundSize(100 / count));
  }
  const cleaned = source.map((value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return 100 / count;
    }
    return Math.max(MIN_SPLIT_SIZE, numeric);
  });
  const total = cleaned.reduce((sum, value) => sum + value, 0);
  if (!total) {
    return Array.from({ length: count }, () => roundSize(100 / count));
  }
  const normalized = cleaned.map((value) => roundSize((value / total) * 100));
  const diff = roundSize(100 - normalized.reduce((sum, value) => sum + value, 0));
  normalized[normalized.length - 1] = roundSize(normalized[normalized.length - 1] + diff);
  return normalized;
}

function clampRatio(value: number | undefined, fallback = 50): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return roundSize(Math.min(MAX_RATIO, Math.max(MIN_RATIO, Number(value))));
}

function buildFallbackPanels(layout: LayoutPayload, panels: PanelMeta[]): { top: string; bottom: string } {
  const allowed = panels.map((panel) => panel.id);
  const firstAllowed = allowed[0] ?? "workspace-overview";
  const secondAllowed = allowed.find((panelId) => panelId !== firstAllowed) ?? firstAllowed;
  const top = allowed.includes(layout.panes.top) ? layout.panes.top : firstAllowed;
  const bottom = allowed.includes(layout.panes.bottom) && layout.panes.bottom !== top ? layout.panes.bottom : secondAllowed;
  return { top, bottom };
}

export function buildComposerFromLegacy(layout: LayoutPayload, panels: PanelMeta[]): ComposerLayout {
  const fallbackPanels = buildFallbackPanels(layout, panels);
  const topWindowId = nextNodeId("window");
  const bottomWindowId = nextNodeId("window");
  return {
    root: {
      id: nextNodeId("split"),
      kind: "split",
      axis: "vertical",
      children: [
        {
          id: topWindowId,
          kind: "window",
          panel_id: fallbackPanels.top,
        },
        {
          id: bottomWindowId,
          kind: "window",
          panel_id: fallbackPanels.bottom,
        },
      ],
      sizes: [clampRatio(layout.ratio, 56), roundSize(100 - clampRatio(layout.ratio, 56))],
    },
    focus_window_id: topWindowId,
    spotlight_window_id: null,
  };
}

export function listComposerWindows(node: ComposerNode): ComposerWindowNode[] {
  if (node.kind === "window") {
    return [node];
  }
  return node.children.flatMap((child) => listComposerWindows(child));
}

function findWindowPath(node: ComposerNode, windowId: string, path: number[] = []): number[] | null {
  if (node.kind === "window") {
    return node.id === windowId ? path : null;
  }
  for (const [index, child] of node.children.entries()) {
    const match = findWindowPath(child, windowId, [...path, index]);
    if (match) {
      return match;
    }
  }
  return null;
}

function findSplitPath(node: ComposerNode, splitId: string, path: number[] = []): number[] | null {
  if (node.kind !== "split") {
    return null;
  }
  if (node.id === splitId) {
    return path;
  }
  for (const [index, child] of node.children.entries()) {
    const match = findSplitPath(child, splitId, [...path, index]);
    if (match) {
      return match;
    }
  }
  return null;
}

function getNodeAtPath(root: ComposerNode, path: number[]): ComposerNode {
  let current = root;
  for (const index of path) {
    if (current.kind !== "split" || !current.children[index]) {
      return root;
    }
    current = current.children[index];
  }
  return current;
}

function updateNodeAtPath(root: ComposerNode, path: number[], updater: (node: ComposerNode) => ComposerNode): ComposerNode {
  if (!path.length) {
    return updater(root);
  }
  if (root.kind !== "split") {
    return root;
  }
  const [head, ...rest] = path;
  return {
    ...root,
    children: root.children.map((child, index) => {
      if (index !== head) {
        return child;
      }
      return updateNodeAtPath(child, rest, updater);
    }),
  };
}

function removeNodeAtPath(root: ComposerNode, path: number[]): ComposerNode | null {
  if (!path.length) {
    return null;
  }
  if (root.kind !== "split") {
    return root;
  }
  const [head, ...rest] = path;
  const nextChildren = root.children.slice();
  const removedDirectChild = !rest.length;
  if (!rest.length) {
    nextChildren.splice(head, 1);
  } else {
    const nextChild = removeNodeAtPath(nextChildren[head], rest);
    if (nextChild === null) {
      nextChildren.splice(head, 1);
    } else {
      nextChildren[head] = nextChild;
    }
  }
  if (!nextChildren.length) {
    return null;
  }
  if (nextChildren.length === 1) {
    return nextChildren[0];
  }
  return {
    ...root,
    children: nextChildren,
    sizes: normalizeSizes(removedDirectChild ? root.sizes.filter((_, index) => index !== head) : root.sizes, nextChildren.length),
  };
}

function insertSiblingSize(values: number[], targetIndex: number, insertIndex: number): number[] {
  const normalized = normalizeSizes(values, values.length);
  const sourceSize = normalized[targetIndex] ?? roundSize(100 / normalized.length);
  const nextSize = roundSize(Math.max(MIN_SPLIT_SIZE, sourceSize * 0.45));
  normalized[targetIndex] = roundSize(Math.max(MIN_SPLIT_SIZE, sourceSize - nextSize));
  normalized.splice(insertIndex, 0, nextSize);
  return normalizeSizes(normalized, normalized.length);
}

function syncLegacyFields(layout: LayoutPayload, panels: PanelMeta[]): LayoutPayload {
  const composer = layout.composer;
  if (!composer) {
    return layout;
  }
  const windows = listComposerWindows(composer.root);
  const allowed = panels.map((panel) => panel.id);
  const firstAllowed = allowed[0] ?? layout.panes.top;
  const topPanel = windows[0]?.panel_id ?? firstAllowed;
  const bottomPanel = windows.find((window) => window.panel_id !== topPanel)?.panel_id ?? allowed.find((panelId) => panelId !== topPanel) ?? topPanel;
  const ratio = composer.root.kind === "split" ? clampRatio(composer.root.sizes[0], layout.ratio) : clampRatio(layout.ratio, 50);
  return {
    ...layout,
    version: Math.max(2, layout.version || 1),
    ratio,
    panes: {
      top: topPanel,
      bottom: bottomPanel,
    },
  };
}

export function ensureComposerLayout(layout: LayoutPayload, panels: PanelMeta[]): LayoutPayload {
  const fallbackComposer = buildComposerFromLegacy(layout, panels);
  const composer = layout.composer;
  if (!composer) {
    return syncLegacyFields(
      {
        ...layout,
        version: Math.max(2, layout.version || 1),
        composer: fallbackComposer,
      },
      panels,
    );
  }
  const windows = listComposerWindows(composer.root);
  if (!windows.length) {
    return syncLegacyFields(
      {
        ...layout,
        version: Math.max(2, layout.version || 1),
        composer: fallbackComposer,
      },
      panels,
    );
  }
  const focusWindowId = windows.some((window) => window.id === composer.focus_window_id) ? composer.focus_window_id : windows[0].id;
  const spotlightWindowId =
    composer.spotlight_window_id && windows.some((window) => window.id === composer.spotlight_window_id)
      ? composer.spotlight_window_id
      : null;
  return syncLegacyFields(
    {
      ...layout,
      version: Math.max(2, layout.version || 1),
      composer: {
        ...composer,
        focus_window_id: focusWindowId,
        spotlight_window_id: spotlightWindowId,
      },
    },
    panels,
  );
}

export function getFocusedWindowId(layout: LayoutPayload, panels: PanelMeta[]): string {
  const nextLayout = ensureComposerLayout(layout, panels);
  return nextLayout.composer?.focus_window_id ?? listComposerWindows(buildComposerFromLegacy(layout, panels).root)[0].id;
}

export function focusComposerWindow(layout: LayoutPayload, panels: PanelMeta[], windowId: string): LayoutPayload {
  const nextLayout = ensureComposerLayout(layout, panels);
  const windows = listComposerWindows(nextLayout.composer!.root);
  if (!windows.some((window) => window.id === windowId)) {
    return nextLayout;
  }
  return {
    ...nextLayout,
    composer: {
      ...nextLayout.composer!,
      focus_window_id: windowId,
    },
  };
}

export function toggleSpotlightWindow(layout: LayoutPayload, panels: PanelMeta[], windowId: string): LayoutPayload {
  const nextLayout = focusComposerWindow(layout, panels, windowId);
  return {
    ...nextLayout,
    composer: {
      ...nextLayout.composer!,
      spotlight_window_id: nextLayout.composer?.spotlight_window_id === windowId ? null : windowId,
    },
  };
}

export function findComposerWindowByPanel(layout: LayoutPayload, panels: PanelMeta[], panelId: string): ComposerWindowNode | null {
  const nextLayout = ensureComposerLayout(layout, panels);
  return listComposerWindows(nextLayout.composer!.root).find((window) => window.panel_id === panelId) ?? null;
}

export function replaceWindowPanel(
  layout: LayoutPayload,
  panels: PanelMeta[],
  windowId: string,
  panelId: string,
): LayoutPayload {
  const nextLayout = ensureComposerLayout(layout, panels);
  const path = findWindowPath(nextLayout.composer!.root, windowId);
  if (!path) {
    return nextLayout;
  }
  const nextRoot = updateNodeAtPath(nextLayout.composer!.root, path, (node) =>
    node.kind === "window"
      ? {
          ...node,
          panel_id: panelId,
        }
      : node,
  );
  return syncLegacyFields(
    {
      ...nextLayout,
      composer: {
        ...nextLayout.composer!,
        root: nextRoot,
        focus_window_id: windowId,
      },
    },
    panels,
  );
}

type InsertWindowArgs = {
  targetWindowId: string;
  panelId: string;
  axis: ComposerAxis;
  position?: "before" | "after";
};

function insertWindow(layout: LayoutPayload, panels: PanelMeta[], args: InsertWindowArgs): LayoutPayload {
  const nextLayout = ensureComposerLayout(layout, panels);
  const path = findWindowPath(nextLayout.composer!.root, args.targetWindowId);
  if (!path) {
    return nextLayout;
  }
  const targetNode = getNodeAtPath(nextLayout.composer!.root, path);
  if (targetNode.kind !== "window") {
    return nextLayout;
  }
  const parentPath = path.slice(0, -1);
  const targetIndex = path[path.length - 1] ?? 0;
  const newWindow: ComposerWindowNode = {
    id: nextNodeId("window"),
    kind: "window",
    panel_id: args.panelId,
  };
  const parentNode = parentPath.length ? getNodeAtPath(nextLayout.composer!.root, parentPath) : null;

  let nextRoot: ComposerNode;
  if (parentNode && parentNode.kind === "split" && parentNode.axis === args.axis && parentNode.children.length < 4) {
    const insertIndex = args.position === "before" ? targetIndex : targetIndex + 1;
    nextRoot = updateNodeAtPath(nextLayout.composer!.root, parentPath, (node) => {
      if (node.kind !== "split") {
        return node;
      }
      const children = node.children.slice();
      children.splice(insertIndex, 0, newWindow);
      return {
        ...node,
        children,
        sizes: insertSiblingSize(node.sizes, targetIndex, insertIndex),
      };
    });
  } else {
    const splitNode: ComposerSplitNode = {
      id: nextNodeId("split"),
      kind: "split",
      axis: args.axis,
      children: args.position === "before" ? [newWindow, targetNode] : [targetNode, newWindow],
      sizes: [50, 50],
    };
    nextRoot = updateNodeAtPath(nextLayout.composer!.root, path, () => splitNode);
  }

  return syncLegacyFields(
    {
      ...nextLayout,
      composer: {
        ...nextLayout.composer!,
        root: nextRoot,
        focus_window_id: newWindow.id,
        spotlight_window_id: nextLayout.composer?.spotlight_window_id ?? null,
      },
    },
    panels,
  );
}

export function openPanelInComposer(
  layout: LayoutPayload,
  panels: PanelMeta[],
  args: {
    panelId: string;
    targetWindowId?: string;
    axis: ComposerAxis;
    mode?: "focus-or-add" | "replace";
  },
): LayoutPayload {
  const nextLayout = ensureComposerLayout(layout, panels);
  const existingWindow = findComposerWindowByPanel(nextLayout, panels, args.panelId);
  if (args.mode !== "replace" && existingWindow) {
    return focusComposerWindow(nextLayout, panels, existingWindow.id);
  }
  const focusWindowId = args.targetWindowId || nextLayout.composer!.focus_window_id;
  if (args.mode === "replace") {
    return replaceWindowPanel(nextLayout, panels, focusWindowId, args.panelId);
  }
  return insertWindow(nextLayout, panels, {
    targetWindowId: focusWindowId,
    panelId: args.panelId,
    axis: args.axis,
    position: "after",
  });
}

export function closeComposerWindow(layout: LayoutPayload, panels: PanelMeta[], windowId: string): LayoutPayload {
  const nextLayout = ensureComposerLayout(layout, panels);
  const windows = listComposerWindows(nextLayout.composer!.root);
  if (windows.length <= 1) {
    return nextLayout;
  }
  const path = findWindowPath(nextLayout.composer!.root, windowId);
  if (!path) {
    return nextLayout;
  }
  const windowOrder = windows.map((window) => window.id);
  const index = windowOrder.indexOf(windowId);
  const fallbackFocusId = windowOrder[index + 1] ?? windowOrder[index - 1] ?? windowOrder[0];
  const nextRoot = removeNodeAtPath(nextLayout.composer!.root, path);
  if (!nextRoot) {
    return nextLayout;
  }
  const nextWindows = listComposerWindows(nextRoot);
  const nextFocusId = nextWindows.some((window) => window.id === fallbackFocusId) ? fallbackFocusId : nextWindows[0].id;
  const spotlightWindowId =
    nextLayout.composer?.spotlight_window_id && nextLayout.composer.spotlight_window_id !== windowId
      ? nextLayout.composer.spotlight_window_id
      : null;
  return syncLegacyFields(
    {
      ...nextLayout,
      composer: {
        ...nextLayout.composer!,
        root: nextRoot,
        focus_window_id: nextFocusId,
        spotlight_window_id: spotlightWindowId,
      },
    },
    panels,
  );
}

export function resizeComposerSplit(layout: LayoutPayload, panels: PanelMeta[], splitId: string, sizes: number[]): LayoutPayload {
  const nextLayout = ensureComposerLayout(layout, panels);
  const path = findSplitPath(nextLayout.composer!.root, splitId);
  if (!path) {
    return nextLayout;
  }
  const nextRoot = updateNodeAtPath(nextLayout.composer!.root, path, (node) => {
    if (node.kind !== "split") {
      return node;
    }
    return {
      ...node,
      sizes: normalizeSizes(sizes, node.children.length),
    };
  });
  return syncLegacyFields(
    {
      ...nextLayout,
      composer: {
        ...nextLayout.composer!,
        root: nextRoot,
      },
    },
    panels,
  );
}
