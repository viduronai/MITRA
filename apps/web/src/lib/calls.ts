import type { ApiCallDirection, ApiCallResult, CallSummaryRow } from "./api/types";

/** Result as the UI shows it (pill + label); `processing` while the post-call summary runs. */
export type CallResult =
  | "booked"
  | "interested"
  | "callBack"
  | "notInterested"
  | "failed"
  | "missed"
  | "transferred"
  | "answered"
  | "processing";

export type CallDirection = "incoming" | "outgoing" | "web";

const resultMap: Record<ApiCallResult, CallResult> = {
  booked: "booked",
  interested: "interested",
  call_back: "callBack",
  not_interested: "notInterested",
  transferred: "transferred",
  info_only: "answered",
  missed: "missed",
};

export function uiResult(result: ApiCallResult | null): CallResult {
  return result ? resultMap[result] : "processing";
}

export function uiDirection(direction: ApiCallDirection): CallDirection {
  return direction === "inbound" ? "incoming" : direction === "outbound" ? "outgoing" : "web";
}

/** Filter chips on Calls (docs/07 §3.4) → API result values. */
export const resultChips = [
  { key: "booked", results: ["booked"] },
  { key: "interested", results: ["interested"] },
  { key: "callBack", results: ["call_back"] },
  { key: "missed", results: ["missed"] },
] as const satisfies readonly { key: CallResult; results: ApiCallResult[] }[];

export const allResults: ApiCallResult[] = [
  "booked",
  "interested",
  "call_back",
  "transferred",
  "not_interested",
  "info_only",
  "missed",
];

export function isApiResult(value: string): value is ApiCallResult {
  return (allResults as string[]).includes(value);
}

/** "Anjali Sharma", or "••••4821" when the caller never said their name. */
export function callerLabel(name: string | null, last4: string | null, fallback: string): string {
  if (name) return name;
  return last4 ? `••••${last4}` : fallback;
}

/** Row data for <CallRow> from the API. */
export function toCallRow(call: CallSummaryRow, fallbackEmployee: string, webCaller: string) {
  return {
    id: call.id,
    contact: callerLabel(call.contact_name, call.phone_last4, webCaller),
    direction: uiDirection(call.direction),
    result: uiResult(call.result),
    durationSeconds: call.duration_seconds ?? 0,
    at: new Date(call.started_at),
    employeeName: call.employee_name ?? fallbackEmployee,
  };
}

/** Summary text → up to 3 bullets (docs/07 §3.4). */
export function summaryBullets(summary: string | null): string[] {
  if (!summary) return [];
  return summary
    .split(/(?<=[.!?।])\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 3);
}
