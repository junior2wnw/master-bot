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
        label: "Сигналы рядом",
        title: "Открыть уведомления",
        body: "Непрочитанные сигналы стоит держать рядом с текущей работой, а не искать потом.",
        panelId: "notifications-list",
      }),
    );
  }

  if (ctx.bootstrap.workspace.active_estimates > 0 && !hasPanel(ctx.layout, ctx.panels, "estimates-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-estimates",
        label: "Сметы в фокус",
        title: "Открыть сметы",
        body: "Активные сметы лучше держать на виду, чтобы быстрее двигать работу к заказу.",
        panelId: "estimates-list",
      }),
    );
  }

  if (ctx.bootstrap.workspace.active_orders > 0 && !hasPanel(ctx.layout, ctx.panels, "orders-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-orders",
        label: "Заказы рядом",
        title: "Открыть заказы",
        body: "Если уже есть живая работа, ей нужен отдельный контекст рядом с рынком и профилем.",
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
        label: "Доверие профиля",
        title: "Доработать профиль",
        body: "Телефон и специализация нужны, чтобы сеть мастеров и отклики выглядели надёжно.",
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
        label: "Очередь решений",
        title: "Открыть согласования",
        body: "Очередь approvals не стоит прятать глубоко, если по ней уже есть хвост.",
        panelId: "approvals-queue",
      }),
    );
  }

  if (!recommendations.length && !hasPanel(ctx.layout, ctx.panels, "board-feed")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "general-board",
        label: "Вернуться к спросу",
        title: "Открыть доску",
        body: "Когда нет явного next step, безопаснее держать рядом живой спрос и не терять входящий рынок.",
        panelId: "board-feed",
      }),
    );
  }

  return {
    kind: "general",
    title: "Composer сам подсказывает следующий шаг",
    body: "Мы держим рядом только те окна, которые реально двигают текущую задачу, а не засоряют поверхность.",
    recommendations: recommendations.slice(0, 4),
  };
}

export function buildEstimateIntent(ctx: ContextShape, estimate: EstimateDetail): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  if (estimate.status === "draft" && estimate.capabilities.can_edit && !hasPanel(ctx.layout, ctx.panels, "catalog-browser")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-catalog",
        label: "Каталог рядом",
        title: "Добавлять позиции без лишнего хождения",
        body: "Черновик сметы лучше собирать с открытым каталогом рядом, чтобы не прыгать между режимами.",
        panelId: "catalog-browser",
      }),
    );
  }

  if (estimate.status === "approved" && ctx.bootstrap.capabilities.can_create_order && !hasPanel(ctx.layout, ctx.panels, "orders-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-orders",
        label: "Перевести в заказ",
        title: "Держать заказы рядом со сметой",
        body: "Согласованную смету логично сразу переводить в работу, не теряя контекста стоимости.",
        panelId: "orders-list",
      }),
    );
  }

  if (estimate.status === "client_review" && !hasPanel(ctx.layout, ctx.panels, "notifications-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "estimate-signals",
        label: "Ответ клиента",
        title: "Открыть сигналы рядом",
        body: "Когда смета у клиента, рядом полезно держать уведомления, чтобы не пропустить ответ или замечание.",
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
        label: "Очередь approvals",
        title: "Подтянуть согласования",
        body: "Если по скидкам и решениям уже есть хвост, держите очередь рядом со сметой.",
        panelId: "approvals-queue",
      }),
    );
  }

  return {
    kind: "estimate",
    title: `Смета #${estimate.id} в фокусе`,
    body: "Composer собирает вокруг сметы только те окна, которые помогают довести её до согласования и заказа.",
    recommendations: recommendations.slice(0, 4),
  };
}

export function buildOrderIntent(ctx: ContextShape, order: OrderDetail): ComposerIntentSurface {
  const recommendations: ComposerRecommendation[] = [];

  if (order.estimate?.id && !hasPanel(ctx.layout, ctx.panels, "estimates-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "order-estimate",
        label: "Смета рядом",
        title: "Держать смету рядом с заказом",
        body: "Так проще сверять состав работ, сумму и переходить к изменениям без потери контекста.",
        panelId: "estimates-list",
        estimateId: order.estimate.id,
      }),
    );
  }

  if (ctx.bootstrap.notifications.unread > 0 && !hasPanel(ctx.layout, ctx.panels, "notifications-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "order-signals",
        label: "Сигналы рядом",
        title: "Открыть уведомления рядом с заказом",
        body: "У активной работы сигналы и статусы лучше держать рядом, чем вспоминать о них позже.",
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
        label: "Репутация мастеров",
        title: "Открыть сеть мастеров",
        body: "После завершения сделки полезно держать под рукой публичный контекст мастеров и доверия.",
        panelId: "network-directory",
      }),
    );
  }

  return {
    kind: "order",
    title: `Заказ #${order.id} в фокусе`,
    body: "Вокруг активного заказа мы подбираем только окна исполнения: смету, сигналы и доверительный контекст.",
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
        label: "Витрина рядом",
        title: "Открыть сеть мастеров рядом",
        body: "Так проще сразу видеть, как профиль выглядит в живом рынке, а не только в форме.",
        panelId: "network-directory",
      }),
    );
  }

  if ((!profile?.phone || !profile?.specialization) && !hasPanel(ctx.layout, ctx.panels, "board-feed")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: "profile-board",
        label: "Спрос рядом",
        title: "Держать рынок рядом с профилем",
        body: "Когда профиль ещё сырой, полезно видеть спрос и понимать, под какие задачи его довести.",
        panelId: "board-feed",
      }),
    );
  }

  return {
    kind: "profile",
    title: "Профиль как рабочая опора",
    body: "Профиль нужен не сам по себе, а как точка доверия между спросом, сетью мастеров и текущей работой.",
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
        label: "Заказ рядом",
        title: "Открыть заказ рядом с уведомлениями",
        body: "Так уведомление не теряется после перехода, а живёт рядом с исполнением.",
        panelId: "orders-list",
        workflowCallback: callback,
      }),
    );
  }
  if (callback.startsWith("est_") && !hasPanel(ctx.layout, ctx.panels, "estimates-list")) {
    recommendations.push(
      openRecommendation(ctx, {
        id: `notification-estimate-${notification.id}`,
        label: "Смета рядом",
        title: "Открыть смету рядом с уведомлениями",
        body: "Сигналы по смете удобнее разбирать, когда сам документ открыт рядом.",
        panelId: "estimates-list",
        workflowCallback: callback,
      }),
    );
  }

  return {
    kind: "notification",
    title: notification.title,
    body: "При переходе из уведомления composer старается не терять сам источник сигнала и соседний рабочий модуль.",
    recommendations: recommendations.slice(0, 3),
  };
}
