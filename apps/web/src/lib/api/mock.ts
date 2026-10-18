import "server-only";
import { ApiError, type MitraApi } from "./client";
import type {
  Business,
  CatalogVoice,
  Employee,
  Fact,
  FactCategory,
  Gap,
  Industry,
  KnowledgeSource,
  OnboardingProgress,
  Rate,
  RoleTemplate,
  TestCall,
  TranscriptLine,
} from "./types";

/**
 * DEV-ONLY MOCK of services/core, enabled with MITRA_API_MOCK=1. In-memory
 * and per server process; it mirrors the Step 2 contract closely enough to
 * build the UI before the real API is up. The OTP is always 123456.
 */

interface MockUser {
  id: string;
  phone: string;
  businessId: string | null;
}

interface MockTestCall {
  id: string;
  employeeId: string;
  businessId: string;
  startedAt: number;
}

interface Store {
  otps: Map<string, { phone: string; code: string; attempts: number }>;
  users: Map<string, MockUser>;
  businesses: Map<string, Business>;
  employees: Map<string, Employee>;
  sources: Map<string, KnowledgeSource & { businessId: string; readyAt: number }>;
  facts: Map<string, Fact & { businessId: string }>;
  testCalls: Map<string, MockTestCall>;
}

const globalStore = globalThis as unknown as { __mitraMock?: Store };
const store: Store = (globalStore.__mitraMock ??= {
  otps: new Map(),
  users: new Map(),
  businesses: new Map(),
  employees: new Map(),
  sources: new Map(),
  facts: new Map(),
  testCalls: new Map(),
});

const DEV_CODE = "123456";
const STATE_MS = 2000;
const now = () => new Date().toISOString();
const id = () => crypto.randomUUID();
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function b64url(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

/** Unsigned JWT-shaped token so the proxy can read `sub`, `business_id`, `exp`. */
function issueToken(user: MockUser) {
  const exp = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7;
  const token = `${b64url({ alg: "none", typ: "JWT" })}.${b64url({ sub: user.id, business_id: user.businessId, exp })}.mock`;
  return { access_token: token, token_type: "bearer" as const, expires_in: 60 * 60 * 24 * 7 };
}

function userFrom(token: string): MockUser {
  try {
    const claims = JSON.parse(Buffer.from(token.split(".")[1] ?? "", "base64url").toString()) as { sub?: string };
    const user = claims.sub ? store.users.get(claims.sub) : undefined;
    if (user) return user;
  } catch {
    // fall through
  }
  throw new ApiError(401, "unauthorized", "Not signed in.");
}

function businessOf(token: string): Business {
  const user = userFrom(token);
  const business = user.businessId ? store.businesses.get(user.businessId) : undefined;
  if (!business) throw new ApiError(403, "no_business", "Create a business first.");
  return business;
}

/** Drops the mock-only fields before data leaves the "API". */
function publicFact(fact: Fact & { businessId: string }): Fact {
  const { id: factId, category, key, value, source_id, status } = fact;
  return { id: factId, category, key, value, source_id, status };
}

function publicSource(source: KnowledgeSource & { readyAt: number }): KnowledgeSource {
  const { id: sourceId, type, title, created_at, error, readyAt } = source;
  return { id: sourceId, type, title, created_at, error, status: Date.now() >= readyAt ? "ready" : "processing" };
}

const employeesOf = (businessId: string) => [...store.employees.values()].filter((e) => e.business_id === businessId);
const factsOf = (businessId: string) => [...store.facts.values()].filter((f) => f.businessId === businessId);

const roleTemplates: RoleTemplate[] = [
  { id: "receptionist", name: "Receptionist", description: "Answers every call, books appointments and answers questions.", default_for: ["clinic", "other"], sample_audio_url: null },
  { id: "lead_caller", name: "Lead Caller", description: "Calls new enquiries within minutes and finds out what they need.", default_for: ["real_estate", "education"], sample_audio_url: null },
  { id: "reminder_caller", name: "Reminder Caller", description: "Reminds customers about appointments and visits a day before.", default_for: [], sample_audio_url: null },
  { id: "payment_caller", name: "Payment Caller", description: "Politely follows up on pending payments and fees.", default_for: [], sample_audio_url: null },
];

const voices: CatalogVoice[] = [
  { id: "priya-te-hyd", name: "Priya", personality: "Friendly, warm", languages: ["te", "en"], dialect: "Hyderabadi", gender: "female", tier: "natural", sample_text: "Namaskaram!", sample_audio_url: null },
  { id: "ravi-te-vja", name: "Ravi", personality: "Calm, respectful", languages: ["te", "en"], dialect: "Coastal Andhra", gender: "male", tier: "smart", sample_text: "Namaskaram!", sample_audio_url: null },
  { id: "meena-hi-del", name: "Meena", personality: "Bright, quick", languages: ["hi", "en"], dialect: "Delhi", gender: "female", tier: "natural", sample_text: "Namaste!", sample_audio_url: null },
  { id: "arjun-hi-mum", name: "Arjun", personality: "Polite, formal", languages: ["hi", "en"], dialect: "Mumbai", gender: "male", tier: "signature", sample_text: "Namaste!", sample_audio_url: null },
  { id: "kavya-en-blr", name: "Kavya", personality: "Clear, patient", languages: ["en", "te", "hi"], dialect: "Indian English", gender: "female", tier: "signature", sample_text: "Hello!", sample_audio_url: null },
  { id: "sai-en-hyd", name: "Sai", personality: "Easy-going, helpful", languages: ["en", "te"], dialect: "Indian English", gender: "male", tier: "smart", sample_text: "Hello!", sample_audio_url: null },
];

const rates: Rate[] = [
  { tier: "smart", inr_per_min: 3 },
  { tier: "natural", inr_per_min: 4.5 },
  { tier: "signature", inr_per_min: 6 },
];

const gapsByIndustry: Record<Industry, Gap[]> = {
  clinic: [
    { category: "prices", key: "Consultation fee", question: "What is your consultation fee?" },
    { category: "timings", key: "Sunday timings", question: "Are you open on Sundays?" },
    { category: "location", key: "Address", question: "What is your clinic's address?" },
  ],
  real_estate: [
    { category: "prices", key: "Price range", question: "What price range are your projects in?" },
    { category: "location", key: "Site address", question: "Where is the site office?" },
  ],
  education: [
    { category: "prices", key: "Course fee", question: "What is the course fee?" },
    { category: "timings", key: "Batch timings", question: "What are the batch timings?" },
  ],
  other: [
    { category: "timings", key: "Opening hours", question: "When are you open?" },
    { category: "location", key: "Address", question: "Where are you located?" },
  ],
};

function guessCategory(key: string): FactCategory {
  const k = key.toLowerCase();
  if (/fee|price|cost|₹|rs/.test(k)) return "prices";
  if (/time|timing|hour|open|close|sunday|day/.test(k)) return "timings";
  if (/address|location|where|parking/.test(k)) return "location";
  if (/phone|email|whatsapp|contact/.test(k)) return "contact";
  if (/policy|refund|cancel/.test(k)) return "policy";
  if (/service|treatment|course|doctor/.test(k)) return "services";
  return "faq";
}

function addFacts(businessId: string, sourceId: string, pairs: [string, string][]) {
  for (const [key, value] of pairs) {
    const fact = { id: id(), category: guessCategory(key), key, value, source_id: sourceId, status: "suggested" as const, businessId };
    store.facts.set(fact.id, fact);
  }
}

function transcriptFor(employee: Employee, business: Business): TranscriptLine[] {
  const fee = factsOf(business.id).find((f) => f.status === "confirmed" && f.category === "prices");
  return [
    { speaker: "employee", text: `Namaskaram, ${business.name} nunchi ${employee.name} maatladutunnanu. How can I help you?`, at_ms: 0 },
    { speaker: "caller", text: "Hi, I want to book an appointment for tomorrow.", at_ms: 1500 },
    { speaker: "employee", text: "Sure. Would morning or evening suit you better?", at_ms: 3000 },
    { speaker: "caller", text: "Evening. And how much is it?", at_ms: 4500 },
    { speaker: "employee", text: fee ? `${fee.key} is ${fee.value}. I've booked you for 6:15 pm tomorrow.` : "Let me check that and send it to you on WhatsApp. I've booked you for 6:15 pm tomorrow.", at_ms: 6000 },
  ];
}

const CONNECTED_MS = 8000;

function testCallView(call: MockTestCall): TestCall {
  const elapsed = Date.now() - call.startedAt;
  const employee = store.employees.get(call.employeeId)!;
  const business = store.businesses.get(call.businessId)!;
  const lines = transcriptFor(employee, business);
  if (elapsed < STATE_MS) return { id: call.id, status: "queued", simulated: true, transcript: [] };
  if (elapsed < STATE_MS * 2) return { id: call.id, status: "ringing", simulated: true, transcript: [] };
  const talk = elapsed - STATE_MS * 2;
  if (talk < CONNECTED_MS) {
    return { id: call.id, status: "connected", simulated: true, transcript: lines.filter((l) => l.at_ms <= talk) };
  }
  return {
    id: call.id,
    status: "completed",
    simulated: true,
    transcript: lines,
    summary: `${employee.name} greeted the caller, booked an appointment for 6:15 pm tomorrow and answered a question about fees.`,
  };
}

function progressOf(token: string): OnboardingProgress {
  const user = userFrom(token);
  const businessId = user.businessId;
  const employees = businessId ? employeesOf(businessId) : [];
  const done = {
    business: Boolean(businessId),
    role: employees.length > 0,
    teach: businessId ? factsOf(businessId).filter((f) => f.status === "confirmed").length >= 3 : false,
    voice: employees.some((e) => e.voice_id),
    test_call: [...store.testCalls.values()].some((c) => c.businessId === businessId && testCallView(c).status === "completed"),
    go_live: false, // as in the API: going live needs a number + wallet (later step)
  };
  const steps = (Object.keys(done) as (keyof typeof done)[]).map((key) => ({ key, done: done[key] }));
  const count = steps.filter((s) => s.done).length;
  return { steps, percent: Math.round((count / steps.length) * 100), next: steps.find((s) => !s.done)?.key ?? null };
}

export const mockApi: MitraApi = {
  async requestOtp(phone) {
    if (!/^\+91[6-9]\d{9}$/.test(phone)) throw new ApiError(422, "validation_error", "Invalid phone number.");
    const requestId = id();
    store.otps.set(requestId, { phone, code: DEV_CODE, attempts: 0 });
    return { request_id: requestId, expires_in: 300, resend_in: 30, dev_code: DEV_CODE };
  },
  async verifyOtp(requestId, code) {
    const otp = store.otps.get(requestId);
    if (!otp) throw new ApiError(400, "otp_expired", "Code expired.");
    if (++otp.attempts > 5) throw new ApiError(429, "too_many_attempts", "Too many attempts.");
    if (otp.code !== code) throw new ApiError(400, "invalid_code", "Wrong code.");
    store.otps.delete(requestId);
    let user = [...store.users.values()].find((u) => u.phone === otp.phone);
    if (!user) {
      user = { id: id(), phone: otp.phone, businessId: null };
      store.users.set(user.id, user);
    }
    const business = user.businessId ? store.businesses.get(user.businessId) : undefined;
    return {
      ...issueToken(user),
      user: { id: user.id, phone_last4: user.phone.slice(-4), name: null, preferred_locale: "en" },
      memberships: business ? [{ business_id: business.id, business_name: business.name, role: "owner" }] : [],
    };
  },
  async me(token) {
    const user = userFrom(token);
    const business = user.businessId ? store.businesses.get(user.businessId) : undefined;
    return {
      user: { id: user.id, phone_e164: user.phone, name: null, email: null, preferred_locale: "en" },
      memberships: business ? [{ business_id: business.id, business_name: business.name, role: "owner" }] : [],
    };
  },

  async createBusiness(token, body) {
    const user = userFrom(token);
    const business: Business = {
      id: id(), agency_id: null, name: body.name, industry: body.industry, city: body.city ?? null,
      languages: body.languages, timezone: body.timezone ?? "Asia/Kolkata", created_at: now(), updated_at: now(),
    };
    store.businesses.set(business.id, business);
    user.businessId = business.id;
    const { access_token, expires_in } = issueToken(user);
    return { business, membership: { business_id: business.id, business_name: business.name, role: "owner" }, access_token, expires_in };
  },
  async currentBusiness(token) {
    return businessOf(token);
  },
  async updateBusiness(token, body) {
    const business = businessOf(token);
    Object.assign(business, body, { updated_at: now() });
    return business;
  },

  async listEmployees(token) {
    return employeesOf(businessOf(token).id);
  },
  async createEmployee(token, body) {
    const business = businessOf(token);
    const employee: Employee = {
      id: id(), business_id: business.id, name: body.name, role_template: body.role_template,
      voice_tier: body.voice_tier ?? "natural", status: "training", languages: body.languages,
      working_hours: body.working_hours ?? null, voice_id: null, greeting: null, behaviour: null,
      created_at: now(), updated_at: now(),
    };
    store.employees.set(employee.id, employee);
    return employee;
  },
  async updateEmployee(token, employeeId, body) {
    const business = businessOf(token);
    const employee = store.employees.get(employeeId);
    if (!employee || employee.business_id !== business.id) throw new ApiError(404, "not_found", "Employee not found.");
    if (body.voice_id && !voices.some((v) => v.id === body.voice_id)) throw new ApiError(422, "validation_error", "Unknown voice.");
    Object.assign(employee, body, { updated_at: now() });
    return employee;
  },

  async roleTemplates() {
    return roleTemplates;
  },
  async voices(_token, language) {
    return language ? voices.filter((v) => v.languages.includes(language)) : voices;
  },
  async rates() {
    return rates;
  },

  async addSource(token, body) {
    const business = businessOf(token);
    if (body.type === "url" && !/^https?:\/\//i.test(body.url)) throw new ApiError(422, "validation_error", "Invalid link.");
    const source = {
      id: id(), type: body.type, status: "processing" as const, title: body.type === "url" ? body.url : "Your notes",
      created_at: now(), error: null, businessId: business.id, readyAt: Date.now() + 2500,
    };
    store.sources.set(source.id, source);
    if (body.type === "text") {
      const pairs = body.text
        .split(/\r?\n/)
        .map((line): [string, string] => {
          const at = line.indexOf(":");
          return at < 0 ? ["", ""] : [line.slice(0, at).trim(), line.slice(at + 1).trim()];
        })
        .filter(([key, value]) => key && value);
      addFacts(business.id, source.id, pairs.length ? pairs : [["Note", body.text.trim().slice(0, 200)]]);
    } else {
      addFacts(business.id, source.id, [
        ["Business name", business.name],
        ["Opening hours", "Mon–Sat, 9 am – 9 pm"],
        ["Phone", "+91 40 2345 6789"],
        ["Services", "General consultation, health check-ups, lab tests"],
      ]);
    }
    return { ...publicSource(source), status: "processing" };
  },
  async listSources(token) {
    const business = businessOf(token);
    return [...store.sources.values()]
      .filter((s) => s.businessId === business.id)
      .map(publicSource);
  },
  async listFacts(token) {
    const business = businessOf(token);
    const pending = [...store.sources.values()].filter((s) => s.businessId === business.id && Date.now() < s.readyAt);
    return factsOf(business.id)
      .filter((f) => !pending.some((s) => s.id === f.source_id))
      .map(publicFact);
  },
  async addFact(token, body) {
    const business = businessOf(token);
    const fact = { id: id(), ...body, source_id: null, status: "confirmed" as const, businessId: business.id };
    store.facts.set(fact.id, fact);
    return publicFact(fact);
  },
  async updateFact(token, factId, body) {
    const business = businessOf(token);
    const fact = store.facts.get(factId);
    if (!fact || fact.businessId !== business.id) throw new ApiError(404, "not_found", "Fact not found.");
    Object.assign(fact, body);
    return publicFact(fact);
  },
  async deleteFact(token, factId) {
    const business = businessOf(token);
    const fact = store.facts.get(factId);
    if (fact?.businessId === business.id) store.facts.delete(factId);
  },
  async listGaps(token) {
    const business = businessOf(token);
    const facts = factsOf(business.id);
    return gapsByIndustry[business.industry].filter(
      (gap) => !facts.some((f) => f.key.toLowerCase() === gap.key.toLowerCase()),
    );
  },

  async startTestCall(token, employeeId) {
    const business = businessOf(token);
    if (!store.employees.has(employeeId)) throw new ApiError(404, "not_found", "Employee not found.");
    const call = { id: id(), employeeId, businessId: business.id, startedAt: Date.now() };
    store.testCalls.set(call.id, call);
    return { id: call.id, status: "queued", simulated: true };
  },
  async getTestCall(token, callId) {
    const business = businessOf(token);
    const call = store.testCalls.get(callId);
    if (!call || call.businessId !== business.id) throw new ApiError(404, "not_found", "Test call not found.");
    return testCallView(call);
  },
  async addCorrection(token, callId, text) {
    const business = businessOf(token);
    await wait(400);
    const call = store.testCalls.get(callId);
    if (!call) throw new ApiError(404, "not_found", "Test call not found.");
    if (/₹|price|fee|time|hours|rs\.?\s?\d/i.test(text)) {
      const factId = id();
      store.facts.set(factId, { id: factId, category: guessCategory(text), key: "Owner note", value: text, source_id: null, status: "confirmed", businessId: business.id });
      return { id: id(), applied_to: "knowledge", change_summary: `Added to what they know: "${text}"` };
    }
    return { id: id(), applied_to: "behaviour", change_summary: `Noted how to behave: "${text}"` };
  },

  async progress(token) {
    return progressOf(token);
  },
};
