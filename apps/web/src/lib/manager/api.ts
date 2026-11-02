import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  Approval,
  ApprovalEvent,
  ApprovalRule,
  ManagerSettings,
  ManagerSettingsPatch,
  ThreadMessage,
  WaMessage,
} from "./types";

// Same server-only base URL as lib/api/http.ts (a small client of its own, like billing).
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  token: string,
  { method = "GET", body }: { method?: "GET" | "POST" | "PATCH" | "PUT"; body?: unknown } = {},
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

export const managerApi = {
  thread: async (token: string) => (await request<{ items: ThreadMessage[] }>("/manager/thread", token)).items,
  ask: async (token: string, text: string) =>
    (await request<{ items: ThreadMessage[] }>("/manager/thread", token, { method: "POST", body: { text } })).items,
  settings: (token: string) => request<ManagerSettings>("/manager/settings", token),
  updateSettings: (token: string, body: ManagerSettingsPatch) =>
    request<ManagerSettings>("/manager/settings", token, { method: "PATCH", body }),

  approvals: (token: string, status: "pending" | "decided" | "all" = "pending") =>
    request<{ items: Approval[]; pending: number }>(`/approvals?status=${status}`, token),
  approval: (token: string, id: string) =>
    request<{ approval: Approval; events: ApprovalEvent[] }>(`/approvals/${enc(id)}`, token),
  editApproval: (token: string, id: string, version: number, payload: Record<string, unknown>, summary?: string) =>
    request<Approval>(`/approvals/${enc(id)}`, token, { method: "PATCH", body: { version, payload, summary } }),
  decide: (token: string, id: string, action: "approve" | "decline", version: number, note?: string) =>
    request<Approval>(`/approvals/${enc(id)}/decide`, token, { method: "POST", body: { action, version, note } }),
  rules: async (token: string) => (await request<{ items: ApprovalRule[] }>("/approvals/rules", token)).items,
  putRules: async (token: string, items: ApprovalRule[]) =>
    (await request<{ items: ApprovalRule[] }>("/approvals/rules", token, { method: "PUT", body: { items } })).items,

  simMessages: async (token: string) =>
    (await request<{ items: WaMessage[] }>("/manager/whatsapp-sim/messages", token)).items,
  simInbound: (
    token: string,
    body: { kind: "text" | "voice" | "button_reply"; text?: string; button_id?: string; context_id?: string },
  ) => request<{ outcome: string }>("/manager/whatsapp-sim/inbound", token, { method: "POST", body }),
};
