"use client";

import { Plus, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface Schedule {
  calling_days: number[];
  holidays: string[];
  ends_on: string | null;
  retry_ladder: number[];
}

export type LadderKey = "standard" | "gentle" | "persistent" | "once";

export const LADDERS: Record<LadderKey, number[]> = {
  standard: [30, 120, 1440],
  gentle: [120, 1440],
  persistent: [30, 120, 1440, 2880],
  once: [],
};

const LADDER_KEYS = Object.keys(LADDERS) as LadderKey[];

export function ladderKey(ladder: number[]): LadderKey | "custom" {
  return LADDER_KEYS.find((k) => LADDERS[k].join() === ladder.join()) ?? "custom";
}

/** Monday = 0 (as the API counts). 1 Jan 2024 was a Monday. */
function weekdayName(index: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" }).format(Date.UTC(2024, 0, 1 + index));
}

function formatDay(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}

/** Calling days, holidays, last day and the retry ladder (CALL-04, CALL-15). */
export function ScheduleFields({ value, onChange }: { value: Schedule; onChange: (next: Schedule) => void }) {
  const t = useTranslations("campaigns.schedule");
  const locale = useLocale();
  const ids = { holiday: useId(), ends: useId() };
  const [holiday, setHoliday] = useState("");
  const set = (patch: Partial<Schedule>) => onChange({ ...value, ...patch });
  const key = ladderKey(value.retry_ladder);

  return (
    <div className="flex flex-col gap-5">
      <fieldset>
        <legend className="mb-2 text-sm leading-5 font-medium">{t("days")}</legend>
        <div className="grid grid-cols-7 gap-1">
          {Array.from({ length: 7 }, (_, d) => {
            const on = value.calling_days.includes(d);
            return (
              <button
                key={d}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  const next = on ? value.calling_days.filter((x) => x !== d) : [...value.calling_days, d].sort();
                  if (next.length) set({ calling_days: next });
                }}
                className={cn(
                  "focus-ring flex h-11 items-center justify-center rounded-lg border text-[13px] font-medium transition-colors motion-fast",
                  on ? "border-brand-500 bg-brand-50 text-brand-700" : "bg-surface text-text-muted hover:bg-surface-2",
                )}
              >
                {weekdayName(d, locale)}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.holiday}>{t("holidays")}</Label>
        <div className="flex gap-2">
          <Input id={ids.holiday} type="date" value={holiday} onChange={(e) => setHoliday(e.target.value)} />
          <Button
            type="button"
            variant="secondary"
            disabled={!holiday || value.holidays.includes(holiday) || value.holidays.length >= 60}
            onClick={() => {
              set({ holidays: [...value.holidays, holiday].sort() });
              setHoliday("");
            }}
          >
            <Plus aria-hidden />
            {t("addHoliday")}
          </Button>
        </div>
        {value.holidays.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {value.holidays.map((h) => (
              <li key={h}>
                <button
                  type="button"
                  onClick={() => set({ holidays: value.holidays.filter((x) => x !== h) })}
                  className="focus-ring inline-flex h-8 items-center gap-1 rounded-full bg-surface-2 px-3 text-[13px]"
                  aria-label={t("removeHoliday", { day: formatDay(h, locale) })}
                >
                  {formatDay(h, locale)}
                  <X className="size-3.5" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] leading-5 text-text-muted">{t("holidaysHint")}</p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.ends}>{t("endsOn")}</Label>
        <Input
          id={ids.ends}
          type="date"
          value={value.ends_on ?? ""}
          onChange={(e) => set({ ends_on: e.target.value || null })}
          className="sm:max-w-56"
        />
        <p className="text-[13px] leading-5 text-text-muted">{t("endsOnHint")}</p>
      </div>

      <fieldset>
        <legend className="mb-2 text-sm leading-5 font-medium">{t("retries")}</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {LADDER_KEYS.map((k) => (
            <label
              key={k}
              className={cn(
                "flex min-h-14 cursor-pointer flex-col justify-center rounded-lg border px-3 py-2 transition-colors motion-fast has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
                key === k ? "border-brand-500 bg-brand-50" : "bg-surface hover:bg-surface-2",
              )}
            >
              <input
                type="radio"
                name="ladder"
                className="sr-only"
                checked={key === k}
                onChange={() => set({ retry_ladder: LADDERS[k] })}
              />
              <span className="text-sm font-medium">{t(`ladders.${k}`)}</span>
              <span className="text-[13px] leading-5 text-text-muted">{t(`ladderHints.${k}`)}</span>
            </label>
          ))}
        </div>
        <p className="mt-2 text-[13px] leading-5 text-text-muted">{t("retriesHint")}</p>
      </fieldset>
    </div>
  );
}
