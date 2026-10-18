import "server-only";
import { ApiError, type MitraApi } from "./client";
import type {
  ApiErrorBody,
  Business,
  BusinessCreatedOut,
  CatalogVoice,
  CorrectionOut,
  Employee,
  Fact,
  Gap,
  KnowledgeSource,
  MeOut,
  OnboardingProgress,
  OtpRequestOut,
  OtpVerifyOut,
  Rate,
  RoleTemplate,
  TestCall,
} from "./types";

// Server-only base URL: never exposed to the browser (no NEXT_PUBLIC_ prefix).
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  token?: string;
  body?: unknown;
  idempotencyKey?: string;
}

async function request<T>(path: string, { method = "GET", token, body, idempotencyKey }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
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

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, error?.code ?? `http_${response.status}`, error?.message ?? response.statusText);
  }
  return data as T;
}

/** Lists come back either bare or wrapped as `{ items: [...] }`. */
function items<T>(data: T[] | { items: T[] }): T[] {
  return Array.isArray(data) ? data : data.items;
}

const enc = encodeURIComponent;

export const httpApi: MitraApi = {
  requestOtp: (phone) => request<OtpRequestOut>("/auth/otp/request", { method: "POST", body: { phone } }),
  verifyOtp: (requestId, code) =>
    request<OtpVerifyOut>("/auth/otp/verify", { method: "POST", body: { request_id: requestId, code } }),
  me: (token) => request<MeOut>("/me", { token }),

  createBusiness: (token, body, idempotencyKey) =>
    request<BusinessCreatedOut>("/businesses", { method: "POST", token, body, idempotencyKey }),
  currentBusiness: (token) => request<Business>("/businesses/current", { token }),
  updateBusiness: (token, body) => request<Business>("/businesses/current", { method: "PATCH", token, body }),

  listEmployees: async (token) => items(await request<Employee[] | { items: Employee[] }>("/employees", { token })),
  createEmployee: (token, body, idempotencyKey) =>
    request<Employee>("/employees", { method: "POST", token, body, idempotencyKey }),
  updateEmployee: (token, id, body) => request<Employee>(`/employees/${enc(id)}`, { method: "PATCH", token, body }),

  roleTemplates: async (token) =>
    items(await request<RoleTemplate[] | { items: RoleTemplate[] }>("/catalog/role-templates", { token })),
  voices: async (token, language) =>
    items(
      await request<CatalogVoice[] | { items: CatalogVoice[] }>(
        `/catalog/voices${language ? `?language=${enc(language)}` : ""}`,
        { token },
      ),
    ),
  rates: async (token) => items(await request<Rate[] | { items: Rate[] }>("/catalog/rates", { token })),

  addSource: (token, body) => request<KnowledgeSource>("/knowledge/sources", { method: "POST", token, body }),
  listSources: async (token) =>
    items(await request<KnowledgeSource[] | { items: KnowledgeSource[] }>("/knowledge/sources", { token })),
  listFacts: async (token) => items(await request<Fact[] | { items: Fact[] }>("/knowledge/facts", { token })),
  addFact: (token, body) => request<Fact>("/knowledge/facts", { method: "POST", token, body }),
  updateFact: (token, id, body) => request<Fact>(`/knowledge/facts/${enc(id)}`, { method: "PATCH", token, body }),
  deleteFact: (token, id) => request<void>(`/knowledge/facts/${enc(id)}`, { method: "DELETE", token }),
  listGaps: async (token) => items(await request<Gap[] | { items: Gap[] }>("/knowledge/gaps", { token })),

  startTestCall: (token, employeeId) =>
    request<TestCall>("/test-calls", { method: "POST", token, body: { employee_id: employeeId } }),
  getTestCall: (token, id) => request<TestCall>(`/test-calls/${enc(id)}`, { token }),
  addCorrection: (token, testCallId, text) =>
    request<CorrectionOut>(`/test-calls/${enc(testCallId)}/corrections`, { method: "POST", token, body: { text } }),

  progress: (token) => request<OnboardingProgress>("/onboarding/progress", { token }),
};
