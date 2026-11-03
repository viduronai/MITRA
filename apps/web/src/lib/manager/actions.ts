"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { requireSession } from "@/lib/session";
import { managerApi } from "./api";
import { ALERT_KINDS, type ApprovalRule, type ManagerSettingsPatch, type ThreadMessage } from "./types";

/** Inputs are validated here (system boundary); core re-validates everything. */
export type ManagerErrorKey = "generic" | "unreachable" | "invalid" | "forbidden" | "stale" | "decided";
export type ManagerResult<T = null> = { ok: true; data: T } | { ok: false; error: ManagerErrorKey };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const LOCALES = ["en", "hi", "te"] as const;
const RULE_KINDS = ["discount", "refund", "cancellation", "big_booking", "list_call", "payment_link"] as const;

function fail(error: unknown): { ok: false; error: ManagerErrorKey } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 403) return { ok: false, error: "forbidden" };
    if (error.status === 422) return { ok: false, error: "invalid" };
    if (error.code === "stale_version") return { ok: false, error: "stale" };
    if (error.code === "already_decided") return { ok: false, error: "decided" };
  }
  console.error("[manager]", error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

async function run<T>(load: (token: string) => Promise<T>): Promise<ManagerResult<T>> {
  const { token } = await requireSession();
  try {
    const data = await load(token);
    refresh();
    return { ok: true, data };
  } catch (error) {
    return fail(error);
  }
}

function cleanText(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().replace(/\s+/g, " ");
  return trimmed.length > 0 && trimmed.length <= max ? trimmed : null;
}

/** Ask Mitra: returns the new owner + Mitra turns. */
export async function askMitra(text: string): Promise<ManagerResult<ThreadMessage[]>> {
  const said = cleanText(text, 1000);
  if (!said) return { ok: false, error: "invalid" };
  return run((token) => managerApi.ask(token, said));
}

export async function decideApproval(
  id: string,
  action: "approve" | "decline",
  version: number,
  note?: string,
): Promise<ManagerResult> {
  if (!UUID.test(id) || (action !== "approve" && action !== "decline") || !Number.isInteger(version) || version < 1) {
    return { ok: false, error: "invalid" };
  }
  const why = note ? cleanText(note, 300) ?? undefined : undefined;
  return run(async (token) => {
    await managerApi.decide(token, id, action, version, why);
    return null;
  });
}

/** Edit before approving (APPR-06): the version bumps, so older cards stop working. */
export async function editApproval(
  id: string,
  version: number,
  payload: Record<string, unknown>,
  summary?: string,
): Promise<ManagerResult<number>> {
  const isObject = typeof payload === "object" && payload !== null && !Array.isArray(payload);
  if (!UUID.test(id) || !Number.isInteger(version) || !isObject || JSON.stringify(payload).length > 16_000) {
    return { ok: false, error: "invalid" };
  }
  const text = summary === undefined ? undefined : cleanText(summary, 500) ?? undefined;
  return run(async (token) => (await managerApi.editApproval(token, id, version, payload, text)).version);
}

export async function saveRules(rules: ApprovalRule[]): Promise<ManagerResult> {
  const valid =
    Array.isArray(rules) &&
    rules.length <= RULE_KINDS.length &&
    rules.every(
      (r) =>
        RULE_KINDS.includes(r.kind) &&
        typeof r.enabled === "boolean" &&
        (r.threshold === null || (Number.isInteger(r.threshold) && r.threshold >= 0 && r.threshold <= 100_000_000)) &&
        (r.timeout_minutes === null || (Number.isInteger(r.timeout_minutes) && r.timeout_minutes >= 1 && r.timeout_minutes <= 10_080)) &&
        (r.default_action === null || r.default_action === "approve" || r.default_action === "decline"),
    );
  if (!valid) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await managerApi.putRules(token, rules);
    return null;
  });
}

export async function saveManagerSettings(patch: ManagerSettingsPatch): Promise<ManagerResult> {
  const ids = (list: unknown) => Array.isArray(list) && list.length <= 20 && list.every((v) => typeof v === "string" && UUID.test(v));
  const ok =
    (patch.report_enabled === undefined || typeof patch.report_enabled === "boolean") &&
    (patch.report_time === undefined || TIME.test(patch.report_time)) &&
    (patch.language === undefined || patch.language === null || LOCALES.includes(patch.language)) &&
    (patch.report_user_ids === undefined || ids(patch.report_user_ids)) &&
    (patch.alert_user_ids === undefined || ids(patch.alert_user_ids)) &&
    (patch.alert_kinds === undefined ||
      (Array.isArray(patch.alert_kinds) && patch.alert_kinds.every((k) => (ALERT_KINDS as readonly string[]).includes(k))));
  if (!ok) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await managerApi.updateSettings(token, patch);
    return null;
  });
}

/** Dev simulator: reply on "WhatsApp" as the logged-in owner. */
export async function simReply(
  input: { kind: "text" | "voice"; text: string } | { kind: "button_reply"; button_id: string; context_id: string },
): Promise<ManagerResult<string>> {
  if (input.kind === "button_reply") {
    const okButton = typeof input.button_id === "string" && input.button_id.length <= 200 && typeof input.context_id === "string" && input.context_id.length <= 128;
    if (!okButton) return { ok: false, error: "invalid" };
    return run(async (token) => (await managerApi.simInbound(token, input)).outcome);
  }
  const said = cleanText(input.text, 1000);
  if (!said || (input.kind !== "text" && input.kind !== "voice")) return { ok: false, error: "invalid" };
  return run(async (token) => (await managerApi.simInbound(token, { kind: input.kind, text: said })).outcome);
}
