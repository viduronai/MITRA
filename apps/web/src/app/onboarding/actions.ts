"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type {
  CorrectionOut,
  Employee,
  Fact,
  FactCategory,
  Gap,
  Industry,
  KnowledgeSource,
  Locale,
  RoleTemplateId,
  TestCall,
} from "@/lib/api/types";
import {
  DEFAULT_HOURS,
  hoursFromPreset,
  HOURS_COOKIE,
  INDUSTRIES,
  isHoursPreset,
  LANGUAGES,
  ROLES,
  type HoursPreset,
} from "@/lib/onboarding";
import { clearSession, requireSession, setSession } from "@/lib/session";

/** Every action validates its input here (system boundary) and maps API errors to friendly keys. */
export type StepErrorKey = "generic" | "unreachable" | "needEmployee" | "invalid";
export type Result<T = null> = { ok: true; data: T } | { ok: false; error: StepErrorKey };

const FACT_CATEGORIES: FactCategory[] = ["services", "prices", "timings", "location", "contact", "faq", "policy"];
const MAX_TEXT = 5000;

function str(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed.length <= max ? trimmed : null;
}

function fail(error: unknown): { ok: false; error: StepErrorKey } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 422) return { ok: false, error: "invalid" };
  }
  console.error("[onboarding]", error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

async function run<T>(load: (token: string) => Promise<T>): Promise<Result<T>> {
  const { token } = await requireSession();
  try {
    return { ok: true, data: await load(token) };
  } catch (error) {
    return fail(error);
  }
}

async function firstEmployee(token: string): Promise<Employee | null> {
  return (await api.listEmployees(token))[0] ?? null;
}

// ---------- 1 · Your business ----------

export interface BusinessInput {
  name: string;
  industry: Industry;
  city: string;
  languages: Locale[];
  hours: HoursPreset;
}

export async function saveBusiness(input: BusinessInput): Promise<Result> {
  const name = str(input?.name, 120);
  const city = typeof input?.city === "string" ? input.city.trim().slice(0, 80) : "";
  const languages = Array.isArray(input?.languages) ? [...new Set(input.languages)].filter((l) => LANGUAGES.includes(l)) : [];
  if (!name || !INDUSTRIES.includes(input.industry) || languages.length < 1 || languages.length > 3) {
    return { ok: false, error: "invalid" };
  }
  const hours = isHoursPreset(input.hours) ? input.hours : DEFAULT_HOURS;
  const { token, claims } = await requireSession();
  const body = { name, industry: input.industry, city: city || null, languages };

  try {
    if (claims.business_id) {
      await api.updateBusiness(token, body);
      const employee = await firstEmployee(token);
      if (employee) await api.updateEmployee(token, employee.id, { working_hours: hoursFromPreset(hours), languages });
    } else {
      const created = await api.createBusiness(token, { ...body, timezone: "Asia/Kolkata" }, crypto.randomUUID());
      await setSession(created.access_token, created.expires_in);
    }
  } catch (error) {
    return fail(error);
  }
  (await cookies()).set(HOURS_COOKIE, hours, { httpOnly: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30 });
  redirect("/onboarding?step=role");
}

// ---------- 2 · Choose a role ----------

export async function chooseRole(role: RoleTemplateId, defaultName: string): Promise<Result> {
  const name = str(defaultName, 60);
  if (!ROLES.includes(role) || !name) return { ok: false, error: "invalid" };
  const { token } = await requireSession();
  try {
    if (!(await firstEmployee(token))) {
      const business = await api.currentBusiness(token);
      const stored = (await cookies()).get(HOURS_COOKIE)?.value;
      await api.createEmployee(
        token,
        {
          name,
          role_template: role,
          voice_tier: "natural",
          languages: business.languages,
          working_hours: hoursFromPreset(isHoursPreset(stored) ? stored : DEFAULT_HOURS),
        },
        crypto.randomUUID(),
      );
    }
  } catch (error) {
    return fail(error);
  }
  redirect("/onboarding?step=teach");
}

// ---------- 3 · Teach Mitra ----------

export interface TeachState {
  sources: KnowledgeSource[];
  facts: Fact[];
  gaps: Gap[];
}

export async function getTeachState(): Promise<Result<TeachState>> {
  return run(async (token) => {
    const [sources, facts, gaps] = await Promise.all([api.listSources(token), api.listFacts(token), api.listGaps(token)]);
    return { sources, facts, gaps };
  });
}

export async function addSource(input: { type: "url"; url: string } | { type: "text"; text: string }): Promise<Result<KnowledgeSource>> {
  if (input?.type === "url") {
    const url = str(input.url, 2000);
    let parsed: URL | null = null;
    try {
      parsed = url ? new URL(url) : null;
    } catch {
      parsed = null;
    }
    if (!parsed || !["http:", "https:"].includes(parsed.protocol)) return { ok: false, error: "invalid" };
    return run((token) => api.addSource(token, { type: "url", url: parsed.toString() }));
  }
  if (input?.type === "text") {
    const text = str(input.text, MAX_TEXT);
    if (!text) return { ok: false, error: "invalid" };
    return run((token) => api.addSource(token, { type: "text", text }));
  }
  return { ok: false, error: "invalid" };
}

const validId = (id: unknown): id is string => typeof id === "string" && /^[\w-]{1,64}$/.test(id);

export async function confirmFact(id: string): Promise<Result<Fact>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => api.updateFact(token, id, { status: "confirmed" }));
}

export async function editFact(id: string, value: string): Promise<Result<Fact>> {
  const clean = str(value, 1000);
  if (!validId(id) || !clean) return { ok: false, error: "invalid" };
  return run((token) => api.updateFact(token, id, { value: clean, status: "confirmed" }));
}

export async function removeFact(id: string): Promise<Result> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await api.deleteFact(token, id);
    return null;
  });
}

export async function answerGap(category: FactCategory, key: string, value: string): Promise<Result<Fact>> {
  const cleanKey = str(key, 200);
  const cleanValue = str(value, 1000);
  if (!FACT_CATEGORIES.includes(category) || !cleanKey || !cleanValue) return { ok: false, error: "invalid" };
  return run((token) => api.addFact(token, { category, key: cleanKey, value: cleanValue }));
}

/** "Looks right, continue": confirms every remaining suggestion. */
export async function finishTeach(): Promise<Result> {
  const { token } = await requireSession();
  try {
    const facts = await api.listFacts(token);
    await Promise.all(facts.filter((f) => f.status === "suggested").map((f) => api.updateFact(token, f.id, { status: "confirmed" })));
  } catch (error) {
    return fail(error);
  }
  redirect("/onboarding?step=voice");
}

// ---------- 4 · Pick a voice ----------

export async function saveVoice(voiceId: string, employeeName: string): Promise<Result> {
  const name = str(employeeName, 60);
  if (!validId(voiceId) || !name) return { ok: false, error: "invalid" };
  const { token } = await requireSession();
  try {
    const employee = await firstEmployee(token);
    if (!employee) return { ok: false, error: "needEmployee" };
    const voice = (await api.voices(token)).find((v) => v.id === voiceId);
    if (!voice) return { ok: false, error: "invalid" };
    // voice_id sets the tier server-side (billing follows the voice).
    await api.updateEmployee(token, employee.id, { voice_id: voice.id, name });
  } catch (error) {
    return fail(error);
  }
  redirect("/onboarding?step=test_call");
}

// ---------- 5 · Test call ----------

export async function startTestCall(): Promise<Result<TestCall>> {
  return run(async (token) => {
    const employee = await firstEmployee(token);
    if (!employee) throw new ApiError(404, "no_employee", "No employee");
    return api.startTestCall(token, employee.id);
  });
}

export async function getTestCall(id: string): Promise<Result<TestCall>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => api.getTestCall(token, id));
}

export async function sendCorrection(id: string, text: string): Promise<Result<CorrectionOut>> {
  const clean = str(text, 500);
  if (!validId(id) || !clean) return { ok: false, error: "invalid" };
  return run((token) => api.addCorrection(token, id, clean));
}

// ---------- 6 · Go live ----------

/**
 * "Finish setup". Nothing to save in Step 2: forwarding needs a Mitra number
 * and going live arrives with numbers and the wallet, so go_live stays "coming next".
 */
export async function finishOnboarding(): Promise<Result> {
  await requireSession();
  (await cookies()).delete(HOURS_COOKIE);
  redirect("/onboarding?step=done");
}

export async function signOut(): Promise<void> {
  await clearSession();
  redirect("/login");
}
