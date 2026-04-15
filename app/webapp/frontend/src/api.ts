import type {
  AnalyticsOverview,
  ApprovalItem,
  AuthResponse,
  BoardResponse,
  BootstrapResponse,
  CatalogItem,
  ControlBootstrapResponse,
  ControlFeatureFlag,
  EstimateDetail,
  EstimateQrPayload,
  EstimateSummary,
  JobPost,
  JobPostResponseList,
  LayoutPayload,
  MasterProfileResponse,
  MasterReviewItem,
  NetworkResponse,
  NotificationItem,
  OrderDetail,
  OrderPaymentInfo,
  OrderSummary,
  ProfileResponse,
  PublicProfileResponse,
  RoleModeResponse,
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
  auth: AuthResponse;
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
    if (!parsed.accessToken || !parsed.externalUserId || !parsed.expiresAt || !parsed.auth) {
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
    auth,
  };
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessionSnapshot));
}

function hasActiveSession(): boolean {
  return Boolean(readStoredSession());
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
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
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

async function requestBlob(
  path: string,
  options: {
    params?: Record<string, string | number | boolean | undefined>;
  } = {},
): Promise<{ blob: Blob; filename: string }> {
  const session = readStoredSession();
  const response = await fetch(buildUrl(path, options.params), {
    headers: {
      ...(session ? { Authorization: `Bearer ${session.accessToken}` } : {}),
    },
  });

  if (!response.ok) {
    let message = "Не удалось получить файл";
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

  const disposition = response.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] || "download.bin",
  };
}

export const api = {
  hasActiveSession,
  async auth(): Promise<AuthResponse> {
    const bridge = resolveBridge();
    const cachedSession = readStoredSession();
    if (!bridge.initData && cachedSession?.auth) {
      return cachedSession.auth;
    }
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
  listBoardResponses(externalUserId: number, postId: number) {
    return request<JobPostResponseList>(`/board/posts/${postId}/responses`);
  },
  listMasters(externalUserId: number, params?: Record<string, string | number | boolean | undefined>) {
    return request<NetworkResponse>("/network/masters", {
      params,
    });
  },
  getMaster(externalUserId: number, masterExternalUserId: number) {
    return request<MasterProfileResponse>(`/network/masters/${masterExternalUserId}`);
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
  getRoleMode(externalUserId: number) {
    return request<RoleModeResponse>("/profile/role-mode");
  },
  setRoleMode(externalUserId: number, roleCode: string | null) {
    return request<RoleModeResponse>("/profile/role-mode", {
      method: "PUT",
      body: { role_code: roleCode },
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
  updateEstimateItem(externalUserId: number, estimateId: number, lineItemId: number, quantity: number) {
    return request<{ id: number; quantity: number; subtotal: number }>(
      `/estimates/${estimateId}/items/${lineItemId}`,
      {
        method: "PATCH",
        body: { quantity },
      },
    );
  },
  deleteEstimateItem(externalUserId: number, estimateId: number, lineItemId: number) {
    return request<{ ok: boolean }>(`/estimates/${estimateId}/items/${lineItemId}`, {
      method: "DELETE",
    });
  },
  deleteEstimate(externalUserId: number, estimateId: number) {
    return request<{ ok: boolean }>(`/estimates/${estimateId}`, {
      method: "DELETE",
    });
  },
  updateEstimateStatus(
    externalUserId: number,
    estimateId: number,
    body: { status: string; client_external_id?: number | null },
  ) {
    return request<{ id: number; status: string }>(`/estimates/${estimateId}/status`, {
      method: "POST",
      body,
    });
  },
  requestEstimateDiscount(externalUserId: number, estimateId: number, value: number) {
    return request<{ id: number; status: string }>(`/estimates/${estimateId}/discount`, {
      method: "POST",
      body: { value },
    });
  },
  downloadEstimatePdf(externalUserId: number, estimateId: number) {
    return requestBlob(`/estimates/${estimateId}/export/pdf`);
  },
  downloadEstimateXlsx(externalUserId: number, estimateId: number) {
    return requestBlob(`/estimates/${estimateId}/export/xlsx`);
  },
  getEstimateQr(externalUserId: number, estimateId: number) {
    return request<EstimateQrPayload>(`/estimates/${estimateId}/qr`);
  },
  listOrders(externalUserId: number) {
    return request<OrderSummary[]>("/orders");
  },
  createOrder(
    externalUserId: number,
    body: { estimate_id: number; address: string; urgency?: string; notes?: string | null },
  ) {
    return request<{ id: number; status: string }>("/orders", {
      method: "POST",
      body,
    });
  },
  getOrder(externalUserId: number, orderId: number) {
    return request<OrderDetail>(`/orders/${orderId}`);
  },
  updateOrderStatus(externalUserId: number, orderId: number, body: { status: string; reason?: string | null }) {
    return request<{ id: number; status: string }>(`/orders/${orderId}/status`, {
      method: "POST",
      body,
    });
  },
  assignOrderToSelf(externalUserId: number, orderId: number) {
    return request<{ id: number; status: string; master_id: number }>(`/orders/${orderId}/assign-self`, {
      method: "POST",
    });
  },
  getOrderPayment(externalUserId: number, orderId: number) {
    return request<OrderPaymentInfo>(`/orders/${orderId}/payment`);
  },
  createOrderReview(
    externalUserId: number,
    orderId: number,
    body: { rating: number; headline?: string | null; body?: string | null; is_public: boolean },
  ) {
    return request<MasterReviewItem>(`/orders/${orderId}/review`, {
      method: "POST",
      body,
    });
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
  processApproval(externalUserId: number, requestId: number, action: "approve" | "reject", comment?: string) {
    return request<{ ok: boolean }>(`/approvals/${requestId}`, {
      method: "POST",
      body: { action, comment },
    });
  },
  getAnalytics(externalUserId: number) {
    return request<AnalyticsOverview>("/analytics/overview");
  },
  getControlBootstrap(externalUserId: number) {
    return request<ControlBootstrapResponse>("/control/bootstrap");
  },
  listControlUsers(
    externalUserId: number,
    params?: Record<string, string | number | boolean | undefined>,
  ) {
    return request<ControlBootstrapResponse["users"]>("/control/users", {
      params,
    });
  },
  updateControlUserRole(
    externalUserId: number,
    targetExternalUserId: number,
    body: { role_code: string; enabled: boolean },
  ) {
    return request<ControlBootstrapResponse["users"]["items"][number]>(
      `/control/users/${targetExternalUserId}/roles`,
      {
        method: "PUT",
        body,
      },
    );
  },
  assignControlUserBranch(
    externalUserId: number,
    targetExternalUserId: number,
    body: { branch_id: number | null },
  ) {
    return request<ControlBootstrapResponse["users"]["items"][number]>(
      `/control/users/${targetExternalUserId}/branch`,
      {
        method: "PUT",
        body,
      },
    );
  },
  createControlInvite(externalUserId: number, body: Record<string, unknown>) {
    return request<ControlBootstrapResponse["invites"]["items"][number]>("/control/invites", {
      method: "POST",
      body,
    });
  },
  createControlBranch(externalUserId: number, body: { name: string }) {
    return request<ControlBootstrapResponse["branches"][number]>("/control/branches", {
      method: "POST",
      body,
    });
  },
  moderateControlInviteActivation(
    externalUserId: number,
    activationId: number,
    action: "approve" | "reject",
  ) {
    return request<ControlBootstrapResponse["invite_activations"]["items"][number]>(
      `/control/invite-activations/${activationId}`,
      {
        method: "POST",
        body: { action },
      },
    );
  },
  createControlStaffingAction(externalUserId: number, body: Record<string, unknown>) {
    return request<ControlBootstrapResponse["staffing"]["items"][number]>("/control/staffing", {
      method: "POST",
      body,
    });
  },
  moderateControlStaffingAction(
    externalUserId: number,
    actionId: number,
    body: { action: "approve" | "reject"; comment?: string | null },
  ) {
    return request<ControlBootstrapResponse["staffing"]["items"][number]>(`/control/staffing/${actionId}`, {
      method: "POST",
      body,
    });
  },
  toggleControlFlag(externalUserId: number, code: string, enabled: boolean) {
    return request<ControlFeatureFlag>(`/control/flags/${code}`, {
      method: "PATCH",
      body: { enabled },
    });
  },
};
