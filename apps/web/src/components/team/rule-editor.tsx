"use client";

import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { addRule, removeRule, setRuleEnabled } from "@/app/(app)/team/actions";
import { Button } from "@/components/ui/button";
import {
  CHANNELS,
  RULE_RESULTS,
  TASKS,
  type HandoffRule,
  type RuleResult,
  type TeamChannel,
  type TeamMember,
  type TeamTask,
} from "@/lib/team/types";

export const selectClass =
  "focus-ring h-10 rounded-lg border border-input bg-surface px-2 text-[15px] disabled:opacity-60";
const DELAYS = [0, 10, 60, 1440, 10080];
const STAFF = "staff";

export function useDelayLabel() {
  const t = useTranslations("teamMap");
  return (minutes: number) =>
    minutes === 0
      ? t("delay.now")
      : minutes < 60
        ? t("delay.minutes", { n: minutes })
        : minutes < 1440
          ? t("delay.hours", { n: Math.round(minutes / 60) })
          : t("delay.days", { n: Math.round(minutes / 1440) });
}

/** TEAM-02: hand-offs written as sentences, chosen from dropdowns. */
export function RuleEditor({
  teamId,
  members,
  rules,
}: {
  teamId: string | null;
  members: TeamMember[];
  rules: HandoffRule[];
}) {
  const t = useTranslations("teamMap");
  const delayLabel = useDelayLabel();
  const [pending, start] = useTransition();
  const first = members[0]?.employee_id ?? "";
  const [from, setFrom] = useState(first);
  const [result, setResult] = useState<RuleResult>("interested");
  const [to, setTo] = useState(members[1]?.employee_id ?? first);
  const [task, setTask] = useState<TeamTask>("follow_up");
  const [channel, setChannel] = useState<TeamChannel>("call");
  const [delay, setDelay] = useState(10);
  const name = (id: string | null) => members.find((m) => m.employee_id === id)?.name ?? t("someone");

  const sentence = (r: Pick<HandoffRule, "from_employee_id" | "when_result" | "to_employee_id" | "task" | "channel" | "delay_minutes">) =>
    r.to_employee_id === null
      ? t("sentenceStaff", { from: name(r.from_employee_id), result: t(`results.${r.when_result}`) })
      : t("sentence", {
          from: name(r.from_employee_id),
          result: t(`results.${r.when_result}`),
          to: name(r.to_employee_id),
          task: t(`tasks.${r.task}`),
          channel: t(`channels.${r.channel}`),
          delay: delayLabel(r.delay_minutes),
        });

  const act = (fn: () => Promise<{ ok: boolean }>, success?: string) =>
    start(async () => {
      const res = await fn();
      if (!res.ok) toast.error(t("error"));
      else if (success) toast.success(success);
    });

  const toStaff = to === STAFF;
  return (
    <section aria-labelledby="rules-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="rules-title" className="text-lg font-semibold">
        {t("rulesTitle")}
      </h2>
      <p className="mt-1 text-sm text-text-muted">{t("rulesHint")}</p>
      <ul className="mt-4 flex flex-col divide-y">
        {rules.map((rule) => (
          <li key={rule.id} className="flex items-start gap-3 py-3">
            <input
              type="checkbox"
              className="mt-1 size-5 accent-brand-600"
              checked={rule.enabled}
              disabled={pending}
              aria-label={t("ruleOn")}
              onChange={(e) => act(() => setRuleEnabled(rule.id, e.target.checked))}
            />
            <p className={rule.enabled ? "flex-1" : "flex-1 text-text-muted line-through"}>
              {sentence(rule)}
              <span className="ms-2 text-xs text-text-subtle">{t("passedCount", { n: rule.handoffs_7d })}</span>
            </p>
            <Button
              variant="ghost"
              size="icon"
              disabled={pending}
              aria-label={t("removeRule")}
              onClick={() => act(() => removeRule(rule.id))}
            >
              <Trash2 aria-hidden />
            </Button>
          </li>
        ))}
        {rules.length === 0 && <li className="py-3 text-text-muted">{t("noRules")}</li>}
      </ul>

      {members.length > 0 && (
        <form
          className="mt-4 flex flex-wrap items-center gap-2 rounded-lg bg-surface-2 p-3 text-[15px]"
          onSubmit={(e) => {
            e.preventDefault();
            act(
              () =>
                addRule({
                  team_id: teamId,
                  from_employee_id: from,
                  when_result: result,
                  to_employee_id: toStaff ? null : to,
                  task: toStaff ? "brief_staff" : task,
                  channel: toStaff ? "whatsapp" : channel,
                  delay_minutes: toStaff ? 0 : delay,
                }),
              t("ruleAdded"),
            );
          }}
        >
          <span>{t("when")}</span>
          <select aria-label={t("fromLabel")} className={selectClass} value={from} onChange={(e) => setFrom(e.target.value)}>
            {members.map((m) => (
              <option key={m.employee_id} value={m.employee_id}>
                {m.name}
              </option>
            ))}
          </select>
          <span>{t("finds")}</span>
          <select aria-label={t("resultLabel")} className={selectClass} value={result} onChange={(e) => setResult(e.target.value as RuleResult)}>
            {RULE_RESULTS.map((r) => (
              <option key={r} value={r}>
                {t(`results.${r}`)}
              </option>
            ))}
          </select>
          <span>{t("passTo")}</span>
          <select aria-label={t("toLabel")} className={selectClass} value={to} onChange={(e) => setTo(e.target.value)}>
            {members.map((m) => (
              <option key={m.employee_id} value={m.employee_id}>
                {m.name}
              </option>
            ))}
            <option value={STAFF}>{t("myStaff")}</option>
          </select>
          {!toStaff && (
            <>
              <span>{t("to")}</span>
              <select aria-label={t("taskLabel")} className={selectClass} value={task} onChange={(e) => setTask(e.target.value as TeamTask)}>
                {TASKS.filter((x) => x !== "brief_staff").map((x) => (
                  <option key={x} value={x}>
                    {t(`tasks.${x}`)}
                  </option>
                ))}
              </select>
              <select aria-label={t("channelLabel")} className={selectClass} value={channel} onChange={(e) => setChannel(e.target.value as TeamChannel)}>
                {CHANNELS.map((x) => (
                  <option key={x} value={x}>
                    {t(`channels.${x}`)}
                  </option>
                ))}
              </select>
              <select aria-label={t("delayLabel")} className={selectClass} value={delay} onChange={(e) => setDelay(Number(e.target.value))}>
                {DELAYS.map((d) => (
                  <option key={d} value={d}>
                    {delayLabel(d)}
                  </option>
                ))}
              </select>
            </>
          )}
          <Button type="submit" disabled={pending || !from} className="ms-auto">
            {t("addRule")}
          </Button>
        </form>
      )}
    </section>
  );
}
