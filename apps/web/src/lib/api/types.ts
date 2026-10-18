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
