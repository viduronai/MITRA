/** Mirrors services/core schemas/telephony.py (public Connect / Go-live API). */

export type NumberType = "local" | "mobile_virtual" | "byo_sip" | "1600" | "1601" | "140";
export type KycStatus = "pending_kyc" | "submitted" | "approved" | "rejected";
export type VerificationStatus = "not_started" | "pending" | "verified" | "rejected";
export type NumberHealth = "healthy" | "watch" | "paused";
export type OperatorId = "jio" | "airtel" | "vi" | "bsnl";
export type KycDocument = "gst" | "shop_establishment" | "udyam" | "pan" | "clinic_registration";

export type PhoneNumber = {
  id: string;
  e164: string | null;
  display: string | null;
  type: NumberType;
  carrier: "exotel" | "plivo" | "sip" | "sim";
  city: string | null;
  label: string | null;
  employee_id: string | null;
  kyc_status: KycStatus;
  display_name: string | null;
  truecaller_status: VerificationStatus;
  cnap_status: VerificationStatus;
  answer_rate_7d: number | null;
  health: NumberHealth;
  health_reasons: string[];
  remediation: string[];
  outbound_enabled: boolean;
  spam_flag: boolean;
  forwarding_tested_at: string | null;
  created_at: string;
  /** CALL-20: calls are rejected unanswered and Mitra calls back. */
  missed_call?: boolean;
};

export type PhoneNumberList = {
  items: PhoneNumber[];
  carrier: "sim" | "exotel" | "plivo";
  simulated: boolean;
  business_name: string;
};

export type OperatorCodes = {
  operator: OperatorId;
  name: string;
  busy: string;
  no_answer: string;
  unreachable: string;
  cancel: string;
};

export type Forwarding = { phone_number_id: string; target: string; operators: OperatorCodes[] };

export type ForwardingTest = {
  status: "passed" | "pending";
  simulated: boolean;
  tested_at: string | null;
  message: string;
};

export type MissedCallStatus = "queued" | "deduped" | "rate_limited" | "blocked";

export type MissedCallRow = {
  id: string;
  phone_masked: string | null;
  status: MissedCallStatus;
  received_at: string;
  call_back_at: string | null;
  /** The callback's dialer status or last outcome (answered, no_answer, queued, ...). */
  outcome: string | null;
};

export type CallerBlock = { id: string; phone_masked: string | null; reason: string | null; created_at: string };

export type MissedCallSetup = {
  phone_number_id: string | null;
  e164: string | null;
  display: string | null;
  live: boolean;
  tel_uri: string | null;
  poster: { en: string; hi: string; te: string } | null;
  stats: { days: number; missed: number; called_back: number; answered: number };
  recent: MissedCallRow[];
  blocks: CallerBlock[];
};
