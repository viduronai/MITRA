import "server-only";
import { ApiError, type MitraApi } from "./client";
import type {
  ApiCallResult,
  CallDetail,
  CallFilters,
  CallSummaryRow,
  CustomerDetail,
  CustomerRow,
  HomeSummary,
  MemoryFact,
  TimelineEvent,
} from "./types";

/**
 * DEV-ONLY mock of the calls, customers and home endpoints (part of MITRA_API_MOCK=1).
 * Each business gets a handful of invented calls from this morning the first time it
 * asks, so the screens have something to show before the voice service is running.
 */

export interface MockTenant {
  businessId: string;
  employeeId: string | null;
  employeeName: string;
}

interface MockContact {
  id: string;
  name: string | null;
  phone_last4: string;
  language: "te" | "hi" | "en";
  created_at: string;
  memory: MemoryFact[];
}

interface CallsStore {
  calls: CallDetail[];
  contacts: Map<string, MockContact>;
}

const globalStore = globalThis as unknown as { __mitraMockCalls?: Map<string, CallsStore> };
const stores = (globalStore.__mitraMockCalls ??= new Map<string, CallsStore>());
const id = () => crypto.randomUUID();

/** Today at HH:MM in India. */
function todayAt(hhmm: string): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  return new Date(`${day}T${hhmm}:00+05:30`).toISOString();
}

interface Seed {
  at: string;
  name: string | null;
  last4: string;
  language: "te" | "hi" | "en";
  result: ApiCallResult;
  seconds: number;
  summary: string;
  fields: Record<string, string>;
  lines: [speaker: "caller" | "employee", text: string][];
  actions: { name: string; label: string; ok?: boolean }[];
  memory: [key: string, value: string, status: "confirmed" | "inferred"][];
  alerts?: CallDetail["alerts"];
  unknown?: string[];
}

const seeds: Seed[] = [
  {
    at: "09:25",
    name: "Anjali Sharma",
    last4: "4821",
    language: "te",
    result: "booked",
    seconds: 134,
    summary: 'Caller said: "Doctor appointment kavali repu evening". Booked for tomorrow, 6:15 pm.',
    fields: { name: "Anjali Sharma", appointment: "Tomorrow, 6:15 pm" },
    lines: [
      ["employee", "Namaskaram, Sunrise Clinic nunchi Priya. Nenu AI assistant ni."],
      ["caller", "Doctor appointment kavali repu evening."],
      ["employee", "Repu 6:15 pm ki slot undi. Mee peru cheptara?"],
      ["caller", "Anjali Sharma. Thank you!"],
    ],
    actions: [
      { name: "book_slot", label: "Booked tomorrow, 6:15 pm" },
      { name: "send_whatsapp_template", label: "WhatsApp sent: booking confirmation" },
    ],
    memory: [
      ["name", "Anjali Sharma", "confirmed"],
      ["preferred_time", "evening", "inferred"],
      ["preferred_language", "Telugu", "inferred"],
    ],
  },
  {
    at: "10:15",
    name: null,
    last4: "7710",
    language: "hi",
    result: "missed",
    seconds: 6,
    summary: "Missed call: nobody spoke.",
    fields: {},
    lines: [["employee", "Namaste, Sunrise Clinic se Priya bol rahi hoon."]],
    actions: [],
    memory: [],
  },
  {
    at: "11:30",
    name: "Ravi Kumar",
    last4: "3302",
    language: "en",
    result: "call_back",
    seconds: 88,
    summary: 'Caller said: "Is the clinic open on Sunday?". Asked for a callback.',
    fields: {},
    lines: [
      ["caller", "Is the clinic open on Sunday?"],
      ["employee", "I'll check with the team and get back to you on Sunday timings."],
    ],
    actions: [{ name: "schedule_callback", label: "Callback scheduled: Sunday timings" }],
    memory: [["name", "Ravi Kumar", "confirmed"]],
    alerts: [{ kind: "unknown_question", message: 'Could not answer: "Is the clinic open on Sunday?"' }],
    unknown: ["Is the clinic open on Sunday?"],
  },
];

function storeFor(tenant: MockTenant): CallsStore {
  let store = stores.get(tenant.businessId);
  if (store) return store;
  store = { calls: [], contacts: new Map() };
  for (const seed of seeds) {
    const contact: MockContact = {
      id: id(),
      name: seed.name,
      phone_last4: seed.last4,
      language: seed.language,
      created_at: todayAt(seed.at),
      memory: [],
    };
    const callId = id();
    contact.memory = seed.memory.map(([key, value, status]) => ({
      id: id(),
      key,
      value,
      status,
      confidence: status === "confirmed" ? 0.9 : 0.5,
      source_call_id: callId,
      expires_at: status === "inferred" ? new Date(Date.now() + 180 * 864e5).toISOString() : null,
      updated_at: todayAt(seed.at),
    }));
    store.contacts.set(contact.id, contact);
    store.calls.push({
      id: callId,
      employee_id: tenant.employeeId,
      employee_name: tenant.employeeName,
      contact_id: contact.id,
      contact_name: seed.name,
      phone_last4: seed.last4,
      direction: "inbound",
      status: "processed",
      language: seed.language,
      started_at: todayAt(seed.at),
      ended_at: todayAt(seed.at),
      duration_seconds: seed.seconds,
      result: seed.result,
      summary: seed.summary,
      rating: null,
      rating_reason: null,
      next_step: seed.result === "call_back" ? "Call back: Sunday timings" : null,
      sentiment: "neutral",
      fields: seed.fields,
      transcript: seed.lines.map(([speaker, text]) => ({ speaker, text, interrupted: false, at_ms: null })),
      actions: seed.actions.map((a) => ({ name: a.name, label: a.label, ok: a.ok ?? true, args: {}, result: {} })),
      alerts: seed.alerts ?? [],
      unknown_questions: seed.unknown ?? [],
      recording_uri: null,
    });
  }
  store.calls.sort((a, b) => b.started_at.localeCompare(a.started_at));
  stores.set(tenant.businessId, store);
  return store;
}

function row(c: CallDetail): CallSummaryRow {
  return {
    id: c.id,
    employee_id: c.employee_id,
    employee_name: c.employee_name,
    contact_id: c.contact_id,
    contact_name: c.contact_name,
    phone_last4: c.phone_last4,
    direction: c.direction,
    status: c.status,
    language: c.language,
    started_at: c.started_at,
    duration_seconds: c.duration_seconds,
    result: c.result,
    summary: c.summary,
    rating: c.rating,
  };
}

function matches(call: CallDetail, f: CallFilters): boolean {
  if (f.result?.length && (!call.result || !f.result.includes(call.result))) return false;
  if (f.language && call.language !== f.language) return false;
  if (f.employee_id && call.employee_id !== f.employee_id) return false;
  const day = call.started_at.slice(0, 10);
  if (f.date_from && day < f.date_from) return false;
  if (f.date_to && day > f.date_to) return false;
  if (f.q) {
    const q = f.q.toLowerCase();
    const haystack = [call.summary, call.contact_name, ...call.transcript.map((l) => l.text)].join(" ").toLowerCase();
    if (!haystack.includes(q)) return false;
  }
  return true;
}

function customerRow(store: CallsStore, contact: MockContact): CustomerRow {
  const calls = store.calls.filter((c) => c.contact_id === contact.id);
  const last = calls[0];
  const tag = last?.result === "booked" ? "booked" : last?.result === "call_back" ? "call_back" : null;
  return {
    id: contact.id,
    name: contact.name,
    phone_last4: contact.phone_last4,
    language: contact.language,
    tags: tag ? [tag] : [],
    calls: calls.length,
    last_contact_at: last?.started_at ?? null,
    last_result: last?.result ?? null,
    next_step: last?.next_step ?? null,
  };
}

function contactOf(store: CallsStore, customerId: string): MockContact {
  const contact = store.contacts.get(customerId);
  if (!contact) throw new ApiError(404, "not_found", "Customer not found");
  return contact;
}

type CallsApi = Pick<
  MitraApi,
  | "listCalls"
  | "getCall"
  | "rateCall"
  | "exportCalls"
  | "homeSummary"
  | "listCustomers"
  | "getCustomer"
  | "updateMemory"
  | "deleteMemory"
  | "forgetCustomer"
>;

export function callsMock(tenantOf: (token: string) => MockTenant): CallsApi {
  const get = (token: string) => storeFor(tenantOf(token));
  const call = (token: string, callId: string) => {
    const found = get(token).calls.find((c) => c.id === callId);
    if (!found) throw new ApiError(404, "not_found", "Call not found");
    return found;
  };
  return {
    async listCalls(token, filters = {}) {
      const all = get(token).calls.filter((c) => matches(c, filters));
      return { items: all.map(row), total: all.length };
    },
    async getCall(token, callId) {
      return call(token, callId);
    },
    async rateCall(token, callId, rating, reason) {
      Object.assign(call(token, callId), { rating, rating_reason: reason ?? null });
    },
    async exportCalls(token, filters = {}) {
      const lines = get(token)
        .calls.filter((c) => matches(c, filters))
        .map((c) => [c.started_at, c.employee_name, c.contact_name, c.phone_last4, c.result, c.summary]);
      const csv = [["started_at", "employee", "customer", "phone_last4", "result", "summary"], ...lines]
        .map((cells) => cells.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(","))
        .join("\n");
      return `﻿${csv}\n`;
    },
    async homeSummary(token): Promise<HomeSummary> {
      const store = get(token);
      const today = store.calls.filter((c) => c.started_at.slice(0, 10) === todayAt("12:00").slice(0, 10));
      const needs = store.calls.flatMap((c) =>
        c.alerts.map((a) => ({
          call_id: c.id,
          kind: a.kind,
          message: a.message,
          contact_name: c.contact_name,
          phone_last4: c.phone_last4,
          at: c.started_at,
        })),
      );
      return {
        date: todayAt("12:00").slice(0, 10),
        timezone: "Asia/Kolkata",
        has_calls: store.calls.length > 0,
        stats: {
          calls_today: today.length,
          booked_today: today.filter((c) => c.result === "booked").length,
          rescued_today: 0,
          needs_you: needs.length,
          live_now: 0,
        },
        needs_you: needs,
        recent_calls: store.calls.slice(0, 5).map(row),
      };
    },
    async listCustomers(token, q) {
      const store = get(token);
      const needle = q?.trim().toLowerCase();
      const items = [...store.contacts.values()]
        .filter((c) => !needle || (c.name ?? "").toLowerCase().includes(needle) || c.phone_last4.includes(needle))
        .map((c) => customerRow(store, c))
        .sort((a, b) => (b.last_contact_at ?? "").localeCompare(a.last_contact_at ?? ""));
      return { items, total: items.length };
    },
    async getCustomer(token, customerId): Promise<CustomerDetail> {
      const store = get(token);
      const contact = contactOf(store, customerId);
      const calls = store.calls.filter((c) => c.contact_id === contact.id);
      const timeline: TimelineEvent[] = calls.flatMap((c) => [
        ...c.actions.map((a) => ({
          kind: "action" as const,
          at: c.started_at,
          title: a.label,
          detail: null,
          call_id: c.id,
          result: null,
        })),
        { kind: "call" as const, at: c.started_at, title: "Call", detail: c.summary, call_id: c.id, result: c.result },
      ]);
      return {
        ...customerRow(store, contact),
        created_at: contact.created_at,
        memory: contact.memory,
        commitments: [],
        timeline,
      };
    },
    async updateMemory(token, customerId, factId, body) {
      const fact = contactOf(get(token), customerId).memory.find((m) => m.id === factId);
      if (!fact) throw new ApiError(404, "not_found", "Memory not found");
      if (body.value !== undefined) Object.assign(fact, { value: body.value, status: "confirmed" });
      if (body.status) fact.status = body.status;
      if (fact.status === "confirmed") Object.assign(fact, { confidence: 1, expires_at: null });
      fact.updated_at = new Date().toISOString();
      return fact;
    },
    async deleteMemory(token, customerId, factId) {
      const contact = contactOf(get(token), customerId);
      contact.memory = contact.memory.filter((m) => m.id !== factId);
    },
    async forgetCustomer(token, customerId) {
      const store = get(token);
      const contact = contactOf(store, customerId);
      const before = store.calls.length;
      store.calls = store.calls.filter((c) => c.contact_id !== contact.id);
      store.contacts.delete(contact.id);
      return {
        id: contact.id,
        forgotten: true,
        calls_deleted: before - store.calls.length,
        memory_deleted: contact.memory.length,
      };
    },
  };
}
