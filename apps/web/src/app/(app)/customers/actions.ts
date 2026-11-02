"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { requireSession } from "@/lib/session";

export type ActionResult = { ok: true } | { ok: false };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function run(customerId: string, action: (token: string) => Promise<unknown>): Promise<ActionResult> {
  const { token } = await requireSession();
  try {
    await action(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    console.error("[customers]", error instanceof Error ? error.message : error);
    return { ok: false };
  }
  revalidatePath(`/customers/${customerId}`);
  return { ok: true };
}

/** Owner correction: an edited value becomes confirmed (MEM-04). */
export async function updateMemory(customerId: string, factId: string, value: string): Promise<ActionResult> {
  const clean = typeof value === "string" ? value.trim() : "";
  if (!UUID.test(customerId) || !UUID.test(factId) || !clean || clean.length > 300) return { ok: false };
  return run(customerId, (token) => api.updateMemory(token, customerId, factId, { value: clean }));
}

export async function confirmMemory(customerId: string, factId: string): Promise<ActionResult> {
  if (!UUID.test(customerId) || !UUID.test(factId)) return { ok: false };
  return run(customerId, (token) => api.updateMemory(token, customerId, factId, { status: "confirmed" }));
}

export async function deleteMemory(customerId: string, factId: string): Promise<ActionResult> {
  if (!UUID.test(customerId) || !UUID.test(factId)) return { ok: false };
  return run(customerId, (token) => api.deleteMemory(token, customerId, factId));
}

/** DPDP erasure, then back to the list. */
export async function forgetCustomer(customerId: string): Promise<ActionResult> {
  if (!UUID.test(customerId)) return { ok: false };
  const result = await run(customerId, (token) => api.forgetCustomer(token, customerId));
  if (!result.ok) return result;
  revalidatePath("/customers");
  revalidatePath("/calls");
  redirect("/customers?forgotten=1");
}
