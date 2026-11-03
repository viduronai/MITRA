"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { getLocale } from "next-intl/server";
import { ApiError } from "@/lib/api";
import { leadsApi, webhooksApi } from "@/lib/leads/api";
import {
  LEAD_SOURCES,
  WEBHOOK_EVENTS,
  type Lead,
  type LeadSetup,
  type LeadSource,
  type LeadSourceKind,
  type LeadSourcePatch,
  type PullResult,
  type Webhook,
  type WebhookDelivery,
  type WebhookEvent,
} from "@/lib/leads/types";
import { requireSession } from "@/lib/session";

/** Inputs are validated here (system boundary); core re-validates everything. */
export type LeadErrorKey = "generic" | "unreachable" | "invalid" | "forbidden" | "conflict";
export type LeadResult<T = null> = { ok: true; data: T } | { ok: false; error: LeadErrorKey; message?: string };

const ID_RE = /^[0-9a-f-]{36}$/i;
const DELAYS = [0, 300, 900, 3600];

function fail(error: unknown): { ok: false; error: LeadErrorKey; message?: string } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 403) return { ok: false, error: "forbidden" };
    if (error.status === 422) return { ok: false, error: "invalid", message: error.message };
    if (error.status === 409) return { ok: false, error: "conflict" };
  }
  console.error("[leads]", error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

async function run<T>(load: (token: string) => Promise<T>, { refreshPage = true } = {}): Promise<LeadResult<T>> {
  const { token } = await requireSession();
  try {
    const data = await load(token);
    if (refreshPage) refresh();
    return { ok: true, data };
  } catch (error) {
    return fail(error);
  }
}

const isKind = (kind: unknown): kind is LeadSourceKind => LEAD_SOURCES.includes(kind as LeadSourceKind);
const validId = (id: unknown): id is string => typeof id === "string" && ID_RE.test(id);

// Secrets come back once; the client keeps them in state (a refresh keeps client state).
export async function enableLeads(): Promise<LeadResult<LeadSetup>> {
  return run((token) => leadsApi.enable(token), { refreshPage: false });
}

export async function rotateLeadSecret(): Promise<LeadResult<LeadSetup>> {
  return run((token) => leadsApi.rotateSecret(token), { refreshPage: false });
}

export async function updateLeadSource(kind: LeadSourceKind, patch: LeadSourcePatch): Promise<LeadResult<LeadSource>> {
  if (!isKind(kind)) return { ok: false, error: "invalid" };
  const body: LeadSourcePatch = {};
  for (const key of ["enabled", "auto_call", "heads_up", "consent_attested"] as const) {
    if (typeof patch[key] === "boolean") body[key] = patch[key];
  }
  if (body.consent_attested !== undefined) {
    // The owner's own words are logged in the language they read them in.
    const locale = await getLocale();
    body.attestation_lang = locale === "hi" || locale === "te" ? locale : "en";
  }
  if (patch.call_delay_seconds !== undefined) {
    if (!DELAYS.includes(patch.call_delay_seconds)) return { ok: false, error: "invalid" };
    body.call_delay_seconds = patch.call_delay_seconds;
  }
  if (patch.employee_id !== undefined) {
    if (patch.employee_id !== null && !validId(patch.employee_id)) return { ok: false, error: "invalid" };
    body.employee_id = patch.employee_id;
  }
  if (patch.external_id !== undefined) {
    const page = typeof patch.external_id === "string" ? patch.external_id.trim() : null;
    if (page !== null && !/^[0-9A-Za-z_.-]{1,64}$/.test(page)) return { ok: false, error: "invalid" };
    body.external_id = page || null;
  }
  if (patch.credential !== undefined) {
    const key = typeof patch.credential === "string" ? patch.credential.trim() : null;
    if (key !== null && (key.length < 8 || key.length > 400)) return { ok: false, error: "invalid" };
    body.credential = key || null;
  }
  return run((token) => leadsApi.patchSource(token, kind, body));
}

export async function sendTestLead(kind: LeadSourceKind): Promise<LeadResult<{ lead: Lead; duplicate: boolean }>> {
  if (!isKind(kind)) return { ok: false, error: "invalid" };
  return run((token) => leadsApi.testLead(token, kind));
}

export async function pullIndiaMart(): Promise<LeadResult<PullResult>> {
  return run((token) => leadsApi.pullIndiaMart(token));
}

// ---- webhooks ------------------------------------------------------------------------------

const HEADER_NAME = /^[A-Za-z0-9-]{1,64}$/;

function cleanHook(url: unknown, events: unknown, description: unknown, headers: unknown) {
  const u = typeof url === "string" ? url.trim() : "";
  const ev = Array.isArray(events) ? events.filter((e): e is WebhookEvent => (WEBHOOK_EVENTS as readonly unknown[]).includes(e)) : [];
  const desc = typeof description === "string" ? description.trim().slice(0, 120) : "";
  const hdrs: Record<string, string> = {};
  if (headers && typeof headers === "object") {
    for (const [k, v] of Object.entries(headers as Record<string, unknown>)) {
      if (HEADER_NAME.test(k) && typeof v === "string" && v.length <= 500) hdrs[k] = v;
    }
  }
  if (!/^https?:\/\//.test(u) || u.length > 2048 || ev.length === 0 || Object.keys(hdrs).length > 10) return null;
  return { url: u, events: ev, description: desc || null, headers: hdrs };
}

export async function createWebhook(url: string, events: WebhookEvent[], description: string, headers: Record<string, string>): Promise<LeadResult<Webhook>> {
  const body = cleanHook(url, events, description, headers);
  if (!body) return { ok: false, error: "invalid" };
  return run((token) => webhooksApi.create(token, body));
}

export async function setWebhookEnabled(id: string, enabled: boolean): Promise<LeadResult<Webhook>> {
  if (!validId(id) || typeof enabled !== "boolean") return { ok: false, error: "invalid" };
  return run((token) => webhooksApi.update(token, id, { enabled }));
}

export async function deleteWebhook(id: string): Promise<LeadResult> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await webhooksApi.remove(token, id);
    return null;
  });
}

export async function rotateWebhookSecret(id: string): Promise<LeadResult<Webhook>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => webhooksApi.rotateSecret(token, id));
}

export async function sendWebhookTest(id: string): Promise<LeadResult<WebhookDelivery>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => webhooksApi.test(token, id));
}

export async function retryDelivery(id: string): Promise<LeadResult<WebhookDelivery>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => webhooksApi.retry(token, id));
}
