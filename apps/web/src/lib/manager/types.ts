/** Shapes returned by core's /v1/approvals and /v1/manager endpoints. */

export type ApprovalStatus = "pending" | "approved" | "declined" | "expired" | "cancelled";
export type Locale = "en" | "hi" | "te";

export interface Approval {
  id: string;
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
  version: number;
  status: ApprovalStatus;
  requested_by: string;
  default_action: "approve" | "decline" | null;
  expires_at: string | null;
  decided_by: string | null;
  decided_via: "app" | "whatsapp" | "timeout" | null;
  decided_at: string | null;
  decision_note: string | null;
  apply_error: string | null;
  created_at: string;
  /** Payload fields the owner may change before approving; null = any field. */
  editable: string[] | null;
}

export interface ApprovalEvent {
  id: string;
  event: string;
  version: number;
  actor_user_id: string | null;
  via: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface ApprovalRule {
  kind: "discount" | "refund" | "cancellation" | "big_booking" | "list_call" | "payment_link";
  enabled: boolean;
  threshold: number | null;
  timeout_minutes: number | null;
  default_action: "approve" | "decline" | null;
}

export interface ConfirmCard {
  type: "confirm";
  approval_id: string;
  version: number;
  kind: string;
  status?: ApprovalStatus;
  apply_error?: string | null;
}

export interface LinksCard {
  links: { label: string; href: string }[];
}

export interface ThreadMessage {
  id: string;
  role: "owner" | "mitra";
  channel: "app" | "whatsapp";
  text: string;
  card: ConfirmCard | LinksCard | null;
  created_at: string;
}

export interface ManagerSettings {
  report_enabled: boolean;
  report_time: string;
  language: Locale | null;
  report_user_ids: string[];
  alert_user_ids: string[];
  alert_kinds: string[];
  people: { user_id: string; name: string | null; role: string; phone_last4: string }[];
}

export type ManagerSettingsPatch = Partial<
  Pick<ManagerSettings, "report_enabled" | "report_time" | "language" | "report_user_ids" | "alert_user_ids" | "alert_kinds">
>;

export interface WaMessage {
  id: string;
  direction: "in" | "out";
  kind: string;
  purpose: string;
  user_id: string | null;
  phone_last4: string;
  body: string;
  template: string | null;
  /** Reply buttons carry an id (payload); template URL buttons carry the full url. */
  buttons: { id?: string; url?: string; title: string }[];
  ref: Record<string, unknown>;
  provider_message_id: string | null;
  status: string;
  created_at: string;
}

export const ALERT_KINDS = ["hot_lead", "angry", "vip", "payment_failed", "campaign_paused"] as const;
export type AlertKind = (typeof ALERT_KINDS)[number];
