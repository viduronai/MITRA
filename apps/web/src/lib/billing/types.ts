import type { VoiceTier } from "@/lib/api/types";

/** services/core billing shapes (money is always integer paise). */

export type PauseReason = "zero_balance" | "spend_cap";
export type TxnKind = "topup" | "bonus" | "usage" | "passthrough" | "refund" | "expiry";

export interface TierRate {
  tier: VoiceTier;
  paise_per_min: number;
  minutes_left: number;
}

export interface BonusSlab {
  min_paise: number;
  pct: number;
}

export interface TopupRules {
  min_paise: number;
  max_paise: number;
  gst_rate_pct: number;
  bonus_slabs: BonusSlab[];
}

export interface BillingSummary {
  balance_paise: number;
  bonus_paise: number;
  available_paise: number;
  rates: TierRate[];
  month: string;
  month_usage_paise: number;
  month_extras_paise: number;
  monthly_cap_paise: number | null;
  cap_remaining_paise: number | null;
  outbound_paused: boolean;
  pause_reason: PauseReason | null;
  low_balance: boolean;
  low_balance_threshold_paise: number;
  autopay_enabled: boolean;
  autopay_amount_paise: number;
  credits_expire_at: string | null;
  grace_seconds_left_today: number;
  number_rental: { fee_paise: number; waiver_usage_paise: number; remaining_to_waive_paise: number };
  topup_rules: TopupRules;
  profile: { billing_name: string | null; gstin: string | null; state_code: string | null };
}

export interface BillingSettingsPatch {
  monthly_cap_paise?: number | null;
  autopay_enabled?: boolean;
  autopay_amount_paise?: number;
  low_balance_threshold_paise?: number;
  billing_name?: string | null;
  gstin?: string | null;
  state_code?: string | null;
}

export interface Topup {
  id: string;
  status: "created" | "paid" | "failed";
  source: "manual" | "autopay";
  provider: string;
  provider_order_id: string;
  amount_paise: number;
  bonus_paise: number;
  gst_paise: number;
  total_paise: number;
  created_at: string;
  paid_at: string | null;
  invoice_id: string | null;
  checkout: { provider: string; key_id: string; order_id: string; amount: number; currency: string } | null;
}

export interface Txn {
  id: string;
  kind: TxnKind;
  category: string | null;
  paid_delta_paise: number;
  bonus_delta_paise: number;
  balance_after_paise: number;
  bonus_after_paise: number;
  description: string;
  created_at: string;
}

export interface UsageReport {
  since: string;
  by_day: { day: string; calls: number; billable_seconds: number; amount_paise: number }[];
  by_employee: {
    employee_id: string;
    employee_name: string;
    tier: VoiceTier;
    calls: number;
    billable_seconds: number;
    amount_paise: number;
  }[];
}

export interface InvoiceSummary {
  id: string;
  number: string;
  issued_at: string;
  taxable_paise: number;
  total_paise: number;
}

export interface InvoiceParty {
  name: string;
  gstin: string | null;
  state_code: string | null;
  address: string | null;
}

export interface Invoice {
  id: string;
  number: string;
  issued_at: string;
  supplier: InvoiceParty;
  buyer: InvoiceParty;
  place_of_supply: string | null;
  intra_state: boolean;
  description: string;
  sac_code: string;
  taxable_paise: number;
  cgst_paise: number;
  sgst_paise: number;
  igst_paise: number;
  total_paise: number;
  gst_rate_pct: number;
}
