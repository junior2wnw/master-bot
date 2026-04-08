import { create } from "zustand";

import type { BootstrapResponse, LayoutPayload, PaneId, PanelMeta, PresetMeta } from "./types";

interface WorkspaceState {
  layout: LayoutPayload | null;
  panels: PanelMeta[];
  presets: PresetMeta[];
  bootstrap: BootstrapResponse | null;
  commandOpen: boolean;
  hydrateFromBootstrap: (bootstrap: BootstrapResponse) => void;
  replaceLayout: (layout: LayoutPayload) => void;
  setPanePanel: (pane: PaneId, panelId: string) => void;
  setRatio: (ratio: number) => void;
  setCommandOpen: (value: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  layout: null,
  panels: [],
  presets: [],
  bootstrap: null,
  commandOpen: false,
  hydrateFromBootstrap: (bootstrap) =>
    set({
      bootstrap,
      layout: bootstrap.layout,
      panels: bootstrap.panels,
      presets: bootstrap.presets,
    }),
  replaceLayout: (layout) => set({ layout }),
  setPanePanel: (pane, panelId) =>
    set((state) => {
      if (!state.layout) {
        return state;
      }
      return {
        layout: {
          ...state.layout,
          panes: {
            ...state.layout.panes,
            [pane]: panelId,
          },
        },
      };
    }),
  setRatio: (ratio) =>
    set((state) => {
      if (!state.layout) {
        return state;
      }
      return {
        layout: {
          ...state.layout,
          ratio,
        },
      };
    }),
  setCommandOpen: (value) => set({ commandOpen: value }),
}));
