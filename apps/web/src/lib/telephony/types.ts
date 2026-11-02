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
