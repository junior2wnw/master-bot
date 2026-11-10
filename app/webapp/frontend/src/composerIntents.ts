import type {
  BootstrapResponse,
  ComposerAxis,
  EstimateDetail,
  LayoutPayload,
  NotificationItem,
  OrderDetail,
  PanelMeta,
  ProfileResponse,
} from "./types";
import { findComposerWindowByPanel } from "./windowLayout";

export type ComposerRecommendation = {
  id: string;
  label: string;
  title: string;
  body: string;
  panelId: string;
  mode?: "focus-or-add" | "replace";
  axis?: ComposerAxis;
  workflowCallback?: string;
  estimateId?: number;
  orderId?: number;
  profileScenario?: boolean;
};

export type ComposerIntentSurface = {
  kind: "general" | "estimate" | "order" | "profile" | "notification";
  title: string;
  body: string;
  recommendations: ComposerRecommendation[];
};

type ContextShape = {
  layout: LayoutPayload;
  panels: PanelMeta[];
  bootstrap: BootstrapResponse;
  splitAxis: ComposerAxis;
};

function hasPanel(layout: LayoutPayload, panels: PanelMeta[], panelId: string): boolean {
  return Boolean(findComposerWindowByPanel(layout, panels, panelId));
}

function openRecommendation(
  ctx: ContextShape,
  recommendation: Omit<ComposerRecommendation, "axis">,
): ComposerRecommendation {
  return {
    ...recommendation,
    axis: ctx.splitAxis,
  };
}

export function buildGeneralIntent(ctx: ContextShape): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  if (ctx.bootstrap.notifications.unread > 0 && !hasPanel(ctx.layout, ctx.panels, "notifications-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-notifications",
        label: "Сигналы",
        title: "Открыть уведомления",
        body: "Держите уведомления рядом с работой.",
        panelId: "notifications-list",
      }),
    );
  }

  if (ctx.bootstrap.workspace.active_estimates > 0 && !hasPanel(ctx.layout, ctx.panels, "estimates-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-estimates",
        label: "Сметы",
        title: "Открыть сметы",
        body: "Откройте активные сметы рядом.",
        panelId: "estimates-list",
      }),
    );
  }

  if (ctx.bootstrap.workspace.active_orders > 0 && !hasPanel(ctx.layout, ctx.panels, "orders-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-orders",
        label: "Заказы",
        title: "Открыть заказы",
        body: "Держите активные заказы под рукой.",
        panelId: "orders-list",
      }),
    );
  }

  if (
    ctx.bootstrap.capabilities.can_publish_master_profile &&
    (!ctx.bootstrap.profile.phone || !ctx.bootstrap.profile.specialization) &&
    !hasPanel(ctx.layout, ctx.panels, "profile-card")
  ) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-profile",
        label: "Профиль",
        title: "Доработать профиль",
        body: "Заполните профиль для откликов и сети.",
        panelId: "profile-card",
        profileScenario: true,
      }),
    );
  }

  if (
    ctx.bootstrap.capabilities.can_process_approvals &&
    ctx.bootstrap.workspace.pending_approvals > 0 &&
    !hasPanel(ctx.layout, ctx.panels, "approvals-queue")
  ) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-approvals",
        label: "Согласования",
        title: "Открыть согласования",
        body: "Есть решения, которые ждут вас.",
        panelId: "approvals-queue",
      }),
    );
  }

  if (!recommendations.length && !hasPanel(ctx.layout, ctx.panels, "board-feed")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-board",
        label: "Доска",
        title: "Открыть доску",
        body: "Вернитесь к новым заявкам.",
        panelId: "board-feed",
      }),
    );
  }

  return {
    kind: "general",
    title: "Следующий шаг уже рядом",
    body: "Только нужные окна и действия.",
    recommendations: recommendations.slice(0, 4),
  };
}

export function buildEstimateIntent(ctx: ContextShape, estimate: EstimateDetail): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  if (estimate.status === "draft" && estimate.capabilities.can_edit && !hasPanel(ctx.layout, ctx.panels, "catalog-browser")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-catalog",
        label: "Каталог",
        title: "Добавлять позиции без лишнего хождения",
        body: "Добавляйте позиции прямо рядом со сметой.",
        panelId: "catalog-browser",
      }),
    );
  }

  if (estimate.status === "approved" && ctx.bootstrap.capabilities.can_create_order && !hasPanel(ctx.layout, ctx.panels, "orders-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-orders",
        label: "В заказ",
        title: "Держать заказы рядом со сметой",
        body: "Переведите согласованную смету в работу.",
        panelId: "orders-list",
      }),
    );
  }

  if (estimate.status === "client_review" && !hasPanel(ctx.layout, ctx.panels, "notifications-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-signals",
        label: "Ответ",
        title: "Открыть сигналы рядом",
        body: "Проверьте ответ клиента рядом со сметой.",
        panelId: "notifications-list",
      }),
    );
  }

  if (
    ctx.bootstrap.capabilities.can_process_approvals &&
    ctx.bootstrap.workspace.pending_approvals > 0 &&
    !hasPanel(ctx.layout, ctx.panels, "approvals-queue")
  ) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-approvals",
        label: "Согласования",
        title: "Подтянуть согласования",
        body: "Рядом есть очередь решений.",
        panelId: "approvals-queue",
      }),
    );
  }

  return {
    kind: "estimate",
    title: `Смета #${estimate.id}`,
    body: "Рядом только нужные шаги по смете.",
    recommendations: recommendations.slice(0, 4),
  };
}

export function buildOrderIntent(ctx: ContextShape, order: OrderDetail): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  if (order.estimate?.id && !hasPanel(ctx.layout, ctx.panels, "estimates-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "order-estimate",
        label: "Смета",
        title: "Держать смету рядом с заказом",
        body: "Сверяйте состав и сумму без лишних переходов.",
        panelId: "estimates-list",
        estimateId: order.estimate.id,
      }),
    );
  }

  if (ctx.bootstrap.notifications.unread > 0 && !hasPanel(ctx.layout, ctx.panels, "notifications-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "order-signals",
        label: "Сигналы",
        title: "Открыть уведомления рядом с заказом",
        body: "Статусы и события рядом с заказом.",
        panelId: "notifications-list",
      }),
    );
  }

  if (
    ctx.bootstrap.capabilities.can_publish_master_profile &&
    order.review.can_create &&
    !hasPanel(ctx.layout, ctx.panels, "network-directory")
  ) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "order-network",
        label: "Мастера",
        title: "Открыть сеть мастеров",
        body: "Откройте сеть мастеров и отзывы.",
        panelId: "network-directory",
      }),
    );
  }

  return {
    kind: "order",
    title: `Заказ #${order.id}`,
    body: "Рядом только исполнение и статусы.",
    recommendations: recommendations.slice(0, 4),
  };
}

export function buildProfileIntent(
  ctx: ContextShape,
  profile: Pick<ProfileResponse, "phone" | "specialization"> | null,
): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  if (ctx.bootstrap.capabilities.can_publish_master_profile && !hasPanel(ctx.layout, ctx.panels, "network-directory")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "profile-network",
        label: "Витрина",
        title: "Открыть сеть мастеров рядом",
        body: "Посмотрите, как профиль выглядит в сети.",
        panelId: "network-directory",
      }),
    );
  }

  if ((!profile?.phone || !profile?.specialization) && !hasPanel(ctx.layout, ctx.panels, "board-feed")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "profile-board",
        label: "Спрос",
        title: "Держать рынок рядом с профилем",
        body: "Посмотрите спрос и подтяните профиль под него.",
        panelId: "board-feed",
      }),
    );
  }

  return {
    kind: "profile",
    title: "Профиль",
    body: "Заполните главное и смотрите рынок рядом.",
    recommendations: recommendations.slice(0, 4),
  };
}

export function buildNotificationIntent(ctx: ContextShape, notification: NotificationItem): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  const callback = notification.target_callback || "";
  if (callback.startsWith("order_") && !hasPanel(ctx.layout, ctx.panels, "orders-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: `notification-order-${notification.id}`,
        label: "Заказ",
        title: "Открыть заказ рядом с уведомлениями",
        body: "Откройте заказ рядом с уведомлением.",
        panelId: "orders-list",
        workflowCallback: callback,
      }),
    );
  }
  if (callback.startsWith("est_") && !hasPanel(ctx.layout, ctx.panels, "estimates-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: `notification-estimate-${notification.id}`,
        label: "Смета",
        title: "Открыть смету рядом с уведомлениями",
        body: "Откройте смету рядом с уведомлением.",
        panelId: "estimates-list",
        workflowCallback: callback,
      }),
    );
  }

  return {
    kind: "notification",
    title: notification.title,
    body: "Сигнал и рабочий модуль остаются рядом.",
    recommendations: recommendations.slice(0, 3),
  };
}
