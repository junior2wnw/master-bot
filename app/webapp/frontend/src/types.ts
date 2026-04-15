export type Platform = "max" | "telegram";
export type PaneId = "top" | "bottom";

export interface RoleOption {
  code: string;
  label: string;
}

export interface RoleModeResponse {
  direct_roles: string[];
  roles: string[];
  active_role: string | null;
  active_role_label: string;
  max_role: string | null;
  max_role_label: string;
  role_override: string | null;
  is_role_switched: boolean;
  can_switch_role: boolean;
  available_roles: RoleOption[];
}

export interface AuthResponse {
  user_id: number;
  user_ref: number;
  telegram_id: number;
  platform: Platform;
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  expires_at: number;
  name: string;
  is_active: boolean;
  direct_roles: string[];
  roles: string[];
  active_role: string | null;
  active_role_label: string;
  max_role: string | null;
  max_role_label: string;
  role_override: string | null;
  can_switch_role: boolean;
  available_roles: RoleOption[];
}

export interface PanelMeta {
  id: string;
  title: string;
  subtitle: string;
  group: string;
  icon: string;
}

export interface PresetMeta {
  id: string;
  title: string;
  subtitle: string;
}

export type ComposerAxis = "horizontal" | "vertical";

export interface ComposerWindowNode {
  id: string;
  kind: "window";
  panel_id: string;
}

export interface ComposerSplitNode {
  id: string;
  kind: "split";
  axis: ComposerAxis;
  children: ComposerNode[];
  sizes: number[];
}

export type ComposerNode = ComposerWindowNode | ComposerSplitNode;

export interface ComposerLayout {
  root: ComposerNode;
  focus_window_id: string;
  spotlight_window_id: string | null;
}

export interface LayoutPayload {
  version: number;
  preset: string;
  ratio: number;
  panes: {
    top: string;
    bottom: string;
  };
  chrome: {
    density: "compact" | "cozy";
    dock_compact: boolean;
  };
  composer?: ComposerLayout;
}

export interface JobPost {
  id: number;
  title: string;
  description: string;
  city: string | null;
  urgency: "normal" | "urgent" | "asap";
  status: string;
  budget: {
    from: number | null;
    to: number | null;
  } | null;
  desired_start_label: string | null;
  preferred_contact: string | null;
  created_at: string | null;
  updated_at: string | null;
  response_count: number;
  has_responded: boolean;
  is_owner: boolean;
  can_respond: boolean;
  author: {
    id: number;
    external_id: number;
    name: string;
  };
}

export interface MasterCard {
  user_id: number;
  external_user_id: number;
  name: string;
  username: string | null;
  title: string;
  bio: string;
  city: string;
  experience_years: number;
  hourly_rate_from: number | null;
  hourly_rate_to: number | null;
  availability_status: string;
  verification_status: string;
  rating_average: number;
  rating_count: number;
  completed_jobs: number;
  active_jobs: number;
  skills: string[];
  portfolio: Array<{ title: string; url: string; kind: string }>;
  accent_color: string;
  is_public: boolean;
  tier: string;
  specialization: string;
  response_time_label: string;
  trust_badges: TrustBadge[];
}

export interface BoardResponse {
  items: JobPost[];
  meta: { limit: number; offset: number };
}

export interface JobPostResponseItem {
  id: number;
  job_post_id: number;
  status: string;
  message: string;
  price_offer: number | null;
  eta_label: string | null;
  created_at: string | null;
  responder: {
    id: number;
    external_id: number;
    name: string;
    username: string | null;
  };
}

export interface JobPostResponseList {
  post: JobPost;
  items: JobPostResponseItem[];
  meta: {
    count: number;
  };
}

export interface NetworkResponse {
  items: MasterCard[];
  meta: { limit: number; offset: number };
}

export interface EstimateSummary {
  id: number;
  status: string;
  version: number;
  total: number;
  discount: number;
  final: number;
  client_id: number | null;
  master_id: number | null;
  created_at: string | null;
}

export interface EstimateDetail extends EstimateSummary {
  capabilities: Record<string, boolean>;
  created_at?: string | null;
  updated_at?: string | null;
  items: Array<{
    id: number;
    service_item_id: number;
    name: string;
    unit: string;
    quantity: number;
    unit_price: number;
    coefficients: Record<string, number> | null;
    subtotal: number;
  }>;
}

export interface OrderSummary {
  id: number;
  status: string;
  address: string | null;
  urgency: string;
  estimate_id: number | null;
  created_at: string | null;
}

export interface NotificationItem {
  id: number;
  event_type: string;
  title: string;
  body: string;
  status: string;
  entity_type?: string | null;
  entity_id?: number | null;
  created_at: string | null;
  is_unread: boolean;
  target_callback?: string | null;
  target_label?: string | null;
}

export interface SuggestionTask {
  id: string;
  title: string;
  description: string;
}

export interface BootstrapResponse {
  layout: LayoutPayload;
  presets: PresetMeta[];
  panels: PanelMeta[];
  capabilities: {
    can_post_jobs: boolean;
    can_respond_to_jobs: boolean;
    can_create_estimate: boolean;
    can_create_order: boolean;
    can_publish_master_profile: boolean;
    can_process_approvals: boolean;
    can_view_control: boolean;
  };
  workspace: {
    name: string;
    roles: string[];
    primary_role: string | null;
    active_role_label: string;
    max_role: string | null;
    max_role_label: string;
    can_switch_role: boolean;
    active_estimates: number;
    active_orders: number;
    pending_approvals: number;
    unread_notifications: number;
    completed_orders?: number;
    total_earned?: number;
    action_items: Array<{ icon: string; title: string; body: string; callback: string }>;
    recent_notifications: NotificationItem[];
    onboarding: SuggestionTask[];
  };
  board: {
    items: JobPost[];
    total: number;
  };
  network: {
    items: MasterCard[];
    total: number;
  };
  profile: {
    name: string;
    external_user_id: number;
    roles: string[];
    phone: string;
    specialization: string;
  };
  notifications: {
    unread: number;
  };
}

export interface CatalogItem {
  id: number;
  name: string;
  unit: string;
  price: number;
  price_min: number;
  price_max: number;
}

export interface ProfileResponse {
  user_id: number;
  full_name: string;
  phone: string;
  email: string;
  telegram_username: string;
  company_name: string;
  inn: string;
  address: string;
  specialization: string;
  bank_name: string;
  bik: string;
  correspondent_account: string;
  settlement_account: string;
  card_number: string;
  sbp_phone: string;
  payment_recipient: string;
  roles: string[];
  active_role: string | null;
  active_role_label: string;
  max_role: string | null;
  max_role_label: string;
}

export interface TrustBadge {
  code: string;
  label: string;
  tone: string;
}

export interface MasterReviewItem {
  id: number;
  order_id: number;
  rating: number;
  headline: string;
  body: string;
  is_public: boolean;
  created_at: string | null;
  author: {
    id: number;
    name: string;
    external_user_id: number | null;
  };
}

export interface MasterProfileResponse extends MasterCard {
  reviews: MasterReviewItem[];
}

export interface PublicProfileResponse extends MasterProfileResponse {
  edit: {
    headline: string;
    bio: string;
    city: string;
    experience_years: number;
    hourly_rate_from: number | null;
    hourly_rate_to: number | null;
    availability_status: string;
    response_time_label: string;
    skills: string[];
    portfolio: Array<{ title: string; url: string; kind: string }>;
    is_public: boolean;
    accent_color: string;
  };
}

export interface ControlBranch {
  id: number;
  name: string;
  is_active: boolean;
  senior_master_id: number | null;
  member_count: number;
}

export interface ControlBranchMemberPreview {
  user_id: number;
  external_user_id: number | null;
  name: string;
  is_senior: boolean;
  is_active: boolean;
  completed_orders: number;
}

export interface ControlBranchOverview {
  id: number;
  name: string;
  is_active: boolean;
  senior_master_id: number | null;
  senior_name: string | null;
  member_count: number;
  active_master_count: number;
  estimate_count: number;
  completed_orders: number;
  revenue: number;
  senior_share: number;
  members: ControlBranchMemberPreview[];
}

export interface ControlUser {
  user_id: number;
  external_user_id: number;
  name: string;
  username: string | null;
  roles: string[];
  active_role_label: string;
  max_role_label: string;
  is_active: boolean;
  branches: Array<{
    id: number;
    name: string;
    is_senior: boolean;
    is_active: boolean;
  }>;
  can_manage: boolean;
}

export interface ControlInvite {
  id: number;
  code: string;
  role_code: string;
  branch_id: number | null;
  branch_name: string | null;
  profession_id: number | null;
  max_uses: number;
  used_count: number;
  requires_approval: boolean;
  expires_at: string | null;
  is_active: boolean;
  is_exhausted: boolean;
  is_expired: boolean;
  created_at: string | null;
  creator: {
    id: number;
    name: string;
    external_user_id: number;
  } | null;
}

export interface ControlInviteActivation {
  id: number;
  status: string;
  activated_at: string | null;
  invite: {
    id: number;
    code: string;
    role_code: string;
    branch_name: string | null;
    requires_approval: boolean;
  } | null;
  user: {
    id: number;
    name: string;
    external_user_id: number;
  } | null;
  approver: {
    id: number;
    name: string;
    external_user_id: number;
  } | null;
}

export interface ControlStaffingAction {
  id: number;
  action_type: string;
  status: string;
  status_label: string;
  reason: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
  resolved_at: string | null;
  target: {
    id: number;
    name: string;
    external_user_id: number;
  } | null;
  initiator: {
    id: number;
    name: string;
    external_user_id: number;
  } | null;
  approver: {
    id: number;
    name: string;
    external_user_id: number;
  } | null;
}

export interface ControlFeatureFlag {
  code: string;
  name: string;
  description: string | null;
  module: string | null;
  enabled: boolean;
}

export interface ControlInsightCommission {
  id: number;
  order_id: number | null;
  gross_total: number;
  platform_fee: number;
  master_net: number;
  calculated_at: string | null;
}

export interface ControlInsightMaster {
  user_id: number;
  external_user_id: number | null;
  name: string;
  order_count: number;
  revenue: number;
}

export interface ControlInsights {
  overview: {
    users: number;
    masters: number;
    estimates: number;
    orders: number;
    gross: number;
    platform_net: number;
  };
  finance: {
    gross: number;
    platform_fee: number;
    senior_share: number;
    admin_share: number;
    platform_net: number;
    master_net: number;
    discounts_total: number;
    recent_commissions: ControlInsightCommission[];
  };
  funnel: Record<string, number>;
  masters: ControlInsightMaster[];
  discounts: {
    total_requests: number;
    approved: number;
    rejected: number;
    pending: number;
    total_amount: number;
    approval_rate: number;
  };
  settings: {
    platform_name: string;
    platform_operator_name: string;
    platform_fee_pct: number;
    senior_master_share_pct: number;
    admin_share_pct: number;
    default_city: string;
    default_region: string;
    ai_provider: string;
    app_env: string;
    webapp_url: string;
  };
}

export interface ControlListMeta {
  limit: number;
  offset: number;
  count: number;
}

export interface ControlBootstrapResponse {
  capabilities: {
    can_view_team: boolean;
    can_manage_users: boolean;
    can_manage_branches: boolean;
    can_create_invites: boolean;
    can_moderate_invites: boolean;
    can_initiate_staffing: boolean;
    can_approve_staffing: boolean;
    can_manage_flags: boolean;
  };
  ui: {
    invite_role_options: RoleOption[];
    role_management_options: RoleOption[];
    staffing_action_options: RoleOption[];
  };
  branches: ControlBranch[];
  branch_overview: {
    items: ControlBranchOverview[];
    meta: {
      count: number;
    };
  };
  users: {
    items: ControlUser[];
    meta: ControlListMeta;
  };
  invites: {
    items: ControlInvite[];
    meta: ControlListMeta;
  };
  invite_activations: {
    items: ControlInviteActivation[];
    meta: ControlListMeta;
  };
  staffing: {
    items: ControlStaffingAction[];
    meta: ControlListMeta;
  };
  flags: ControlFeatureFlag[];
  insights: ControlInsights | null;
}

export interface ApprovalItem {
  id: number;
  estimate_id: number;
  type: string;
  value: number;
  status: string;
  created_at: string | null;
}

export interface AnalyticsOverview {
  users: number;
  masters: number;
  estimates: number;
  orders: number;
  gross: number;
  platform_fee: number;
  senior_share: number;
  admin_share: number;
  platform_net: number;
  funnel: Record<string, number>;
}

export interface OrderDetail {
  id: number;
  status: string;
  client_id: number | null;
  master_id: number | null;
  address: string | null;
  urgency: string;
  notes: string | null;
  cancellation_reason: string | null;
  client_name: string | null;
  master_name: string | null;
  payment_status: string | null;
  created_at: string | null;
  capabilities: Record<string, boolean>;
  cancel_reasons: RoleOption[];
  estimate: {
    id: number;
    version: number;
    total: number;
    final: number;
    items: Array<{
      name: string;
      quantity: number;
      unit_price: number;
      subtotal: number;
    }>;
  } | null;
  history: Array<{
    from: string | null;
    to: string;
    reason: string | null;
    at: string | null;
  }>;
  review: {
    can_create: boolean;
    item: MasterReviewItem | null;
  };
}

export interface OrderPaymentInfo {
  order_id: number;
  amount: number;
  phone: string;
  bank_name: string;
  recipient: string;
  payment_status: string;
  qr_data: string | null;
}

export interface EstimateQrPayload {
  qr_data: string | null;
  qr_image: string | null;
  amount: number | null;
  qr_mode: string;
  has_qr: boolean;
  has_qr_image: boolean;
  recipient: string | null;
  bank: string | null;
  account: string | null;
  bik: string | null;
  correspondent_account: string | null;
  card: string | null;
  sbp_phone: string | null;
  inn: string | null;
  has_bank_qr: boolean;
  has_sbp_phone_qr: boolean;
  has_bank_qr_details: boolean;
  has_sbp_phone_details: boolean;
  missing_bank_fields: string[];
  fallback_notice: string | null;
}
