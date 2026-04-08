export type Platform = "max" | "telegram";
export type PaneId = "top" | "bottom";

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
  roles: string[];
  active_role: string | null;
  active_role_label: string;
  max_role: string | null;
  max_role_label: string;
  can_switch_role: boolean;
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
}

export interface BoardResponse {
  items: JobPost[];
  meta: { limit: number; offset: number };
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
  created_at: string | null;
  is_unread: boolean;
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
    can_publish_master_profile: boolean;
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

export interface PublicProfileResponse extends MasterCard {
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
