import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  CallerBlock,
  Forwarding,
  ForwardingTest,
  KycDocument,
  MissedCallSetup,
  PhoneNumber,
  PhoneNumberList,
} from "./types";

// Same server-only base URL as lib/api/http.ts; telephony keeps its own small client (like
// billing) so the shared MitraApi interface stays untouched.
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  token: string,
  { method = "GET", body }: { method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"; body?: unknown } = {},
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
  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, error?.code ?? `http_${response.status}`, error?.message ?? response.statusText);
  }
  return data as T;
}

const enc = encodeURIComponent;

export const telephonyApi = {
  list: (token: string) => request<PhoneNumberList>("/phone-numbers", token),
  requestNumber: (token: string, body: { city: string; type: "local" | "mobile_virtual"; employee_id?: string }) =>
    request<PhoneNumber>("/phone-numbers/requests", token, { method: "POST", body }),
  submitKyc: (token: string, id: string, documentType: KycDocument, fileName: string) =>
    request<PhoneNumber>(`/phone-numbers/${enc(id)}/kyc`, token, {
      method: "POST",
      body: { document_type: documentType, file_name: fileName },
    }),
  startCallerName: (token: string, id: string) =>
    request<PhoneNumber>(`/phone-numbers/${enc(id)}/caller-name`, token, { method: "POST" }),
  rename: (token: string, id: string, displayName: string) =>
    request<PhoneNumber>(`/phone-numbers/${enc(id)}`, token, { method: "PATCH", body: { display_name: displayName } }),
  forwarding: (token: string, id: string) => request<Forwarding>(`/phone-numbers/${enc(id)}/forwarding`, token),
  testForwarding: (token: string, id: string) =>
    request<ForwardingTest>(`/phone-numbers/${enc(id)}/forwarding-test`, token, { method: "POST" }),
  resume: (token: string, id: string) => request<PhoneNumber>(`/phone-numbers/${enc(id)}/resume`, token, { method: "POST" }),
  // Missed-call number (CALL-20).
  missedCall: (token: string) => request<MissedCallSetup>("/missed-call", token),
  setMissedCallNumber: (token: string, phoneNumberId: string | null) =>
    request<MissedCallSetup>("/missed-call/number", token, { method: "PUT", body: { phone_number_id: phoneNumberId } }),
  blockCaller: (token: string, missedCallId: string) =>
    request<CallerBlock>("/missed-call/blocks", token, { method: "POST", body: { missed_call_id: missedCallId } }),
  unblockCaller: (token: string, id: string) => request<null>(`/missed-call/blocks/${enc(id)}`, token, { method: "DELETE" }),
  // A customer's full number: owner/manager only, every view is logged in core.
  revealPhone: (token: string, customerId: string) =>
    request<{ phone: string; phone_masked: string | null }>(`/customers/${enc(customerId)}/phone`, token, { method: "POST" }),
};

/** The number customers are forwarded to: the first live number, with its codes. */
export async function liveForwarding(token: string, numbers: PhoneNumber[]): Promise<Forwarding | null> {
  const live = numbers.find((n) => n.kyc_status === "approved" && n.e164);
  return live ? telephonyApi.forwarding(token, live.id).catch(() => null) : null;
}
