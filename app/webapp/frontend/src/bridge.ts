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
  const hasMax = Boolean(maxBridge?.initData);
  const hasTelegram = Boolean(telegramBridge?.initData);
  const embedded = hasMax || hasTelegram;

  if (hasMax) {
    return {
      platform: "max",
      initData: maxBridge?.initData ?? "",
      embedded: true,
    };
  }

  if (hasTelegram) {
    return {
      platform: "telegram",
      initData: telegramBridge?.initData ?? "",
      embedded: true,
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
  maxBridge?.ready?.();
  maxBridge?.expand?.();
  maxBridge?.enableClosingConfirmation?.();
  telegramBridge?.ready?.();
  telegramBridge?.expand?.();
}
