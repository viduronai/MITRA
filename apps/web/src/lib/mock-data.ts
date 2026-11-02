/**
 * TEMPORARY MOCK DATA — replace with real API data once services/ is wired up.
 * Everything here is invented: a clinic in Hyderabad with one AI employee.
 */

import type { CallDirection, CallResult } from "./calls";

export type { CallDirection, CallResult };

export interface MockCall {
  id: string;
  contact: string;
  direction: CallDirection;
  result: CallResult;
  durationSeconds: number;
  /** Fixed daytime clock time in India ("HH:MM"), so the mock never shows 2 am calls. */
  at: string;
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
  { id: "c1", contact: "Anjali Sharma", direction: "incoming", result: "booked", durationSeconds: 134, at: "17:40", employeeName: "Priya" },
  { id: "c2", contact: "Venkat Rao", direction: "incoming", result: "callBack", durationSeconds: 58, at: "16:55", employeeName: "Priya" },
  { id: "c3", contact: "+91 98xxx xx421", direction: "incoming", result: "interested", durationSeconds: 201, at: "15:20", employeeName: "Priya" },
  { id: "c4", contact: "Kavya Nair", direction: "outgoing", result: "booked", durationSeconds: 95, at: "13:05", employeeName: "Priya" },
  { id: "c5", contact: "Suresh Babu", direction: "outgoing", result: "notInterested", durationSeconds: 41, at: "11:30", employeeName: "Priya" },
  { id: "c6", contact: "Meena Iyer", direction: "incoming", result: "failed", durationSeconds: 9, at: "10:15", employeeName: "Priya" },
  { id: "c7", contact: "Arjun Patel", direction: "incoming", result: "booked", durationSeconds: 162, at: "09:25", employeeName: "Priya" },
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

/** Today's date in India at a mock call's fixed clock time. */
export function mockCallDate(at: string, now: Date = new Date()): Date {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(now); // YYYY-MM-DD
  return new Date(`${day}T${at}:00+05:30`);
}

/** Mock calls that have "happened" by now (IST), newest first; empty before 9:25 am. */
export function mockCallsSoFar(now: Date = new Date()): MockCall[] {
  return calls.filter((call) => mockCallDate(call.at, now) <= now);
}

/** "Now" for mock timestamps. Real data will carry its own times. */
export function requestTime(): Date {
  return new Date();
}
