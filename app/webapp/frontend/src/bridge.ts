import type { Platform } from "./types";

type EmbeddedBridge = {
  initData?: string;
  ready?: () => void;
  expand?: () => void;
  enableClosingConfirmation?: () => void;
  disableClosingConfirmation?: () => void;
  openLink?: (url: string) => void;
  openTelegramLink?: (url: string) => void;
};

declare global {
  interface Window {
    WebApp?: EmbeddedBridge;
    Telegram?: {
      WebApp?: EmbeddedBridge;
    };
  }
}

export interface BridgeContext {
  platform: Platform;
  initData: string;
  embedded: boolean;
}

const LAUNCH_DATA_STORAGE_KEY = "pridel.launchData";

function isLocalDevHost(): boolean {
  const host = window.location.hostname.toLowerCase();
  return host === "localhost" || host === "127.0.0.1" || host.endsWith(".local");
}

function persistLaunchData(initData: string): void {
  if (!initData) {
    return;
  }
  window.sessionStorage.setItem(LAUNCH_DATA_STORAGE_KEY, initData);
}

function readStoredLaunchData(): string {
  return window.sessionStorage.getItem(LAUNCH_DATA_STORAGE_KEY) ?? "";
}

function readHashLaunchData(): string {
  const rawHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!rawHash) {
    return "";
  }

  const params = new URLSearchParams(rawHash);
  const initData =
    params.get("WebAppData") ??
    params.get("tgWebAppData") ??
    params.get("init_data") ??
    params.get("initData") ??
    "";
  if (!initData) {
    return "";
  }

  persistLaunchData(initData);
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  return initData;
}

function readDevPayload(): string {
  const params = new URLSearchParams(window.location.search);
  const direct = params.get("dev_user");
  if (direct) {
    return direct;
  }
  const stored = window.localStorage.getItem("pridel.devUser");
  if (stored) {
    return stored;
  }
  const fallback = JSON.stringify({
    id: 71142489,
    first_name: "Алик",
    username: "alik_dev",
  });
  window.localStorage.setItem("pridel.devUser", fallback);
  return fallback;
}

export function resolveBridge(): BridgeContext {
  const maxBridge = window.WebApp;
  const telegramBridge = window.Telegram?.WebApp;
  const maxInitData = maxBridge?.initData ?? "";
  const telegramInitData = telegramBridge?.initData ?? "";
  const hashInitData = readHashLaunchData();
  const storedInitData = readStoredLaunchData();

  if (maxInitData) {
    persistLaunchData(maxInitData);
    return {
      platform: "max",
      initData: maxInitData,
      embedded: true,
    };
  }

  if (telegramInitData) {
    persistLaunchData(telegramInitData);
    return {
      platform: "telegram",
      initData: telegramInitData,
      embedded: true,
    };
  }

  if (hashInitData) {
    return {
      platform: "max",
      initData: hashInitData,
      embedded: true,
    };
  }

  if (storedInitData) {
    return {
      platform: "max",
      initData: storedInitData,
      embedded: true,
    };
  }

  if (!isLocalDevHost()) {
    return {
      platform: "max",
      initData: "",
      embedded: false,
    };
  }

  return {
    platform: "max",
    initData: readDevPayload(),
    embedded: false,
  };
}

export function prepareBridge(): void {
  const maxBridge = window.WebApp;
  const telegramBridge = window.Telegram?.WebApp;
  const hashInitData = readHashLaunchData();
  if (hashInitData) {
    persistLaunchData(hashInitData);
  }
  maxBridge?.ready?.();
  maxBridge?.expand?.();
  maxBridge?.enableClosingConfirmation?.();
  telegramBridge?.ready?.();
  telegramBridge?.expand?.();
}
