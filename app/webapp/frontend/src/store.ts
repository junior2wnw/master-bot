import { create } from "zustand";

import type { BootstrapResponse, LayoutPayload, PanelMeta, PresetMeta } from "./types";
import { ensureComposerLayout } from "./windowLayout";

interface WorkspaceState {
  layout: LayoutPayload | null;
  panels: PanelMeta[];
  presets: PresetMeta[];
  bootstrap: BootstrapResponse | null;
  commandOpen: boolean;
  hydrateFromBootstrap: (bootstrap: BootstrapResponse) => void;
  replaceLayout: (layout: LayoutPayload) => void;
  updateLayout: (updater: (layout: LayoutPayload) => LayoutPayload) => void;
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
      layout: ensureComposerLayout(bootstrap.layout, bootstrap.panels),
      panels: bootstrap.panels,
      presets: bootstrap.presets,
    }),
  replaceLayout: (layout) =>
    set((state) => {
      if (!state.panels.length) {
        return { layout };
      }
      return {
        layout: ensureComposerLayout(layout, state.panels),
      };
    }),
  updateLayout: (updater) =>
    set((state) => {
      if (!state.layout) {
        return state;
      }
      return {
        layout: ensureComposerLayout(updater(state.layout), state.panels),
      };
    }),
  setCommandOpen: (value) => set({ commandOpen: value }),
}));
