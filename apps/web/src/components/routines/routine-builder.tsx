"use client";

import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { dryRun, saveRoutine } from "@/app/(app)/routines/actions";
import { selectClass } from "@/components/team/rule-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  AUDIENCES,
  EVENTS,
  GOALS,
  WEEKDAYS,
  type Audience,
  type DryRun,
  type Goal,
  type RoutineEvent,
  type RoutineSpec,
  type Weekday,
} from "@/lib/team/types";

interface EmployeeOption {
  id: string;
  name: string;
}

/** Render a spec as the owner's sentence (AUTO-01). Shared by the list and the builder. */
export function useSentence() {
  const t = useTranslations("routines");
  return (spec: RoutineSpec, employee: string) => {
    const verb = t(`verbs.${spec.action.verb}`);
    const goal = t(`goals.${spec.action.goal}`);
    if (spec.trigger.type === "schedule") {
      const days =
        spec.trigger.days.length === 7 ? t("everyDay") : spec.trigger.days.map((d) => t(`days.${d}`)).join(", ");
      return t("sentenceSchedule", {
        days,
        time: spec.trigger.time,
        employee,
        verb,
        audience: t(`audiences.${spec.audience ?? "tomorrows_appointments"}`),
        goal,
      });
    }
    return t("sentenceEvent", {
      event: t(`events.${spec.trigger.event}`),
      employee,
      verb,
      delay: spec.trigger.delay_minutes,
      goal,
    });
  };
}

export function RoutineBuilder({ employees }: { employees: EmployeeOption[] }) {
  const t = useTranslations("routines");
  const sentence = useSentence();
  const [pending, start] = useTransition();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"schedule" | "event">("schedule");
  const [days, setDays] = useState<Weekday[]>([...WEEKDAYS]);
  const [time, setTime] = useState("18:00");
  const [event, setEvent] = useState<RoutineEvent>("call.missed");
  const [delay, setDelay] = useState(5);
  const [verb, setVerb] = useState<"call" | "whatsapp">("call");
  const [employee, setEmployee] = useState(employees[0]?.id ?? "");
  const [audience, setAudience] = useState<Audience>("tomorrows_appointments");
  const [goal, setGoal] = useState<Goal>("confirm");
  const [approvalOver, setApprovalOver] = useState(25);
  const [preview, setPreview] = useState<DryRun | null>(null);

  // New leads are already called by their lead source (Connect): a routine may only WhatsApp.
  const leadOnly = kind === "event" && event === "lead.created";
  const action = leadOnly ? "whatsapp" : verb;
  const spec: RoutineSpec = {
    trigger: kind === "schedule" ? { type: "schedule", days, time } : { type: "event", event, delay_minutes: delay },
    audience: kind === "schedule" ? audience : null,
    action: { verb: action, employee_id: employee, goal },
    approval_over: approvalOver,
  };
  const employeeName = employees.find((e) => e.id === employee)?.name ?? "";
  const toggleDay = (d: Weekday) =>
    setDays((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : WEEKDAYS.filter((x) => cur.includes(x) || x === d)));

  if (employees.length === 0) return <p className="text-text-muted">{t("needEmployee")}</p>;

  return (
    <section aria-labelledby="builder-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="builder-title" className="text-lg font-semibold">
        {t("builderTitle")}
      </h2>
      <div className="mt-4 flex flex-col gap-3 text-[15px]">
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label={t("triggerLabel")} className={selectClass} value={kind} onChange={(e) => setKind(e.target.value as "schedule" | "event")}>
            <option value="schedule">{t("every")}</option>
            <option value="event">{t("whenEvent")}</option>
          </select>
          {kind === "schedule" ? (
            <>
              <div role="group" aria-label={t("daysLabel")} className="flex flex-wrap gap-1">
                {WEEKDAYS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={days.includes(d)}
                    onClick={() => toggleDay(d)}
                    className={cn(
                      "focus-ring h-9 rounded-full border px-3 text-sm",
                      days.includes(d) ? "border-brand-600 bg-brand-50 text-brand-700" : "text-text-muted",
                    )}
                  >
                    {t(`days.${d}`)}
                  </button>
                ))}
              </div>
              <span>{t("at")}</span>
              <Input aria-label={t("timeLabel")} type="time" className="w-32" value={time} onChange={(e) => setTime(e.target.value)} />
            </>
          ) : (
            <>
              <select aria-label={t("eventLabel")} className={selectClass} value={event} onChange={(e) => setEvent(e.target.value as RoutineEvent)}>
                {EVENTS.map((x) => (
                  <option key={x} value={x}>
                    {t(`events.${x}`)}
                  </option>
                ))}
              </select>
              <span>{t("after")}</span>
              <select aria-label={t("delayLabel")} className={selectClass} value={delay} onChange={(e) => setDelay(Number(e.target.value))}>
                {[0, 2, 5, 30, 60, 1440].map((m) => (
                  <option key={m} value={m}>
                    {t("minutes", { n: m })}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label={t("employeeLabel")} className={selectClass} value={employee} onChange={(e) => setEmployee(e.target.value)}>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <select aria-label={t("verbLabel")} className={selectClass} value={action} onChange={(e) => setVerb(e.target.value as "call" | "whatsapp")}>
            <option value="call" disabled={leadOnly}>
              {t("verbs.call")}
            </option>
            <option value="whatsapp">{t("verbs.whatsapp")}</option>
          </select>
          {kind === "schedule" && (
            <select aria-label={t("audienceLabel")} className={selectClass} value={audience} onChange={(e) => setAudience(e.target.value as Audience)}>
              {AUDIENCES.map((x) => (
                <option key={x} value={x}>
                  {t(`audiences.${x}`)}
                </option>
              ))}
            </select>
          )}
          <span>{t("toGoal")}</span>
          <select aria-label={t("goalLabel")} className={selectClass} value={goal} onChange={(e) => setGoal(e.target.value as Goal)}>
            {GOALS.map((x) => (
              <option key={x} value={x}>
                {t(`goals.${x}`)}
              </option>
            ))}
          </select>
        </div>
        <label className="flex flex-wrap items-center gap-2 text-sm text-text-muted">
          {t("askFirstOver")}
          <Input type="number" min={0} max={10000} className="w-24" value={approvalOver} onChange={(e) => setApprovalOver(Math.max(0, Math.floor(Number(e.target.value) || 0)))} />
          {t("people")}
        </label>
        <p className="rounded-lg bg-surface-2 p-3 font-medium">{sentence(spec, employeeName)}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Input aria-label={t("nameLabel")} placeholder={t("nameLabel")} className="max-w-xs" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          <Button
            variant="secondary"
            disabled={pending || (kind === "schedule" && days.length === 0)}
            onClick={() =>
              start(async () => {
                const res = await dryRun(spec);
                if (res.ok) setPreview(res.data);
                else toast.error(t("error"));
              })
            }
          >
            {t("dryRun")}
          </Button>
          <Button
            disabled={pending || !name.trim() || (kind === "schedule" && days.length === 0)}
            onClick={() =>
              start(async () => {
                const res = await saveRoutine(name, spec, true);
                if (!res.ok) {
                  toast.error(t("error"));
                  return;
                }
                toast.success(t("saved"));
                setName("");
                setPreview(null);
              })
            }
          >
            {t("turnOn")}
          </Button>
        </div>
        {preview && <DryRunList preview={preview} />}
      </div>
    </section>
  );
}

function DryRunList({ preview }: { preview: DryRun }) {
  const t = useTranslations("routines");
  if (preview.note === "event") return <p className="text-sm text-text-muted">{t("eventPreview")}</p>;
  return (
    <div className="rounded-lg border p-3" aria-live="polite">
      <p className="font-medium">{t("wouldContact", { n: preview.would_contact.length })}</p>
      {preview.needs_approval && <p className="text-sm text-amber-700">{t("willAsk")}</p>}
      <ul className="mt-2 flex flex-wrap gap-2 text-sm">
        {preview.would_contact.map((p) => (
          <li key={p.contact_id} className="rounded-md bg-surface-2 px-2 py-0.5">
            {p.name ?? t("customer")} · …{p.last4}
          </li>
        ))}
      </ul>
      {preview.skipped.length > 0 && (
        <>
          <p className="mt-3 text-sm text-text-muted">{t("skippedCount", { n: preview.skipped.length })}</p>
          <ul className="mt-1 flex flex-wrap gap-2 text-sm text-text-muted">
            {preview.skipped.map((p) => (
              <li key={p.contact_id} className="rounded-md border px-2 py-0.5">
                {p.name ?? t("customer")} · …{p.last4} · {t(`skip.${p.skip ?? "other"}`)}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
