"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { paymentsApi } from "@/lib/payments/api";
import type { CollectionMode, PaymentAction } from "@/lib/payments/types";
import { requireSession } from "@/lib/session";

/** Inputs are validated here (system boundary); core re-validates everything. */
export type PaymentsErrorKey = "generic" | "unreachable" | "invalid" | "forbidden" | "notConnected" | "notOpen";
export type PaymentsResult = { ok: true } | { ok: false; error: PaymentsErrorKey };

const UUID_RE = /^[0-9a-f-]{36}$/i;
const PHONE_RE = /^\+[1-9][0-9]{7,14}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const REF_RE = /^[A-Za-z0-9-]{8,64}$/;
const ACTIONS: PaymentAction[] = ["resend", "cancel", "mark-paid"];

function fail(error: unknown): { ok: false; error: PaymentsErrorKey } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 403) return { ok: false, error: "forbidden" };
    if (error.status === 422) return { ok: false, error: "invalid" };
    if (error.code === "collections_not_connected") return { ok: false, error: "notConnected" };
    if (error.status === 409) return { ok: false, error: "notOpen" };
  }
  console.error("[payments]", error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

async function run(load: (token: string) => Promise<unknown>): Promise<PaymentsResult> {
  const { token } = await requireSession();
  try {
    await load(token);
    refresh();
    return { ok: true };
  } catch (error) {
    return fail(error);
  }
}

/** Indian mobile numbers may be typed as 10 digits; anything else must be full E.164. */
function normalisePhone(raw: string): string | null {
  const digits = raw.replace(/[\s()-]/g, "");
  if (/^[6-9]\d{9}$/.test(digits)) return `+91${digits}`;
  return PHONE_RE.test(digits) ? digits : null;
}

export interface NewPaymentInput {
  contactId?: string;
  phone?: string;
  name?: string;
  rupees: number;
  purpose: string;
  dueDate?: string;
  key: string;
}

export async function createPaymentLink(input: NewPaymentInput): Promise<PaymentsResult> {
  const amount = Math.round(Number(input.rupees) * 100);
  const purpose = typeof input.purpose === "string" ? input.purpose.trim().slice(0, 200) : "";
  if (!Number.isFinite(amount) || amount < 100 || amount > 100_000_000 || !purpose) return { ok: false, error: "invalid" };
  if (typeof input.key !== "string" || !REF_RE.test(input.key)) return { ok: false, error: "invalid" };
  if (input.dueDate && !DATE_RE.test(input.dueDate)) return { ok: false, error: "invalid" };
  let customer: { contact_id: string } | { phone: string; customer_name?: string };
  if (input.contactId) {
    if (!UUID_RE.test(input.contactId)) return { ok: false, error: "invalid" };
    customer = { contact_id: input.contactId };
  } else {
    const phone = normalisePhone(input.phone ?? "");
    if (!phone) return { ok: false, error: "invalid" };
    const name = (input.name ?? "").trim().slice(0, 120);
    customer = name ? { phone, customer_name: name } : { phone };
  }
  return run((token) =>
    paymentsApi.create(token, {
      ...customer,
      amount_paise: amount,
      purpose,
      ...(input.dueDate ? { due_date: input.dueDate } : {}),
      client_ref: `web-${input.key}`,
    }),
  );
}

export async function actOnPayment(id: string, action: PaymentAction): Promise<PaymentsResult> {
  if (typeof id !== "string" || !UUID_RE.test(id) || !ACTIONS.includes(action)) return { ok: false, error: "invalid" };
  return run((token) => paymentsApi.act(token, id, action));
}

export interface SettingsInput {
  mode: CollectionMode;
  keyId?: string;
  keySecret?: string;
  webhookSecret?: string;
  vpa?: string;
  payeeName?: string;
  reminders?: boolean;
  expiryDays?: number;
  lender?: boolean;
}

export async function saveCollectionSettings(input: SettingsInput): Promise<PaymentsResult> {
  const clean = (v: unknown, max: number) => (typeof v === "string" ? v.trim().slice(0, max) : "");
  if (!["none", "razorpay", "upi"].includes(input.mode)) return { ok: false, error: "invalid" };
  const body: Parameters<typeof paymentsApi.saveSettings>[1] = { mode: input.mode };
  if (input.mode === "razorpay") {
    const keyId = clean(input.keyId, 64);
    if (keyId && !/^rzp_(test|live)_[A-Za-z0-9]{6,40}$/.test(keyId)) return { ok: false, error: "invalid" };
    if (keyId) body.razorpay_key_id = keyId; // omitted: core keeps the connected account
    const keySecret = clean(input.keySecret, 128);
    const hookSecret = clean(input.webhookSecret, 128);
    if (keySecret) body.razorpay_key_secret = keySecret;
    if (hookSecret) body.razorpay_webhook_secret = hookSecret;
  } else if (input.mode === "upi") {
    const vpa = clean(input.vpa, 100);
    if (!/^[A-Za-z0-9.\-_]{2,80}@[A-Za-z][A-Za-z0-9]{1,30}$/.test(vpa)) return { ok: false, error: "invalid" };
    body.upi_vpa = vpa;
    const payee = clean(input.payeeName, 100);
    if (payee) body.payee_name = payee;
  }
  if (typeof input.reminders === "boolean") body.reminders_enabled = input.reminders;
  if (input.expiryDays !== undefined) {
    if (!Number.isInteger(input.expiryDays) || input.expiryDays < 1 || input.expiryDays > 180) return { ok: false, error: "invalid" };
    body.link_expiry_days = input.expiryDays;
  }
  if (typeof input.lender === "boolean") body.is_lender = input.lender;
  return run((token) => paymentsApi.saveSettings(token, body));
}
