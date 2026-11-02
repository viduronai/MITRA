import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  BillingSettingsPatch,
  BillingSummary,
  Invoice,
  InvoiceSummary,
  Topup,
  Txn,
  UsageReport,
} from "./types";

// Same server-only base URL as lib/api/http.ts; billing keeps its own small client so the
// shared MitraApi interface stays untouched.
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  token: string,
  { method = "GET", body, idempotencyKey }: { method?: "GET" | "POST" | "PATCH"; body?: unknown; idempotencyKey?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
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

export const billingApi = {
  summary: (token: string) => request<BillingSummary>("/billing/summary", token),
  updateSettings: (token: string, body: BillingSettingsPatch) =>
    request<BillingSummary>("/billing/settings", token, { method: "PATCH", body }),
  createTopup: (token: string, amountPaise: number, idempotencyKey: string) =>
    request<Topup>("/billing/topups", token, { method: "POST", body: { amount_paise: amountPaise }, idempotencyKey }),
  confirmTopup: (token: string, id: string, paymentId: string, signature: string) =>
    request<Topup>(`/billing/topups/${enc(id)}/confirm`, token, {
      method: "POST",
      body: { payment_id: paymentId, signature },
    }),
  transactions: async (token: string, limit = 20) =>
    (await request<{ items: Txn[] }>(`/billing/transactions?limit=${limit}`, token)).items,
  usage: (token: string, days = 30) => request<UsageReport>(`/billing/usage?days=${days}`, token),
  invoices: async (token: string) => (await request<{ items: InvoiceSummary[] }>("/billing/invoices", token)).items,
  invoice: (token: string, id: string) => request<Invoice>(`/billing/invoices/${enc(id)}`, token),
};
