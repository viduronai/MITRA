// Mirrors services/core schemas/leads.py and schemas/webhooks.py.

export const LEAD_SOURCES = [
  "meta",
  "website_form",
  "google_sheets",
  "google_forms",
  "google_ads",
  "indiamart",
  "justdial",
  "zapier",
  "api",
] as const;
export type LeadSourceKind = (typeof LEAD_SOURCES)[number];

export type LeadStatus =
  | "queued"
  | "scheduled"
  | "duplicate"
  | "not_called"
  | "blocked"
  | "no_consent"
  | "no_attestation"
  | "no_employee"
  | "failed";

export interface IntakeUrls {
  generic: string;
  form: string;
  google_ads: string;
  indiamart: string;
  justdial: string;
  meta_webhook: string;
}

export interface LeadSource {
  kind: LeadSourceKind;
  connected: boolean;
  enabled: boolean;
  auto_call: boolean;
  call_delay_seconds: number;
  heads_up: boolean;
  employee_id: string | null;
  external_id: string | null;
  credential_hint: string | null;
  last_lead_at: string | null;
  last_pulled_at: string | null;
  lead_count: number;
  last_error: string | null;
  simulated: boolean;
  consent_policy: ConsentPolicy;
  attested_at: string | null;
  attested_by: string | null;
}

/** Lead consent policy (docs/08): how each source proves people asked to be contacted. */
export type ConsentPolicy = "form_checkbox" | "portal_enquiry" | "owner_attestation";
export type ConsentLang = "en" | "hi" | "te";

export interface LeadSetup {
  enabled: boolean;
  slug: string | null;
  secret_hint: string | null;
  secret: string | null;
  rotated_at: string | null;
  previous_valid_until: string | null;
  dedupe_minutes: number;
  urls: IntakeUrls | null;
  sources: LeadSource[];
  consent_version: string;
  consent_texts: Record<ConsentLang, string>;
  attestation_texts: Record<ConsentLang, string>;
}

export interface LeadSourcePatch {
  enabled?: boolean;
  auto_call?: boolean;
  call_delay_seconds?: number;
  heads_up?: boolean;
  employee_id?: string | null;
  external_id?: string | null;
  credential?: string | null;
  consent_attested?: boolean;
  attestation_lang?: ConsentLang;
}

export interface Lead {
  id: string;
  source: LeadSourceKind;
  source_detail: string | null;
  name: string | null;
  phone_last4: string;
  fields: Record<string, string>;
  status: LeadStatus;
  reasons: string[];
  reason_text: string[];
  employee_id: string | null;
  call_at: string | null;
  received_at: string;
  duplicate_of: string | null;
}

export interface PullResult {
  fetched: number;
  created: number;
  duplicates: number;
  error: string | null;
}

export const WEBHOOK_EVENTS = ["call.ended", "lead.created", "campaign.finished", "payment.paid", "payment.failed"] as const;
export type WebhookEvent = (typeof WEBHOOK_EVENTS)[number];

export interface Webhook {
  id: string;
  url: string;
  description: string | null;
  events: WebhookEvent[];
  secret_hint: string;
  secret: string | null;
  headers: Record<string, string>;
  enabled: boolean;
  consecutive_failures: number;
  last_delivery_at: string | null;
  last_delivery_ok: boolean | null;
  created_at: string;
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event_id: string;
  event: string;
  status: "pending" | "succeeded" | "failed";
  attempts: number;
  next_attempt_at: string | null;
  last_attempt_at: string | null;
  response_status: number | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface WebhookInput {
  url: string;
  events: WebhookEvent[];
  description?: string | null;
  headers?: Record<string, string>;
}
