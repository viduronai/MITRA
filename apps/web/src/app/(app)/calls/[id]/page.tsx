import { AlertTriangle, ArrowLeft, CheckCircle2, CircleHelp, Play, XCircle } from "lucide-react";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { CallRatingCard, TeachFromCall } from "@/components/calls/call-feedback";
import { EmptyState } from "@/components/mitra/empty-state";
import { ResultPill } from "@/components/mitra/result-pill";
import { localeLabels } from "@/i18n/config";
import { callerLabel, summaryBullets, uiResult } from "@/lib/calls";
import { getCall, validId } from "@/lib/calls-data";
import { formatLongDate, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export async function generateMetadata() {
  const t = await getTranslations("calls");
  return { title: t("title") };
}

function humanKey(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function Card({ title, id, children }: { title: string; id: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-xl border bg-card p-5 shadow-xs">
      <h2 id={id} className="text-lg leading-[26px] font-semibold">
        {title}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export default async function CallDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [t, tCall, locale, call] = await Promise.all([
    getTranslations("callDetail"),
    getTranslations("call"),
    getLocale(),
    getCall(validId(id)),
  ]);
  if (!call) {
    return <EmptyState icon={AlertTriangle} description={t("error")} />;
  }
  const employeeName = call.employee_name ?? "Mitra";
  const caller = callerLabel(call.contact_name, call.phone_last4, tCall("web"));
  const started = new Date(call.started_at);
  const seconds = call.duration_seconds ?? 0;
  const bullets = summaryBullets(call.summary);
  const fields = Object.entries(call.fields).filter(([key]) => key !== "name");
  const firstQuestion = call.unknown_questions[0] ?? null;

  return (
    <>
      <Link
        href="/calls"
        className="focus-ring mb-4 inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-text-muted hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t("back")}
      </Link>

      <header className="mb-6 flex flex-col gap-3 md:mb-8 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">
            {call.contact_id ? (
              <Link href={`/customers/${call.contact_id}`} className="focus-ring rounded-md hover:underline">
                {caller}
              </Link>
            ) : (
              caller
            )}
          </h1>
          <p className="mt-1.5 text-text-muted">
            {formatLongDate(started, locale)} · {formatTime(started, locale)} ·{" "}
            {tCall("duration", { minutes: Math.floor(seconds / 60), seconds: seconds % 60 })} ·{" "}
            {t("handledBy", { name: employeeName })}
            {call.language && ` · ${localeLabels[call.language].name}`}
          </p>
        </div>
        <ResultPill result={uiResult(call.result)} className="self-start md:self-auto" />
      </header>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-6">
          {/* Player placeholder until recordings are stored (CALL-11). */}
          <section
            aria-label={t("recording")}
            className="flex items-center gap-4 rounded-xl border border-dashed bg-card p-4"
          >
            <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-surface-2 text-text-subtle">
              <Play className="size-5" aria-hidden />
            </span>
            <p className="text-sm text-text-muted">{t("recordingSoon")}</p>
          </section>

          <Card title={t("summary")} id="summary-title">
            {bullets.length === 0 ? (
              <p className="text-text-muted">{t("processing", { name: employeeName })}</p>
            ) : (
              <ul className="flex list-disc flex-col gap-1.5 pl-5 leading-6">
                {bullets.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
            {call.next_step && (
              <p className="mt-3 text-sm">
                <span className="font-medium">{t("nextStep")}:</span> {call.next_step}
              </p>
            )}
          </Card>

          <Card title={t("transcript")} id="transcript-title">
            {call.transcript.length === 0 ? (
              <p className="text-text-muted">{t("noTranscript")}</p>
            ) : (
              <ol className="flex flex-col gap-2.5">
                {call.transcript.map((line, index) => {
                  const mine = line.speaker === "employee";
                  return (
                    <li key={index} className={cn("flex", mine ? "justify-start" : "justify-end")}>
                      <div
                        className={cn(
                          "max-w-[85%] rounded-2xl px-4 py-2.5 leading-6",
                          mine ? "rounded-bl-md bg-surface-2" : "rounded-br-md bg-brand-50 text-foreground",
                        )}
                      >
                        <span className="sr-only">{mine ? employeeName : caller}: </span>
                        {line.text}
                        {line.interrupted && (
                          <span className="ml-1.5 text-[12px] text-text-subtle">({t("interrupted")})</span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <Card title={t("collected")} id="collected-title">
            {fields.length === 0 ? (
              <p className="text-text-muted">{t("noFields")}</p>
            ) : (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
                {fields.map(([key, value]) => (
                  <div key={key} className="contents">
                    <dt className="text-text-muted">{humanKey(key)}</dt>
                    <dd className="font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </Card>

          <Card title={t("actions")} id="actions-title">
            {call.actions.length === 0 ? (
              <p className="text-text-muted">{t("noActions")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {call.actions.map((action, index) => (
                  <li key={index} className="flex items-start gap-2 leading-6">
                    {action.ok ? (
                      <CheckCircle2 className="mt-1 size-4 shrink-0 text-success-fg" aria-hidden />
                    ) : (
                      <XCircle className="mt-1 size-4 shrink-0 text-danger-fg" aria-hidden />
                    )}
                    {action.label}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {call.unknown_questions.length > 0 && (
            <Card title={t("unknownQuestions", { name: employeeName })} id="unknown-title">
              <ul className="flex flex-col gap-2">
                {call.unknown_questions.map((q) => (
                  <li key={q} className="flex items-start gap-2 leading-6">
                    <CircleHelp className="mt-1 size-4 shrink-0 text-sky-ink" aria-hidden />
                    {q}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <CallRatingCard callId={call.id} employeeName={employeeName} initial={call.rating} />
          <TeachFromCall callId={call.id} employeeName={employeeName} question={firstQuestion} />
        </div>
      </div>
    </>
  );
}
