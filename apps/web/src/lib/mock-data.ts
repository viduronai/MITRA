/**
 * TEMPORARY MOCK DATA — replace with real API data once services/ is wired up.
 * Everything here is invented: a clinic in Hyderabad with one AI employee.
 */

export type CallResult =
  | "booked"
  | "interested"
  | "callBack"
  | "notInterested"
  | "failed";

export type CallDirection = "incoming" | "outgoing";

export interface MockCall {
  id: string;
  contact: string;
  direction: CallDirection;
  result: CallResult;
  durationSeconds: number;
  /** Minutes before "now"; turned into a Date at request time. */
  minutesAgo: number;
  employeeName: string;
}

export type NeedKind = "unknownQuestion" | "upsetCaller" | "failedMessage";

export interface MockNeed {
  id: string;
  kind: NeedKind;
  name: string;
}

export interface MockSetupStep {
  key: "business" | "teach" | "voice" | "testCall" | "forward";
  done: boolean;
}

export interface MockVoice {
  id: string;
  name: string;
  personality: string;
  languages: string[];
}

export const business = {
  name: "Sunrise Clinic",
  ownerName: "Lakshmi",
  city: "Hyderabad",
  walletRupees: 2450,
  minutesLeft: 540,
};

export const employee = {
  name: "Priya",
  initials: "P",
  role: "receptionist" as const,
  status: "working" as "working" | "paused",
  liveCalls: 2,
  callsToday: 24,
  bookedToday: 9,
};

export const stats = {
  callsToday: { value: 24, change: 4 },
  booked: { value: 9, change: 2 },
  rescued: { value: 6, change: -1 },
  needsYou: { value: 3, change: 0 },
};

export const needs: MockNeed[] = [
  { id: "n1", kind: "unknownQuestion", name: "Ravi Kumar" },
  { id: "n2", kind: "upsetCaller", name: "Sunitha Reddy" },
  { id: "n3", kind: "failedMessage", name: "Mohammed Irfan" },
];

export const calls: MockCall[] = [
  { id: "c1", contact: "Anjali Sharma", direction: "incoming", result: "booked", durationSeconds: 134, minutesAgo: 12, employeeName: "Priya" },
  { id: "c2", contact: "Venkat Rao", direction: "incoming", result: "callBack", durationSeconds: 58, minutesAgo: 34, employeeName: "Priya" },
  { id: "c3", contact: "+91 98xxx xx421", direction: "incoming", result: "interested", durationSeconds: 201, minutesAgo: 61, employeeName: "Priya" },
  { id: "c4", contact: "Kavya Nair", direction: "outgoing", result: "booked", durationSeconds: 95, minutesAgo: 88, employeeName: "Priya" },
  { id: "c5", contact: "Suresh Babu", direction: "outgoing", result: "notInterested", durationSeconds: 41, minutesAgo: 126, employeeName: "Priya" },
  { id: "c6", contact: "Meena Iyer", direction: "incoming", result: "failed", durationSeconds: 9, minutesAgo: 170, employeeName: "Priya" },
  { id: "c7", contact: "Arjun Patel", direction: "incoming", result: "booked", durationSeconds: 162, minutesAgo: 215, employeeName: "Priya" },
];

export const setupSteps: MockSetupStep[] = [
  { key: "business", done: true },
  { key: "teach", done: true },
  { key: "voice", done: true },
  { key: "testCall", done: false },
  { key: "forward", done: false },
];

export const voices: MockVoice[] = [
  { id: "v1", name: "Priya", personality: "Warm and patient, like a trusted front desk.", languages: ["Telugu", "English"] },
  { id: "v2", name: "Meena", personality: "Bright and quick, keeps calls short.", languages: ["Telugu", "Hindi"] },
  { id: "v3", name: "Arjun", personality: "Calm and respectful, good with elders.", languages: ["Hindi", "English"] },
];

export function minutesAgoToDate(minutesAgo: number, now: Date = new Date()): Date {
  return new Date(now.getTime() - minutesAgo * 60_000);
}

/** "Now" for mock timestamps. Real data will carry its own times. */
export function requestTime(): Date {
  return new Date();
}
