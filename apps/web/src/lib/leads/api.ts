import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  Lead,
  LeadSetup,
  LeadSource,
  LeadSourceKind,
  LeadSourcePatch,
  PullResult,
  Webhook,
  WebhookDelivery,
  WebhookInput,
} from "./types";

// Same server-only base URL as lib/api/http.ts; leads keep their own small client (like
// telephony and billing) so the shared MitraApi interface stays untouched.
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

type Method = "GET" | "POST" | "PATCH" | "DELETE";

async function request<T>(path: string, token: string, { method = "GET", body }: { method?: Method; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError(0, "unreachable", "The Mitra service could not be reached.");
  }
  if (response.status === 204) return null as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, error?.code ?? `http_${response.status}`, error?.message ?? response.statusText);
  }
  return data as T;
}

const enc = encodeURIComponent;

export const leadsApi = {
  setup: (token: string) => request<LeadSetup>("/leads/setup", token),
  enable: (token: string) => request<LeadSetup>("/leads/setup", token, { method: "POST" }),
  rotateSecret: (token: string) => request<LeadSetup>("/leads/setup/rotate-secret", token, { method: "POST" }),
  patchSource: (token: string, kind: LeadSourceKind, body: LeadSourcePatch) =>
    request<LeadSource>(`/leads/sources/${enc(kind)}`, token, { method: "PATCH", body }),
  testLead: (token: string, kind: LeadSourceKind) =>
    request<{ lead: Lead; duplicate: boolean }>(`/leads/sources/${enc(kind)}/test`, token, { method: "POST" }),
  pullIndiaMart: (token: string) => request<PullResult>("/leads/sources/indiamart/pull", token, { method: "POST" }),
  recent: (token: string, limit = 10) => request<{ items: Lead[] }>(`/leads?limit=${limit}`, token),
};

export const webhooksApi = {
  list: (token: string) => request<{ items: Webhook[]; events: string[] }>("/webhooks", token),
  create: (token: string, body: WebhookInput) => request<Webhook>("/webhooks", token, { method: "POST", body }),
  update: (token: string, id: string, body: Partial<WebhookInput> & { enabled?: boolean }) =>
    request<Webhook>(`/webhooks/${enc(id)}`, token, { method: "PATCH", body }),
  remove: (token: string, id: string) => request<null>(`/webhooks/${enc(id)}`, token, { method: "DELETE" }),
  rotateSecret: (token: string, id: string) => request<Webhook>(`/webhooks/${enc(id)}/rotate-secret`, token, { method: "POST" }),
  test: (token: string, id: string) => request<WebhookDelivery>(`/webhooks/${enc(id)}/test`, token, { method: "POST" }),
  deliveries: (token: string, id: string, limit = 20) =>
    request<{ items: WebhookDelivery[] }>(`/webhooks/${enc(id)}/deliveries?limit=${limit}`, token),
  retry: (token: string, deliveryId: string) =>
    request<WebhookDelivery>(`/webhooks/deliveries/${enc(deliveryId)}/retry`, token, { method: "POST" }),
};
