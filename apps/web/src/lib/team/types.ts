// Mirrors services/core/src/mitra_core/schemas/team.py (AI team, routines, live calls).

export type TeamTask =
  | "book_visit"
  | "remind_appointment"
  | "follow_up"
  | "collect_payment"
  | "feedback"
  | "send_report"
  | "call_back"
  | "brief_staff";
export type TeamChannel = "call" | "whatsapp" | "whatsapp_then_call";
export type RuleResult = "booked" | "interested" | "call_back" | "not_interested" | "info_only" | "missed";

export const TASKS: TeamTask[] = [
  "book_visit",
  "remind_appointment",
  "follow_up",
  "collect_payment",
  "feedback",
  "send_report",
  "call_back",
  "brief_staff",
];
export const CHANNELS: TeamChannel[] = ["call", "whatsapp", "whatsapp_then_call"];
export const RULE_RESULTS: RuleResult[] = ["interested", "booked", "call_back", "not_interested", "info_only", "missed"];

export interface TeamTemplate {
  id: "real_estate" | "clinic" | "coaching";
  industry: string;
  name: string;
  recommended: boolean;
  roles: { id: string; name: string; title: string; base_role: string; voice_id: string }[];
  rules: { from_role: string; when_result: string; to_role: string | null; task: TeamTask; channel: TeamChannel }[];
}

export interface TeamMember {
  employee_id: string;
  name: string;
  team_role: string;
  base_role: string;
  status: "working" | "paused" | "training";
  position: number;
  calls_7d: number;
  received_7d: number;
  waiting: number;
}

export interface HandoffRule {
  id: string;
  team_id: string | null;
  from_employee_id: string;
  when_result: RuleResult;
  condition: { field?: string; op?: string; value?: string };
  to_employee_id: string | null;
  task: TeamTask;
  channel: TeamChannel;
  delay_minutes: number;
  enabled: boolean;
  version: number;
  handoffs_7d: number;
}

export interface Team {
  id: string;
  name: string;
  template_id: string | null;
  active: boolean;
  members: TeamMember[];
  rules: HandoffRule[];
}

export interface TeamMap {
  teams: Team[];
  others: TeamMember[];
}

export interface RuleIn {
  team_id?: string | null;
  from_employee_id: string;
  when_result: RuleResult;
  to_employee_id: string | null;
  task: TeamTask;
  channel: TeamChannel;
  delay_minutes: number;
}

export interface Staff {
  id: string;
  name: string;
  phone_e164: string;
  role_label: string | null;
  ladder_position: number | null;
  ring_timeout_s: number;
  receives_briefs: boolean;
  is_owner: boolean;
  active: boolean;
}

export interface StaffIn {
  name: string;
  phone_e164: string;
  role_label?: string;
  ladder_position: number | null;
  receives_briefs: boolean;
  is_owner: boolean;
}

export interface HandoffCard {
  id: string;
  caller_last4: string | null;
  reason: string;
  message: string;
  callback_by: string | null;
  attempts: { name: string; outcome: string }[];
  status: "open" | "done";
  created_at: string;
}

// --- routines ---------------------------------------------------------------------------------

export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export const WEEKDAYS: Weekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export type RoutineEvent =
  | "lead.created"
  | "call.missed"
  | "appointment.no_show"
  | "booking.made"
  | "payment.failed"
  | "payment.overdue";
export const EVENTS: RoutineEvent[] = [
  "lead.created",
  "call.missed",
  "appointment.no_show",
  "booking.made",
  "payment.failed",
  "payment.overdue",
];
export type Audience =
  | "tomorrows_appointments"
  | "todays_appointments"
  | "no_shows_yesterday"
  | "interested_not_booked"
  | "callbacks_due"
  | "missed_callers_today"
  | "inactive_customers";
export const AUDIENCES: Audience[] = [
  "tomorrows_appointments",
  "todays_appointments",
  "no_shows_yesterday",
  "interested_not_booked",
  "callbacks_due",
  "missed_callers_today",
  "inactive_customers",
];
export type Goal = "confirm" | "remind" | "follow_up" | "collect_payment" | "feedback" | "recover" | "rebook";
export const GOALS: Goal[] = ["confirm", "remind", "follow_up", "collect_payment", "feedback", "recover", "rebook"];

export type Trigger =
  | { type: "schedule"; days: Weekday[]; time: string }
  | { type: "event"; event: RoutineEvent; delay_minutes: number };

export interface RoutineSpec {
  trigger: Trigger;
  audience: Audience | null;
  action: { verb: "call" | "whatsapp"; employee_id: string; goal: Goal };
  approval_over: number;
}

export interface Routine {
  id: string;
  name: string;
  library_id: string | null;
  spec: RoutineSpec;
  sentence: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
}

export interface LibraryRoutine {
  id: string;
  name: string;
  trigger: Trigger;
  audience: Audience | null;
  goal: Goal;
  verb: "call" | "whatsapp";
  employee_id: string | null;
}

export interface Person {
  contact_id: string;
  name: string | null;
  last4: string;
  skip: "opted_out" | "no_number" | null;
}

export interface DryRun {
  sentence: string;
  would_contact: Person[];
  skipped: Person[];
  needs_approval: boolean;
  note: string | null;
}

export interface RoutineRun {
  id: string;
  routine_id: string;
  trigger: "schedule" | "event" | "manual";
  status: "awaiting_approval" | "running" | "done" | "declined" | "failed";
  audience_count: number;
  contacted_count: number;
  skipped: Record<string, number>;
  contacts: { contact_id: string; name: string | null; last4: string; status: string }[];
  started_at: string;
  finished_at: string | null;
}

// --- live calls -------------------------------------------------------------------------------

export interface LiveCall {
  id: string;
  employee_id: string | null;
  employee_name: string | null;
  direction: string;
  phone_last4: string | null;
  customer_name: string | null;
  started_at: string;
  language: string | null;
}

export interface LiveDetail {
  call: LiveCall;
  live: boolean;
  turns: { seq: number; role: string; text: string }[];
  whispers: { kind: string; text: string | null; at: string; delivered: boolean }[];
}
