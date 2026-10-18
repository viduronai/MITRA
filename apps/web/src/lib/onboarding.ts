import type { Industry, Locale, OnboardingStepKey, RoleTemplateId, WorkingHours } from "./api/types";

/** The six onboarding steps, in order (docs/07 §3.2). */
export const ONBOARDING_STEPS: OnboardingStepKey[] = ["business", "role", "teach", "voice", "test_call", "go_live"];

export function isStepKey(value: unknown): value is OnboardingStepKey {
  return typeof value === "string" && (ONBOARDING_STEPS as string[]).includes(value);
}

export function stepAfter(step: OnboardingStepKey): OnboardingStepKey | "done" {
  return ONBOARDING_STEPS[ONBOARDING_STEPS.indexOf(step) + 1] ?? "done";
}

export const INDUSTRIES: Industry[] = ["clinic", "real_estate", "education", "other"];
export const LANGUAGES: Locale[] = ["te", "hi", "en"];
export const ROLES: RoleTemplateId[] = ["receptionist", "lead_caller", "reminder_caller", "payment_caller"];

/** Used when the catalog has no `default_for` match (docs/07 §3.2). */
export const DEFAULT_ROLE: Record<Industry, RoleTemplateId> = {
  clinic: "receptionist",
  real_estate: "lead_caller",
  education: "lead_caller",
  other: "receptionist",
};

// ---------- Working hours presets (default 9–9) ----------

export type HoursPreset = "everyday9to9" | "monSat9to9" | "monSat10to7" | "allDay";
export const HOURS_PRESETS: HoursPreset[] = ["everyday9to9", "monSat9to9", "monSat10to7", "allDay"];
export const DEFAULT_HOURS: HoursPreset = "everyday9to9";
/** Business has no hours field yet: the choice waits in this cookie until the employee exists. */
export const HOURS_COOKIE = "mitra_onb_hours";

const ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const presetSpec: Record<HoursPreset, { days: readonly (typeof ALL_DAYS)[number][]; start: string; end: string }> = {
  everyday9to9: { days: ALL_DAYS, start: "09:00", end: "21:00" },
  monSat9to9: { days: ALL_DAYS.slice(0, 6), start: "09:00", end: "21:00" },
  monSat10to7: { days: ALL_DAYS.slice(0, 6), start: "10:00", end: "19:00" },
  allDay: { days: ALL_DAYS, start: "00:00", end: "23:59" },
};

export function isHoursPreset(value: unknown): value is HoursPreset {
  return typeof value === "string" && (HOURS_PRESETS as string[]).includes(value);
}

export function hoursFromPreset(preset: HoursPreset): WorkingHours {
  const { days, start, end } = presetSpec[preset];
  return Object.fromEntries(days.map((day) => [day, [{ start, end }]])) as WorkingHours;
}

export function presetFromHours(hours: WorkingHours | null | undefined): HoursPreset | null {
  if (!hours) return null;
  return (
    HOURS_PRESETS.find((preset) => {
      const { days, start, end } = presetSpec[preset];
      return ALL_DAYS.every((day) => {
        const ranges = hours[day] ?? [];
        return days.includes(day)
          ? ranges.length === 1 && ranges[0].start === start && ranges[0].end === end
          : ranges.length === 0;
      });
    }) ?? null
  );
}

// ---------- Call forwarding codes ----------
// TODO(ops): verify with each operator before real numbers launch. The X's
// become the owner's Mitra number once numbers exist.

export type Operator = "jio" | "airtel" | "vi" | "bsnl";
export const OPERATORS: { id: Operator; name: string }[] = [
  { id: "jio", name: "Jio" },
  { id: "airtel", name: "Airtel" },
  { id: "vi", name: "Vi" },
  { id: "bsnl", name: "BSNL" },
];

export type ForwardWhen = "busy" | "noAnswer" | "unreachable";
const NUMBER_PLACEHOLDER = "XXXXXXXXXX";
const gsm: Record<ForwardWhen, string> = {
  busy: `**67*${NUMBER_PLACEHOLDER}#`,
  noAnswer: `**61*${NUMBER_PLACEHOLDER}#`,
  unreachable: `**62*${NUMBER_PLACEHOLDER}#`,
};

export const FORWARD_CODES: Record<Operator, Record<ForwardWhen, string>> = {
  jio: {
    busy: `*405*${NUMBER_PLACEHOLDER}`,
    noAnswer: `*403*${NUMBER_PLACEHOLDER}`,
    unreachable: `*409*${NUMBER_PLACEHOLDER}`,
  },
  airtel: gsm,
  vi: gsm,
  bsnl: gsm,
};
