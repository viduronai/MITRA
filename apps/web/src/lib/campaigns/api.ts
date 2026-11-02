import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  Bucket,
  Campaign,
  CampaignContact,
  CampaignCreated,
  CampaignIn,
  CampaignPatch,
  ContactsAdded,
  ListIn,
  ListPreview,
} from "./types";

// Same server-only base URL as lib/api/http.ts; campaigns keep their own small client (like
// telephony and billing) so the shared MitraApi interface stays untouched.
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 30_000;

type Method = "GET" | "POST" | "PATCH" | "PUT";

async function send(path: string, token: string, method: Method, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
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
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(response.status, data?.error?.code ?? `http_${response.status}`, data?.error?.message ?? response.statusText);
  }
  return response;
}

async function request<T>(path: string, token: string, method: Method = "GET", body?: unknown): Promise<T> {
  return (await (await send(path, token, method, body)).json()) as T;
}

const enc = encodeURIComponent;

export const campaignsApi = {
  list: (token: string) => request<{ items: Campaign[] }>("/campaigns", token),
  get: (token: string, id: string) => request<Campaign>(`/campaigns/${enc(id)}`, token),
  preview: (token: string, body: ListIn) => request<ListPreview>("/campaigns/preview", token, "POST", body),
  create: (token: string, body: CampaignIn) => request<CampaignCreated>("/campaigns", token, "POST", body),
  edit: (token: string, id: string, body: CampaignPatch) =>
    request<Campaign>(`/campaigns/${enc(id)}`, token, "PATCH", body),
  transition: (token: string, id: string, action: "start" | "pause" | "resume" | "cancel") =>
    request<Campaign>(`/campaigns/${enc(id)}/${action}`, token, "POST"),
  extend: (token: string, id: string, body: ListIn) =>
    request<ContactsAdded>(`/campaigns/${enc(id)}/contacts`, token, "POST", body),
  contacts: (token: string, id: string, bucket?: Bucket, offset = 0) => {
    const q = new URLSearchParams({ limit: "50", offset: String(offset) });
    if (bucket) q.set("bucket", bucket);
    return request<{ items: CampaignContact[]; total: number }>(`/campaigns/${enc(id)}/contacts?${q}`, token);
  },
  channels: (token: string) => request<{ channels: number }>("/campaigns/settings", token),
  setChannels: (token: string, channels: number) =>
    request<{ channels: number }>("/campaigns/settings", token, "PUT", { channels }),
  exportCsv: async (token: string, id: string) => (await send(`/campaigns/${enc(id)}/export.csv`, token, "GET")).text(),
  sampleCsv: async (token: string) => (await send("/campaigns/sample.csv", token, "GET")).text(),
};
