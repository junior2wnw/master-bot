import type {
  AnalyticsOverview,
  ApprovalItem,
  AuthResponse,
  BoardResponse,
  BootstrapResponse,
  CatalogItem,
  EstimateDetail,
  EstimateSummary,
  JobPost,
  LayoutPayload,
  NetworkResponse,
  NotificationItem,
  OrderSummary,
  ProfileResponse,
  PublicProfileResponse,
} from "./types";
import { resolveBridge } from "./bridge";

const API_ROOT = "/api/v1";
const SESSION_STORAGE_KEY = "pridel.session";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type SessionSnapshot = {
  accessToken: string;
  externalUserId: number;
  expiresAt: number;
};

let sessionSnapshot: SessionSnapshot | null = null;

function readStoredSession(): SessionSnapshot | null {
  if (sessionSnapshot) {
    return sessionSnapshot;
  }
  const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as SessionSnapshot;
    if (!parsed.accessToken || !parsed.externalUserId || !parsed.expiresAt) {
      return null;
    }
    if (parsed.expiresAt * 1000 <= Date.now()) {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    sessionSnapshot = parsed;
    return parsed;
  } catch {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

function persistSession(auth: AuthResponse): void {
  sessionSnapshot = {
    accessToken: auth.access_token,
    externalUserId: auth.telegram_id,
    expiresAt: auth.expires_at,
  };
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessionSnapshot));
}

function buildUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(`${API_ROOT}${path}`, window.location.origin);
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    url.searchParams.set(key, String(value));
  });
  return `${url.pathname}${url.search}`;
}

async function request<T>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PUT" | "PATCH";
    body?: unknown;
    params?: Record<string, string | number | boolean | undefined>;
  } = {},
): Promise<T> {
  const session = readStoredSession();
  const response = await fetch(buildUrl(path, options.params), {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.accessToken}` } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = "Не удалось загрузить данные";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        message = payload.detail;
      }
    } catch {
      // ignore
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

export const api = {
  async auth(): Promise<AuthResponse> {
    const bridge = resolveBridge();
    const response = await request<AuthResponse>("/auth", {
      method: "POST",
      body: {
        init_data: bridge.initData,
        platform: bridge.platform,
      },
    });
    persistSession(response);
    return response;
  },
  bootstrap(externalUserId: number, preset?: string) {
    return request<BootstrapResponse>("/superapp/bootstrap", {
      params: { preset },
    });
  },
  getLayout(externalUserId: number, preset?: string) {
    return request<LayoutPayload>("/superapp/layout", {
      params: { preset },
    });
  },
  saveLayout(externalUserId: number, preset: string, layout: LayoutPayload) {
    return request<LayoutPayload>("/superapp/layout", {
      method: "PUT",
      body: { preset, layout },
    });
  },
  listBoardPosts(externalUserId: number, params?: Record<string, string | number | boolean | undefined>) {
    return request<BoardResponse>("/board/posts", {
      params,
    });
  },
  createBoardPost(externalUserId: number, body: Record<string, unknown>) {
    return request<JobPost>("/board/posts", {
      method: "POST",
      body,
    });
  },
  respondBoardPost(externalUserId: number, postId: number, body: Record<string, unknown>) {
    return request<{ id: number; status: string }>(`/board/posts/${postId}/responses`, {
      method: "POST",
      body,
    });
  },
  listMasters(externalUserId: number, params?: Record<string, string | number | boolean | undefined>) {
    return request<NetworkResponse>("/network/masters", {
      params,
    });
  },
  getMaster(externalUserId: number, masterExternalUserId: number) {
    return request<PublicProfileResponse>(`/network/masters/${masterExternalUserId}`);
  },
  getPublicProfile(externalUserId: number) {
    return request<PublicProfileResponse>("/network/profile");
  },
  updatePublicProfile(externalUserId: number, body: Record<string, unknown>) {
    return request<PublicProfileResponse>("/network/profile", {
      method: "PUT",
      body,
    });
  },
  searchCatalog(externalUserId: number, query: string) {
    return request<CatalogItem[]>("/catalog/search", {
      params: { q: query },
    });
  },
  listEstimates(externalUserId: number) {
    return request<EstimateSummary[]>("/estimates");
  },
  createEstimate(externalUserId: number) {
    return request<{ id: number; status: string }>("/estimates", {
      method: "POST",
    });
  },
  getEstimate(externalUserId: number, estimateId: number) {
    return request<EstimateDetail>(`/estimates/${estimateId}`);
  },
  addEstimateItem(externalUserId: number, estimateId: number, serviceItemId: number) {
    return request<{ id: number; name: string; subtotal: number }>(`/estimates/${estimateId}/items`, {
      method: "POST",
      body: {
        service_item_id: serviceItemId,
        quantity: 1,
      },
    });
  },
  listOrders(externalUserId: number) {
    return request<OrderSummary[]>("/orders");
  },
  listNotifications(externalUserId: number) {
    return request<NotificationItem[]>("/notifications");
  },
  markNotificationRead(externalUserId: number, notificationId: number) {
    return request<{ ok: boolean }>(`/notifications/${notificationId}/read`, {
      method: "POST",
    });
  },
  getProfile(externalUserId: number) {
    return request<ProfileResponse>("/profile");
  },
  updateProfile(externalUserId: number, body: Record<string, unknown>) {
    return request<{ ok: boolean }>("/profile", {
      method: "PUT",
      body,
    });
  },
  listApprovals(externalUserId: number) {
    return request<ApprovalItem[]>("/approvals");
  },
  getAnalytics(externalUserId: number) {
    return request<AnalyticsOverview>("/analytics/overview");
  },
};
