import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  CollectionSettings,
  CollectionSettingsIn,
  PaymentAction,
  PaymentList,
  PaymentRequest,
  PaymentRequestIn,
  PaymentStatus,
} from "./types";

// Same server-only base URL as lib/api/http.ts; payments keeps its own small client (like billing).
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  token: string,
  { method = "GET", body }: { method?: "GET" | "POST" | "PUT"; body?: unknown } = {},
): Promise<T> {
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
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, error?.code ?? `http_${response.status}`, error?.message ?? response.statusText);
  }
  return data as T;
}

const enc = encodeURIComponent;

export const paymentsApi = {
  settings: (token: string) => request<CollectionSettings>("/payments/settings", token),
  saveSettings: (token: string, body: CollectionSettingsIn) =>
    request<CollectionSettings>("/payments/settings", token, { method: "PUT", body }),
  list: (token: string, { status, contactId }: { status?: PaymentStatus; contactId?: string } = {}) => {
    const query = new URLSearchParams();
    if (status) query.set("status", status);
    if (contactId) query.set("contact_id", contactId);
    const qs = query.toString();
    return request<PaymentList>(`/payments${qs ? `?${qs}` : ""}`, token);
  },
  create: (token: string, body: PaymentRequestIn) => request<PaymentRequest>("/payments", token, { method: "POST", body }),
  act: (token: string, id: string, action: PaymentAction) =>
    request<PaymentRequest>(`/payments/${enc(id)}/${action}`, token, { method: "POST" }),
};
