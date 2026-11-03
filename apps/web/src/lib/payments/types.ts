/** services/core payments shapes (ACT-05/11). Money is integer paise; the business's own money. */

export type CollectionMode = "none" | "razorpay" | "upi";
export type PaymentStatus = "awaiting_approval" | "sent" | "paid" | "failed" | "expired" | "cancelled";
export const PAYMENT_STATUSES: PaymentStatus[] = ["awaiting_approval", "sent", "paid", "failed", "expired", "cancelled"];

export interface CollectionSettings {
  mode: CollectionMode;
  razorpay_key_id: string | null; // masked
  has_key_secret: boolean;
  has_webhook_secret: boolean;
  webhook_url: string;
  upi_vpa: string | null;
  payee_name: string | null;
  reminders_enabled: boolean;
  link_expiry_days: number;
  is_lender: boolean;
  simulated: boolean;
  auto_confirm: boolean;
}

export interface CollectionSettingsIn {
  mode: CollectionMode;
  razorpay_key_id?: string;
  razorpay_key_secret?: string;
  razorpay_webhook_secret?: string;
  upi_vpa?: string;
  payee_name?: string;
  reminders_enabled?: boolean;
  link_expiry_days?: number;
  is_lender?: boolean;
}

export interface PaymentRequest {
  id: string;
  contact_id: string | null;
  customer_name: string | null;
  phone_last4: string | null;
  amount_paise: number;
  purpose: string;
  due_date: string | null;
  status: PaymentStatus;
  mode: "razorpay" | "upi";
  provider: string | null;
  short_url: string | null;
  source: "owner" | "employee" | "manager";
  employee_id: string | null;
  call_id: string | null;
  approval_id: string | null;
  discount_percent: number;
  sent_at: string | null;
  send_error: string | null;
  paid_at: string | null;
  paid_via: string | null;
  failure_reason: string | null;
  cancelled_at: string | null;
  expires_at: string | null;
  customer_says_paid_at: string | null;
  remind_at: string | null;
  reminder_stage: number;
  created_at: string;
}

export interface PaymentTotals {
  collected_this_month_paise: number;
  paid_this_month: number;
  pending_paise: number;
  pending_count: number;
  failed_count: number;
}

export interface PaymentList {
  items: PaymentRequest[];
  totals: PaymentTotals;
}

export interface PaymentRequestIn {
  contact_id?: string;
  phone?: string;
  customer_name?: string;
  amount_paise: number;
  purpose: string;
  due_date?: string;
  client_ref?: string;
}

export type PaymentAction = "resend" | "cancel" | "mark-paid";
