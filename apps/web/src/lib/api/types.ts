/**
 * Types for the Mitra core API (services/core, base path /v1).
 * Written by hand from docs/api/step2-onboarding-contract.md and the Step 1
 * schemas. Keep in sync with the contract file, not with the UI.
 */

export type Uuid = string;
export type IsoDateTime = string;

export type Locale = "en" | "te" | "hi";
export type Industry = "clinic" | "real_estate" | "education" | "other";
export type MemberRole = "owner" | "manager" | "staff" | "agency_admin";
export type RoleTemplateId = "receptionist" | "lead_caller" | "reminder_caller" | "payment_caller";
export type VoiceTier = "smart" | "natural" | "signature";
export type EmployeeStatus = "working" | "paused" | "training";

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}

// ---------- Auth ----------

export interface OtpRequestOut {
  request_id: string;
  expires_in: number;
  resend_in: number;
  /** Present only when the API runs with env=local. */
  dev_code?: string;
}

export interface UserSummary {
  id: Uuid;
  phone_last4: string;
  name: string | null;
  preferred_locale: Locale;
}

export interface Membership {
  business_id: Uuid;
  business_name: string;
  role: MemberRole;
}

export interface TokenOut {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface OtpVerifyOut extends TokenOut {
  user: UserSummary;
  memberships: Membership[];
}

export interface MeOut {
  user: {
    id: Uuid;
    phone_e164: string;
    name: string | null;
    email: string | null;
    preferred_locale: Locale;
  };
  memberships: Membership[];
}

// ---------- Businesses ----------

export interface BusinessIn {
  name: string;
  industry: Industry;
  city?: string | null;
  languages: Locale[];
  timezone?: string;
}

export interface Business {
  id: Uuid;
  agency_id: Uuid | null;
  name: string;
  industry: Industry;
  city: string | null;
  languages: Locale[];
  timezone: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface BusinessCreatedOut {
  business: Business;
  membership: Membership;
  /** Token scoped to the new business (Step 2 addition). */
  access_token: string;
  expires_in?: number;
}

// ---------- Employees ----------

export interface TimeRange {
  start: string;
  end: string;
}

export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type WorkingHours = Partial<Record<Weekday, TimeRange[] | null>>;

export interface Behaviour {
  ask_for: string[];
  never_say: string[];
  transfer_when: string[];
}

export interface Employee {
  id: Uuid;
  business_id: Uuid;
  name: string;
  role_template: RoleTemplateId;
  voice_tier: VoiceTier;
  status: EmployeeStatus;
  languages: Locale[];
  working_hours: WorkingHours | null;
  voice_id: string | null;
  greeting: string | null;
  behaviour: Behaviour | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface EmployeeIn {
  name: string;
  role_template: RoleTemplateId;
  voice_tier?: VoiceTier;
  languages: Locale[];
  working_hours?: WorkingHours | null;
}

export interface EmployeePatch {
  name?: string;
  voice_tier?: VoiceTier;
  status?: EmployeeStatus;
  languages?: Locale[];
  working_hours?: WorkingHours | null;
  voice_id?: string;
  greeting?: string;
  behaviour?: Behaviour;
}

// ---------- Catalog ----------

export interface RoleTemplate {
  id: RoleTemplateId;
  name: string;
  description: string;
  default_for: Industry[];
  sample_audio_url: string | null;
}

export interface CatalogVoice {
  id: string;
  name: string;
  personality: string;
  languages: Locale[];
  dialect: string | null;
  gender: "female" | "male" | string;
  tier: VoiceTier;
  sample_text: string;
  sample_audio_url: string | null;
}

export interface Rate {
  tier: VoiceTier;
  inr_per_min: number;
}

// ---------- Knowledge ("What they know") ----------

export type FactCategory = "services" | "prices" | "timings" | "location" | "contact" | "faq" | "policy";
export type SourceStatus = "processing" | "ready" | "failed";

export type SourceIn = { type: "url"; url: string } | { type: "text"; text: string };

export interface KnowledgeSource {
  id: Uuid;
  type: "url" | "text";
  status: SourceStatus;
  title: string | null;
  created_at: IsoDateTime;
  error?: string | null;
}

export interface Fact {
  id: Uuid;
  category: FactCategory;
  key: string;
  value: string;
  source_id: Uuid | null;
  status: "suggested" | "confirmed";
}

export interface Gap {
  category: FactCategory;
  key: string;
  question: string;
  /** "call": a caller asked and the employee had no answer (unknown-question inbox). */
  source?: "checklist" | "call";
  call_id?: Uuid | null;
}

// ---------- Test calls ----------

export type TestCallStatus = "queued" | "ringing" | "connected" | "completed";

export interface TranscriptLine {
  speaker: "employee" | "caller";
  text: string;
  at_ms: number;
}

export interface TestCall {
  id: Uuid;
  status: TestCallStatus;
  simulated: boolean;
  transcript?: TranscriptLine[];
  summary?: string | null;
}

export interface CorrectionOut {
  id: Uuid;
  applied_to: "knowledge" | "behaviour";
  change_summary: string;
}

// ---------- Onboarding ----------

export type OnboardingStepKey = "business" | "role" | "teach" | "voice" | "test_call" | "go_live";

export interface OnboardingProgress {
  steps: { key: OnboardingStepKey; done: boolean }[];
  percent: number;
  next: OnboardingStepKey | null;
}

// ---------- Calls (services/core api/v1/calls.py) ----------

export type ApiCallResult =
  | "booked"
  | "interested"
  | "call_back"
  | "transferred"
  | "not_interested"
  | "info_only"
  | "missed";
export type ApiCallDirection = "inbound" | "outbound" | "web";
export type CallStatus = "live" | "ended" | "processed";
export type CallRating = "up" | "down";
export type AlertKind = "hot_lead" | "angry" | "urgent" | "failed_action" | "unknown_question";

export interface CallSummaryRow {
  id: Uuid;
  employee_id: Uuid | null;
  employee_name: string | null;
  contact_id: Uuid | null;
  contact_name: string | null;
  phone_last4: string | null;
  direction: ApiCallDirection;
  status: CallStatus;
  language: Locale | null;
  started_at: IsoDateTime;
  duration_seconds: number | null;
  result: ApiCallResult | null;
  summary: string | null;
  rating: CallRating | null;
}

export interface CallList {
  items: CallSummaryRow[];
  total: number;
}

export interface CallFilters {
  result?: ApiCallResult[];
  employee_id?: Uuid;
  language?: Locale;
  date_from?: string;
  date_to?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface CallTranscriptLine {
  speaker: "employee" | "caller";
  text: string;
  interrupted: boolean;
  at_ms: number | null;
}

export interface CallActionOut {
  name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  ok: boolean;
  label: string;
}

export interface CallDetail extends CallSummaryRow {
  ended_at: IsoDateTime | null;
  next_step: string | null;
  sentiment: "positive" | "neutral" | "negative" | null;
  fields: Record<string, string>;
  transcript: CallTranscriptLine[];
  actions: CallActionOut[];
  alerts: { kind: AlertKind; message: string }[];
  unknown_questions: string[];
  recording_uri: string | null;
  rating_reason: string | null;
}

export interface HomeSummary {
  date: string;
  timezone: string;
  has_calls: boolean;
  stats: { calls_today: number; booked_today: number; rescued_today: number; needs_you: number; live_now: number };
  needs_you: {
    call_id: Uuid;
    kind: AlertKind;
    message: string;
    contact_name: string | null;
    phone_last4: string | null;
    at: IsoDateTime;
  }[];
  recent_calls: CallSummaryRow[];
}

// ---------- Customers (services/core api/v1/customers.py) ----------

export type CustomerTag = "hot_lead" | "booked" | "call_back" | "vip" | "opted_out";
export type MemoryStatus = "confirmed" | "inferred";

export interface CustomerRow {
  id: Uuid;
  name: string | null;
  phone_last4: string;
  language: Locale | null;
  tags: CustomerTag[];
  calls: number;
  last_contact_at: IsoDateTime | null;
  last_result: ApiCallResult | null;
  next_step: string | null;
}

export interface CustomerList {
  items: CustomerRow[];
  total: number;
}

export interface MemoryFact {
  id: Uuid;
  key: string;
  value: string;
  status: MemoryStatus;
  confidence: number;
  source_call_id: Uuid | null;
  expires_at: IsoDateTime | null;
  updated_at: IsoDateTime;
}

export interface TimelineEvent {
  kind: "call" | "action" | "commitment";
  at: IsoDateTime;
  title: string;
  detail: string | null;
  call_id: Uuid | null;
  result: ApiCallResult | null;
}

export interface CustomerDetail extends CustomerRow {
  created_at: IsoDateTime;
  memory: MemoryFact[];
  commitments: { id: Uuid; kind: string; description: string; due_at: IsoDateTime | null; status: string }[];
  timeline: TimelineEvent[];
}

export interface ForgetOut {
  id: Uuid;
  forgotten: true;
  calls_deleted: number;
  memory_deleted: number;
}
