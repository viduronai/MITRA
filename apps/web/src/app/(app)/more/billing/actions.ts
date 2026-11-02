"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { VoiceTier } from "@/lib/api/types";
import { billingApi } from "@/lib/billing/api";
import type { Topup } from "@/lib/billing/types";
import { requireSession } from "@/lib/session";

/** Inputs are validated here (system boundary); core re-validates everything. */
export type BillingErrorKey = "generic" | "unreachable" | "invalid" | "forbidden" | "signature";
export type BillingResult<T = null> = { ok: true; data: T } | { ok: false; error: BillingErrorKey };

const TIERS: VoiceTier[] = ["smart", "natural", "signature"];
const MAX_RUPEES = 10_00_000;
const KEY_RE = /^[A-Za-z0-9-]{8,64}$/;

function fail(error: unknown): { ok: false; error: BillingErrorKey } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 403) return { ok: false, error: "forbidden" };
    if (error.status === 422) return { ok: false, error: "invalid" };
    if (error.code === "invalid_signature") return { ok: false, error: "signature" };
  }
  console.error("[billing]", error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

async function run<T>(load: (token: string) => Promise<T>): Promise<BillingResult<T>> {
  const { token } = await requireSession();
  try {
    const data = await load(token);
    refresh();
    return { ok: true, data };
  } catch (error) {
    return fail(error);
  }
}

function wholeRupees(value: unknown, min: number): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= MAX_RUPEES ? value : null;
}

/** Start a top-up. `key` is a client-generated idempotency key (double taps credit once). */
export async function topUp(rupees: number, key: string): Promise<BillingResult<Topup>> {
  const amount = wholeRupees(rupees, 500);
  if (amount === null || typeof key !== "string" || !KEY_RE.test(key)) return { ok: false, error: "invalid" };
  return run((token) => billingApi.createTopup(token, amount * 100, key));
}

/** Razorpay Checkout success callback → server-side signature verification in core. */
export async function confirmTopUp(topupId: string, paymentId: string, signature: string): Promise<BillingResult<Topup>> {
  const ok = [topupId, paymentId, signature].every((v) => typeof v === "string" && v.length > 0 && v.length <= 128);
  if (!ok) return { ok: false, error: "invalid" };
  return run((token) => billingApi.confirmTopup(token, topupId, paymentId, signature));
}

export async function setAutopay(enabled: boolean, rupees?: number): Promise<BillingResult> {
  if (typeof enabled !== "boolean") return { ok: false, error: "invalid" };
  const amount = rupees === undefined ? undefined : wholeRupees(rupees, 500);
  if (amount === null) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await billingApi.updateSettings(token, {
      autopay_enabled: enabled,
      ...(amount === undefined ? {} : { autopay_amount_paise: amount * 100 }),
    });
    return null;
  });
}

/** `rupees: null` removes the cap. */
export async function setMonthlyCap(rupees: number | null): Promise<BillingResult> {
  const amount = rupees === null ? null : wholeRupees(rupees, 0);
  if (rupees !== null && amount === null) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await billingApi.updateSettings(token, { monthly_cap_paise: amount === null ? null : amount * 100 });
    return null;
  });
}

/**
 * Billing follows the voice (core rejects a tier that contradicts the employee's voice), so a
 * tier change picks the closest voice in that tier: same gender and most shared languages.
 * Returns the new voice's name, or null when the employee has no voice yet.
 */
export async function setVoiceTier(employeeId: string, tier: VoiceTier): Promise<BillingResult<string | null>> {
  if (typeof employeeId !== "string" || !/^[0-9a-f-]{36}$/i.test(employeeId) || !TIERS.includes(tier)) {
    return { ok: false, error: "invalid" };
  }
  return run(async (token) => {
    const [employees, voices] = await Promise.all([api.listEmployees(token), api.voices(token)]);
    const employee = employees.find((e) => e.id === employeeId);
    if (!employee) throw new ApiError(404, "not_found", "Employee not found");
    const current = voices.find((v) => v.id === employee.voice_id);
    if (!current) {
      await api.updateEmployee(token, employeeId, { voice_tier: tier });
      return null;
    }
    const score = (v: (typeof voices)[number]) =>
      (v.gender === current.gender ? 10 : 0) + v.languages.filter((l) => employee.languages.includes(l)).length;
    const best = voices.filter((v) => v.tier === tier).sort((a, b) => score(b) - score(a))[0];
    if (!best) throw new ApiError(422, "no_voice", "No voice in that tier");
    await api.updateEmployee(token, employeeId, { voice_id: best.id });
    return best.name;
  });
}
