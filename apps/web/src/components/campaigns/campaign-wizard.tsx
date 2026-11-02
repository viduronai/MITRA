"use client";

import { ArrowLeft, ArrowRight, Check, Play, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { createCampaign, previewList, type CampaignErrorKey } from "@/app/(app)/campaigns/actions";
import { ListInput } from "@/components/campaigns/list-input";
import { LADDERS, ScheduleFields, type Schedule } from "@/components/campaigns/schedule-fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ListPreview } from "@/lib/campaigns/types";
import { cn } from "@/lib/utils";

const STEPS = ["list", "columns", "schedule", "review"] as const;
type Step = (typeof STEPS)[number];
const VAR = /^[a-z][a-z0-9_]{0,39}$/;
const selectClass =
  "focus-ring h-12 w-full rounded-lg border border-input bg-surface px-3 text-[15px] disabled:opacity-50";

interface EmployeeOption {
  id: string;
  name: string;
}

function ErrorLine({ error, message }: { error: CampaignErrorKey | "tooBig" | "badVariable" | null; message?: string }) {
  const t = useTranslations("campaigns.errors");
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
      {t(error)}
      {message && error === "invalidList" ? ` (${message})` : null}
    </p>
  );
}

export function CampaignWizard({ employees, channels }: { employees: EmployeeOption[]; channels: number }) {
  const t = useTranslations("campaigns.wizard");
  const router = useRouter();
  const ids = { name: useId(), employee: useId(), phone: useId(), nameCol: useId(), purpose: useId(), skip: useId() };
  const [step, setStep] = useState<Step>("list");
  const [name, setName] = useState("");
  const [employeeId, setEmployeeId] = useState(employees[0]?.id ?? "");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<ListPreview | null>(null);
  const [columnMap, setColumnMap] = useState<Record<string, string>>({});
  const [purpose, setPurpose] = useState<"service" | "promotional">("service");
  const [skipDays, setSkipDays] = useState(7);
  const [schedule, setSchedule] = useState<Schedule>({
    calling_days: [0, 1, 2, 3, 4, 5],
    holidays: [],
    ends_on: null,
    retry_ladder: LADDERS.standard,
  });
  const [error, setError] = useState<{ key: CampaignErrorKey | "tooBig" | "badVariable"; message?: string } | null>(null);
  const [pending, startTransition] = useTransition();
  const index = STEPS.indexOf(step);

  const runPreview = (overrides: { phone_column?: string; name_column?: string | null; resetMap?: boolean; fresh?: boolean } = {}) => {
    setError(null);
    startTransition(async () => {
      const base = overrides.fresh ? null : preview;
      const res = await previewList({
        text,
        phone_column: overrides.phone_column ?? base?.phone_column ?? null,
        name_column: overrides.name_column !== undefined ? overrides.name_column : (base?.name_column ?? null),
        column_map: overrides.resetMap || !base ? null : columnMap,
      });
      if (!res.ok) return setError({ key: res.error, message: res.message });
      setPreview(res.data);
      setColumnMap(res.data.column_map);
      if (!name) setName(t("defaultName"));
      setStep("columns");
    });
  };

  const submit = (start: boolean) => {
    if (!preview) return;
    setError(null);
    startTransition(async () => {
      const res = await createCampaign(
        {
          name,
          employee_id: employeeId,
          purpose,
          text,
          phone_column: preview.phone_column,
          name_column: preview.name_column,
          column_map: columnMap,
          skip_recent_days: skipDays,
          ...schedule,
        },
        start,
      );
      if (!res.ok) return setError({ key: res.error, message: res.message });
      toast.success(start ? t("started") : t("saved"));
      router.push(`/campaigns/${res.data.id}`);
    });
  };

  const badVariable = Object.values(columnMap).some((v) => !VAR.test(v));
  const eta = preview ? Math.ceil((preview.valid * 90) / Math.max(channels, 1) / 60) : 0;

  return (
    <div className="flex flex-col gap-6">
      <ol className="grid grid-cols-4 gap-2" aria-label={t("stepsLabel")}>
        {STEPS.map((s, i) => (
          <li key={s} aria-current={s === step ? "step" : undefined}>
            <span className={cn("block h-1.5 rounded-full", i <= index ? "bg-brand-500" : "bg-surface-2")} aria-hidden />
            <span className={cn("mt-2 block text-[13px] leading-5", s === step ? "font-medium" : "text-text-muted")}>
              {t(`steps.${s}`)}
            </span>
          </li>
        ))}
      </ol>

      <section className="flex flex-col gap-5 rounded-xl border bg-card p-4 shadow-xs md:p-6">
        {step === "list" && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={ids.name}>{t("name")}</Label>
                <Input id={ids.name} value={name} maxLength={80} placeholder={t("namePlaceholder")} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={ids.employee}>{t("employee")}</Label>
                <select id={ids.employee} className={selectClass} value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <ListInput value={text} onChange={setText} onTooBig={() => setError({ key: "tooBig" })} />
          </>
        )}

        {step === "columns" && preview && (
          <>
            <p className="text-sm leading-5">
              <span className="font-semibold text-success-fg">{t("valid", { count: preview.valid })}</span>
              {preview.invalid > 0 && <span className="text-danger-fg"> · {t("invalid", { count: preview.invalid })}</span>}
              {preview.duplicates > 0 && <span className="text-text-muted"> · {t("duplicates", { count: preview.duplicates })}</span>}
            </p>
            {preview.errors.length > 0 && (
              <p className="text-[13px] leading-5 text-text-muted">
                {t("badRows", { rows: preview.errors.slice(0, 10).map((e) => e.row_number).join(", ") })}
              </p>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={ids.phone}>{t("phoneColumn")}</Label>
                <select
                  id={ids.phone}
                  className={selectClass}
                  value={preview.phone_column}
                  disabled={pending}
                  onChange={(e) => runPreview({ phone_column: e.target.value, resetMap: true })}
                >
                  {preview.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={ids.nameCol}>{t("nameColumn")}</Label>
                <select
                  id={ids.nameCol}
                  className={selectClass}
                  value={preview.name_column ?? ""}
                  disabled={pending}
                  onChange={(e) => runPreview({ name_column: e.target.value || null, resetMap: true })}
                >
                  <option value="">{t("noName")}</option>
                  {preview.headers
                    .filter((h) => h !== preview.phone_column)
                    .map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                </select>
              </div>
            </div>
            <div>
              <h2 className="text-base leading-6 font-semibold">{t("mapTitle")}</h2>
              <p className="mt-1 text-[13px] leading-5 text-text-muted">{t("mapHint")}</p>
              <ul className="mt-3 divide-y rounded-lg border">
                {Object.entries(columnMap).map(([header, variable]) => (
                  <li key={header} className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                    <span className="text-sm font-medium">{header}</span>
                    <span className="flex items-center gap-1 font-mono text-[13px]">
                      {"{"}
                      <Input
                        aria-label={t("variableFor", { column: header })}
                        value={variable}
                        maxLength={40}
                        aria-invalid={!VAR.test(variable)}
                        className="h-9 w-44 font-mono text-[13px]"
                        onChange={(e) => setColumnMap({ ...columnMap, [header]: e.target.value.toLowerCase() })}
                      />
                      {"}"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            {preview.sample.length > 0 && (
              <div>
                <h2 className="text-base leading-6 font-semibold">{t("sampleTitle")}</h2>
                <ul className="mt-2 flex flex-col gap-1.5 text-[13px] leading-5">
                  {preview.sample.map((r) => (
                    <li key={r.row_number} className="rounded-lg bg-surface-2 px-3 py-2">
                      <span className="font-medium">{r.name ?? t("noNameRow")}</span>
                      <span className="text-text-muted"> · ••••{r.phone_last4}</span>
                      {Object.keys(r.variables).length > 0 && (
                        <span className="block text-text-muted">
                          {Object.entries(r.variables)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(" · ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        {step === "schedule" && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={ids.purpose}>{t("purpose")}</Label>
                <select
                  id={ids.purpose}
                  className={selectClass}
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value as "service" | "promotional")}
                >
                  {(["service", "promotional"] as const).map((p) => (
                    <option key={p} value={p}>
                      {t(`purposes.${p}`)}
                    </option>
                  ))}
                </select>
                <p className="text-[13px] leading-5 text-text-muted">{t(`purposeHints.${purpose}`)}</p>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={ids.skip}>{t("skipRecent")}</Label>
                <Input
                  id={ids.skip}
                  type="number"
                  min={0}
                  max={90}
                  value={skipDays}
                  onChange={(e) => setSkipDays(Math.min(90, Math.max(0, Number(e.target.value) || 0)))}
                />
                <p className="text-[13px] leading-5 text-text-muted">{t("skipRecentHint", { days: skipDays })}</p>
              </div>
            </div>
            <ScheduleFields value={schedule} onChange={setSchedule} />
          </>
        )}

        {step === "review" && preview && (
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {[
              [t("name"), name],
              [t("employee"), employees.find((e) => e.id === employeeId)?.name ?? ""],
              [t("people"), t("valid", { count: preview.valid })],
              [t("variables"), Object.values(columnMap).map((v) => `{${v}}`).join(" ") || "—"],
              [t("purpose"), t(`purposes.${purpose}`)],
              [t("eta"), t("etaValue", { minutes: eta, channels })],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-surface-2 px-3 py-2.5">
                <dt className="text-[13px] text-text-muted">{k}</dt>
                <dd className="mt-0.5 font-medium break-words">{v}</dd>
              </div>
            ))}
            <p className="text-[13px] leading-5 text-text-muted sm:col-span-2">{t("reviewNote")}</p>
          </dl>
        )}

        <ErrorLine error={error?.key ?? null} message={error?.message} />
      </section>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <Button
          type="button"
          variant="ghost"
          disabled={index === 0 || pending}
          onClick={() => setStep(STEPS[Math.max(0, index - 1)])}
        >
          <ArrowLeft aria-hidden />
          {t("back")}
        </Button>
        {step === "list" && (
          <Button type="button" disabled={!text.trim() || !employeeId || pending} aria-busy={pending} onClick={() => runPreview({ fresh: true })}>
            <Check aria-hidden />
            {t("check")}
          </Button>
        )}
        {(step === "columns" || step === "schedule") && (
          <Button
            type="button"
            disabled={pending || !preview?.valid || badVariable}
            onClick={() => {
              if (badVariable) return setError({ key: "badVariable" });
              setStep(STEPS[index + 1]);
            }}
          >
            {t("next")}
            <ArrowRight aria-hidden />
          </Button>
        )}
        {step === "review" && (
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button type="button" variant="secondary" disabled={pending || !name.trim()} onClick={() => submit(false)}>
              <Save aria-hidden />
              {t("saveDraft")}
            </Button>
            <Button type="button" disabled={pending || !name.trim()} aria-busy={pending} onClick={() => submit(true)}>
              <Play aria-hidden />
              {t("start")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
