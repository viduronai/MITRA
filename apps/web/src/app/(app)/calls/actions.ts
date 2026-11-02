"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { CallRating, FactCategory } from "@/lib/api/types";
import { requireSession } from "@/lib/session";

export type ActionResult = { ok: true } | { ok: false };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function text(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().replace(/\s+/g, " ");
  return trimmed.length > 0 && trimmed.length <= max ? trimmed : null;
}

async function run(action: (token: string) => Promise<unknown>): Promise<ActionResult> {
  const { token } = await requireSession();
  try {
    await action(token);
    return { ok: true };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    console.error("[calls]", error instanceof Error ? error.message : error);
    return { ok: false };
  }
}

/** 👍 / 👎 with an optional reason (REP-05). */
export async function rateCall(callId: string, rating: CallRating, reason?: string): Promise<ActionResult> {
  if (!UUID.test(callId) || (rating !== "up" && rating !== "down")) return { ok: false };
  const why = reason ? text(reason, 300) : null;
  const result = await run((token) => api.rateCall(token, callId, rating, why ?? undefined));
  if (result.ok) revalidatePath(`/calls/${callId}`);
  return result;
}

function guessCategory(value: string): FactCategory {
  const v = value.toLowerCase();
  if (/₹|fee|price|cost|rs\.?\s?\d|charge/.test(v)) return "prices";
  if (/\b(am|pm)\b|timing|hours|open|close|sunday|monday|saturday/.test(v)) return "timings";
  if (/address|located|parking|road|near|landmark/.test(v)) return "location";
  if (/phone|whatsapp|email|call us/.test(v)) return "contact";
  if (/refund|cancel|policy/.test(v)) return "policy";
  return "faq";
}

/** "Teach Priya something from this call": a confirmed fact she uses from the next call. */
export async function teachFromCall(callId: string, question: string | null, answer: string): Promise<ActionResult> {
  const value = text(answer, 500);
  if (!UUID.test(callId) || !value) return { ok: false };
  const key = (question && text(question, 120)) || value.split(" ").slice(0, 6).join(" ").slice(0, 120);
  const category = guessCategory(`${question ?? ""} ${value}`);
  return run((token) => api.addFact(token, { category, key, value }));
}
