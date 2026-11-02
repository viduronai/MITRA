"use client";

import { ChevronDown, FlaskConical, Send } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { pullIndiaMart, sendTestLead, updateLeadSource, type LeadResult } from "@/app/(app)/more/connect/lead-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { curlSnippet, formsSnippet, keyedUrl, sheetsSnippet, websiteFormSnippet } from "@/lib/leads/snippets";
import type { Lead, IntakeUrls, LeadSource, LeadSourcePatch } from "@/lib/leads/types";
import { cn } from "@/lib/utils";
import { CopyBlock } from "./copy-block";

const DELAYS = ["0", "300", "900", "3600", "never"] as const;
const SELECT =
  "h-12 w-full rounded-lg border border-input bg-surface px-4 text-base shadow-xs focus-visible:border-ring md:text-[15px]";

export type EmployeeOption = { id: string; name: string };

function Switch({ checked, label, disabled, onChange }: { checked: boolean; label: string; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "focus-ring relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors motion-fast disabled:opacity-60",
        checked ? "bg-primary" : "bg-border",
      )}
    >
      <span className={cn("inline-block size-5 rounded-full bg-white shadow-xs transition-transform motion-fast", checked ? "translate-x-6" : "translate-x-1")} />
    </button>
  );
}

function callTime(iso: string | null): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata", day: "numeric", month: "short" }).format(new Date(iso));
}

export function SourceCard({
  source,
  urls,
  secret,
  businessName,
  employees,
  lastLeadText,
}: {
  source: LeadSource;
  urls: IntakeUrls;
  secret: string | null;
  businessName: string;
  employees: EmployeeOption[];
  lastLeadText: string | null;
}) {
  const t = useTranslations("leads");
  const ids = useId();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [page, setPage] = useState(source.external_id ?? "");
  const [credential, setCredential] = useState("");
  const name = t(`sources.${source.kind}`);
  const on = source.connected ? source.enabled : false;

  const act = <T,>(action: () => Promise<LeadResult<T>>, onOk?: (data: T) => void) =>
    startTransition(async () => {
      const res = await action();
      if (!res.ok) {
        toast.error(t(`errors.${res.error}`));
        return;
      }
      onOk?.(res.data);
    });
  const save = (patch: LeadSourcePatch, done?: string) => act(() => updateLeadSource(source.kind, patch), () => done && toast.success(done));
  const leadStatus = (lead: Lead) => t(`status.${lead.status}`, { time: callTime(lead.call_at), reason: lead.reason_text[0] ?? "" });

  const status = !source.connected || !source.enabled ? (source.connected ? t("off") : t("noLeads")) : lastLeadText ? t("lastLead", { time: lastLeadText }) : t("noLeads");
  const delay = source.auto_call ? String(source.call_delay_seconds) : "never";

  return (
    <li className="rounded-xl border bg-card p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="font-semibold">{name}</h3>
            {source.simulated && (
              <span className="inline-flex h-6 items-center gap-1 rounded-full bg-sky-100 px-2.5 text-xs font-medium text-sky-ink">
                <FlaskConical aria-hidden className="size-3.5" />
                {t("testMode")}
              </span>
            )}
          </div>
          <p className="text-sm leading-5 text-text-muted">
            {status}
            {source.lead_count > 0 && ` · ${t("count", { count: source.lead_count })}`}
          </p>
          {source.last_error && <p className="mt-1 text-sm leading-5 font-medium text-danger-fg">{t("problem", { message: source.last_error })}</p>}
        </div>
        <Switch checked={on} label={t("toggle", { source: name })} disabled={pending} onChange={(v) => save({ enabled: v })} />
      </div>

      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${ids}-body`}
        onClick={() => setOpen(!open)}
        className="focus-ring mt-3 inline-flex items-center gap-1 rounded-md text-sm font-medium text-brand-600 dark:text-brand-500"
      >
        {open ? t("hide") : t("setup")}
        <ChevronDown aria-hidden className={cn("size-4 transition-transform motion-fast", open && "rotate-180")} />
      </button>

      {open && (
        <div id={`${ids}-body`} className="mt-3 flex flex-col gap-4">
          <p className="text-sm leading-5">{t(`steps.${source.kind}`)}</p>
          <SetupDetails kind={source.kind} urls={urls} secret={secret} businessName={businessName} />

          {source.kind === "meta" && (
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${ids}-page`}>{t("metaPage")}</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input id={`${ids}-page`} inputMode="numeric" value={page} onChange={(e) => setPage(e.target.value)} />
                <Button variant="secondary" disabled={pending || !page.trim()} onClick={() => save({ external_id: page, enabled: true }, t("saved"))}>
                  {t("metaSave")}
                </Button>
              </div>
              {source.simulated && <p className="text-sm leading-5 text-text-muted">{t("metaSim")}</p>}
            </div>
          )}

          {source.kind === "indiamart" && (
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${ids}-key`}>{t("imKey")}</Label>
              {source.credential_hint && <p className="text-sm text-text-muted">{t("imSaved", { hint: source.credential_hint })}</p>}
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input id={`${ids}-key`} type="password" autoComplete="off" value={credential} onChange={(e) => setCredential(e.target.value)} />
                <Button
                  variant="secondary"
                  disabled={pending || credential.trim().length < 8}
                  onClick={() => save({ credential, enabled: true }, t("saved"))}
                >
                  {t("imSave")}
                </Button>
              </div>
              {source.credential_hint && (
                <Button
                  variant="secondary"
                  className="w-full sm:w-fit"
                  disabled={pending}
                  onClick={() =>
                    act(pullIndiaMart, (r) => (r.error ? toast.error(r.error) : toast.success(t("fetched", { created: r.created, duplicates: r.duplicates }))))
                  }
                >
                  {t("fetchNow")}
                </Button>
              )}
              {source.simulated && <p className="text-sm leading-5 text-text-muted">{t("imSim")}</p>}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${ids}-who`}>{t("whoCalls")}</Label>
              <select
                id={`${ids}-who`}
                className={SELECT}
                value={source.employee_id ?? ""}
                disabled={pending}
                onChange={(e) => save({ employee_id: e.target.value || null })}
              >
                <option value="">{t("anyone")}</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${ids}-when`}>{t("howSoon")}</Label>
              <select
                id={`${ids}-when`}
                className={SELECT}
                value={delay}
                disabled={pending}
                onChange={(e) =>
                  save(e.target.value === "never" ? { auto_call: false } : { auto_call: true, call_delay_seconds: Number(e.target.value) })
                }
              >
                {DELAYS.map((d) => (
                  <option key={d} value={d}>
                    {t(`delays.${d}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p id={`${ids}-wa`} className="font-medium">
                {t("headsUp")}
              </p>
              <p className="text-sm leading-5 text-text-muted">{t("headsUpHint")}</p>
            </div>
            <Switch checked={source.heads_up} label={t("headsUp")} disabled={pending} onChange={(v) => save({ heads_up: v })} />
          </div>

          <Button
            variant="secondary"
            className="w-full sm:w-fit"
            disabled={pending}
            aria-busy={pending}
            onClick={() => act(() => sendTestLead(source.kind), (r) => toast.success(t("testSent", { status: leadStatus(r.lead) })))}
          >
            <Send aria-hidden />
            {t("testLead")}
          </Button>
        </div>
      )}
    </li>
  );
}

function SetupDetails({ kind, urls, secret, businessName }: { kind: LeadSource["kind"]; urls: IntakeUrls; secret: string | null; businessName: string }) {
  const t = useTranslations("leads");
  const secretHeader = `X-Mitra-Secret: ${secret ?? "…"}`;
  switch (kind) {
    case "meta":
      return <CopyBlock label={t("metaWebhook")} value={urls.meta_webhook} />;
    case "website_form":
      return <CopyBlock label={t("code")} value={websiteFormSnippet(urls.form, businessName)} multiline />;
    case "google_sheets":
      return <CopyBlock label={t("code")} value={sheetsSnippet(urls.generic, secret)} multiline />;
    case "google_forms":
      return <CopyBlock label={t("code")} value={formsSnippet(urls.generic, secret)} multiline />;
    case "google_ads":
      return <CopyBlock label={t("url")} value={urls.google_ads} />;
    case "indiamart":
      return <CopyBlock label={t("url")} value={keyedUrl(urls.indiamart, secret)} />;
    case "justdial":
      return <CopyBlock label={t("url")} value={keyedUrl(urls.justdial, secret)} />;
    case "zapier":
    case "api":
      return (
        <>
          <CopyBlock label={t("url")} value={urls.generic} />
          <CopyBlock label={t("header")} value={secretHeader} />
          <CopyBlock label={t("code")} value={curlSnippet(urls.generic, secret, kind)} multiline />
        </>
      );
  }
}
