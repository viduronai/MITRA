/** Campaigns API shapes (services/core schemas/campaign.py, CALL-15). */

export type CampaignStatus = "draft" | "pending_approval" | "running" | "paused" | "completed" | "cancelled";
export type CampaignPurpose = "service" | "callback" | "mandated_service" | "promotional";
export type Bucket = "interested" | "call_back" | "not_interested" | "no_answer" | "blocked";
export type ContactStatus = "pending" | "queued" | "done" | "skipped";

export const BUCKETS: Bucket[] = ["interested", "call_back", "not_interested", "no_answer", "blocked"];

export interface CampaignProgress {
  total: number;
  /** Dialled at least once (a person blocked by compliance was never dialled). */
  called: number;
  blocked: number;
  skipped: number;
  remaining: number;
  dialing: number;
  done: number;
  buckets: Record<Bucket, number>;
  reasons: Record<string, number>;
  blocked_summary: string[];
  eta_minutes: number | null;
  starts_at?: string | null;
  channels: number;
}

export interface Campaign {
  id: string;
  name: string;
  employee_id: string | null;
  employee_name: string | null;
  purpose: CampaignPurpose;
  status: CampaignStatus;
  pause_reason: string | null;
  column_map: Record<string, string>;
  variables: string[];
  skip_recent_days: number;
  calling_days: number[];
  holidays: string[];
  retry_ladder: number[];
  ends_on: string | null;
  avg_call_seconds: number;
  approval_id: string | null;
  /** The owner's list attestation (docs/08 §8.5); null until ticked. */
  consent: CampaignConsent | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress: CampaignProgress;
}

export interface CampaignConsent {
  scope: "service" | "promotional";
  text: string;
  text_version: string;
  by_name: string | null;
  at: string;
}

/** The owner's tick: the server stores its own exact words for this language. */
export interface ConsentTick {
  consent_attested: boolean;
  consent_language: "en" | "hi" | "te";
}

export interface ListPreview {
  headers: string[];
  phone_column: string;
  name_column: string | null;
  column_map: Record<string, string>;
  valid: number;
  invalid: number;
  duplicates: number;
  errors: { row_number: number; reason: string }[];
  sample: { row_number: number; phone_last4: string; name: string | null; variables: Record<string, string> }[];
}

export interface ListIn {
  text: string;
  phone_column?: string | null;
  name_column?: string | null;
  column_map?: Record<string, string> | null;
}

export interface CampaignIn extends ListIn, Partial<ConsentTick> {
  name: string;
  employee_id: string;
  purpose: CampaignPurpose;
  skip_recent_days: number;
  calling_days: number[];
  holidays: string[];
  retry_ladder: number[];
  ends_on: string | null;
}

export interface CampaignPatch {
  name?: string;
  calling_days?: number[];
  holidays?: string[];
  retry_ladder?: number[];
  ends_on?: string | null;
  avg_call_seconds?: number;
}

export interface CampaignCreated {
  campaign: Campaign;
  added: number;
  skipped_recent: number;
  invalid: number;
  duplicates: number;
}

export interface ContactsAdded extends Omit<CampaignCreated, "campaign"> {
  campaign: Campaign;
}

export interface CampaignContact {
  id: string;
  row_number: number;
  name: string | null;
  phone_last4: string;
  status: ContactStatus;
  bucket: Bucket | null;
  reasons: string[];
  attempts: number;
  last_outcome: string | null;
  last_called_at: string | null;
  call_id: string | null;
  summary: string | null;
}
