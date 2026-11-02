import "server-only";
import { ApiError } from "@/lib/api";
import type { ApiErrorBody } from "@/lib/api/types";
import type {
  DryRun,
  HandoffCard,
  HandoffRule,
  LibraryRoutine,
  LiveCall,
  LiveDetail,
  Routine,
  RoutineRun,
  RoutineSpec,
  RuleIn,
  Staff,
  StaffIn,
  TeamMap,
  TeamTemplate,
} from "./types";

// Same server-only base URL as lib/api/http.ts; the team screens keep their own small client
// (like billing and telephony) so the shared MitraApi interface stays untouched.
const BASE_URL = (process.env.MITRA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  token: string,
  { method = "GET", body }: { method?: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown } = {},
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
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, error?.code ?? `http_${response.status}`, error?.message ?? response.statusText);
  }
  return data as T;
}

const enc = encodeURIComponent;

export const teamApi = {
  map: (token: string) => request<TeamMap>("/team", token),
  templates: (token: string) => request<TeamTemplate[]>("/team/templates", token),
  hire: (token: string, templateId: string) =>
    request<TeamMap>("/team/hire", token, { method: "POST", body: { template_id: templateId } }),
  activate: (token: string, teamId: string) =>
    request<TeamMap>(`/team/${enc(teamId)}/activate`, token, { method: "POST" }),
  createRule: (token: string, body: RuleIn) => request<HandoffRule>("/team/rules", token, { method: "POST", body }),
  updateRule: (token: string, id: string, body: Partial<RuleIn> & { enabled?: boolean }) =>
    request<HandoffRule>(`/team/rules/${enc(id)}`, token, { method: "PATCH", body }),
  deleteRule: (token: string, id: string) => request<void>(`/team/rules/${enc(id)}`, token, { method: "DELETE" }),
  staff: (token: string) => request<Staff[]>("/team/staff", token),
  addStaff: (token: string, body: StaffIn) => request<Staff>("/team/staff", token, { method: "POST", body }),
  deleteStaff: (token: string, id: string) => request<void>(`/team/staff/${enc(id)}`, token, { method: "DELETE" }),
  cards: (token: string) => request<HandoffCard[]>("/team/handoff-cards", token),
  resolveCard: (token: string, id: string) =>
    request<HandoffCard>(`/team/handoff-cards/${enc(id)}/done`, token, { method: "POST" }),
};

export const routinesApi = {
  list: (token: string) => request<Routine[]>("/routines", token),
  library: (token: string) => request<LibraryRoutine[]>("/routines/library", token),
  create: (token: string, body: { name: string; spec: RoutineSpec; enabled: boolean }) =>
    request<Routine>("/routines", token, { method: "POST", body }),
  fromLibrary: (token: string, libraryId: string) =>
    request<Routine>("/routines/from-library", token, { method: "POST", body: { library_id: libraryId } }),
  update: (token: string, id: string, body: { enabled?: boolean; name?: string; spec?: RoutineSpec }) =>
    request<Routine>(`/routines/${enc(id)}`, token, { method: "PATCH", body }),
  remove: (token: string, id: string) => request<void>(`/routines/${enc(id)}`, token, { method: "DELETE" }),
  dryRun: (token: string, spec: RoutineSpec) =>
    request<DryRun>("/routines/dry-run", token, { method: "POST", body: { spec } }),
  runNow: (token: string, id: string) => request<RoutineRun>(`/routines/${enc(id)}/run`, token, { method: "POST" }),
  runs: (token: string, id: string) => request<RoutineRun[]>(`/routines/${enc(id)}/runs`, token),
  decide: (token: string, runId: string, approved: boolean) =>
    request<RoutineRun>(`/routines/runs/${enc(runId)}/decision`, token, { method: "POST", body: { approved } }),
};

export const liveApi = {
  list: (token: string) => request<LiveCall[]>("/live-calls", token),
  detail: (token: string, id: string, after = 0) =>
    request<LiveDetail>(`/live-calls/${enc(id)}?after=${Math.max(0, Math.floor(after))}`, token),
  whisper: (token: string, id: string, text: string) =>
    request<{ status: string }>(`/live-calls/${enc(id)}/whisper`, token, { method: "POST", body: { text } }),
  takeover: (token: string, id: string) =>
    request<{ status: string; to_last4: string }>(`/live-calls/${enc(id)}/takeover`, token, { method: "POST" }),
};
