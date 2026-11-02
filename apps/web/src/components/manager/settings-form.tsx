"use client";

import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { saveManagerSettings } from "@/lib/manager/actions";
import { ALERT_KINDS, type ManagerSettings } from "@/lib/manager/types";

const selectClass = "focus-ring h-11 rounded-lg border border-input bg-surface px-3 text-base md:text-[15px]";

/** Who gets the morning report and instant alerts, when, and in which language. */
export function ManagerSettingsForm({ initial }: { initial: ManagerSettings }) {
  const t = useTranslations("managerSettings");
  const [enabled, setEnabled] = useState(initial.report_enabled);
  const [time, setTime] = useState(initial.report_time.slice(0, 5));
  const [language, setLanguage] = useState(initial.language ?? "");
  // Empty list on the server = everyone; the form shows that as all boxes ticked.
  const everyone = initial.people.map((p) => p.user_id);
  const [reportIds, setReportIds] = useState(initial.report_user_ids.length ? initial.report_user_ids : everyone);
  const [alertIds, setAlertIds] = useState(initial.alert_user_ids.length ? initial.alert_user_ids : everyone);
  const [kinds, setKinds] = useState(initial.alert_kinds);
  const [pending, start] = useTransition();

  const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  const narrowed = (ids: string[]) => (ids.length === everyone.length ? [] : ids);

  const save = () =>
    start(async () => {
      const result = await saveManagerSettings({
        report_enabled: enabled,
        report_time: time,
        language: language === "" ? null : (language as "en" | "hi" | "te"),
        report_user_ids: narrowed(reportIds),
        alert_user_ids: narrowed(alertIds),
        alert_kinds: kinds,
      });
      if (result.ok) toast.success(t("saved"));
      else toast.error(t(`errors.${result.error}`));
    });

  const people = (ids: string[], set: (ids: string[]) => void, name: "reportPeople" | "alertPeople") => (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 font-medium">{t(name)}</legend>
      {initial.people.map((p) => (
        <label key={p.user_id} className="flex items-center gap-3">
          <input
            type="checkbox"
            className="size-5"
            checked={ids.includes(p.user_id)}
            onChange={() => set(toggle(ids, p.user_id))}
          />
          <span>
            {p.name ?? t("unnamed")} · {t.has(`roles.${p.role}` as never) ? t(`roles.${p.role}` as never) : p.role} · …{p.phone_last4}
          </span>
        </label>
      ))}
    </fieldset>
  );

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <h2 className="text-lg leading-[26px] font-semibold">{t("reportTitle")}</h2>
        <label className="flex items-center gap-3">
          <input type="checkbox" className="size-5" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span>{t("reportEnabled")}</span>
        </label>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="report-time">{t("reportTime")}</Label>
          <Input id="report-time" type="time" className="w-36" value={time} disabled={!enabled} onChange={(e) => setTime(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="report-language">{t("language")}</Label>
          <select id="report-language" className={selectClass} value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="">{t("languageAuto")}</option>
            <option value="te">తెలుగు</option>
            <option value="hi">हिन्दी</option>
            <option value="en">English</option>
          </select>
        </div>
        {people(reportIds, setReportIds, "reportPeople")}
      </section>

      <section className="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-xs md:p-6">
        <h2 className="text-lg leading-[26px] font-semibold">{t("alertsTitle")}</h2>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 font-medium">{t("alertKinds")}</legend>
          {ALERT_KINDS.map((kind) => (
            <label key={kind} className="flex items-center gap-3">
              <input type="checkbox" className="size-5" checked={kinds.includes(kind)} onChange={() => setKinds(toggle(kinds, kind))} />
              <span>{t(`kinds.${kind}`)}</span>
            </label>
          ))}
        </fieldset>
        {people(alertIds, setAlertIds, "alertPeople")}
      </section>

      <div>
        <Button disabled={pending || (reportIds.length === 0 && enabled)} onClick={save}>
          {t("save")}
        </Button>
      </div>
    </div>
  );
}
