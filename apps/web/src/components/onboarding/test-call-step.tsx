"use client";

import { Check, Info, Phone, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState, useTransition } from "react";
import { getTestCall, sendCorrection, startTestCall } from "@/app/onboarding/actions";
import { EmployeeAvatar } from "@/components/mitra/employee-avatar";
import { LiveDot } from "@/components/mitra/live-dot";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TestCall, TestCallStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { StepFooter } from "./step-footer";

const STATUSES: TestCallStatus[] = ["queued", "ringing", "connected", "completed"];
const POLL_MS = 1000;
const MAX_POLL_FAILURES = 5;

interface TestCallStepProps {
  employeeName: string;
  maskedPhone: string;
}

export function TestCallStep({ employeeName, maskedPhone }: TestCallStepProps) {
  const t = useTranslations("onboarding");
  const tc = useTranslations("onboarding.test");
  const fixId = useId();
  const [call, setCall] = useState<TestCall | null>(null);
  const [failed, setFailed] = useState(false);
  const [connectedAt, setConnectedAt] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [fix, setFix] = useState("");
  const [fixError, setFixError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string[]>([]);
  const [starting, startStarting] = useTransition();
  const [fixing, startFixing] = useTransition();
  const failures = useRef(0);

  const status = call?.status ?? null;
  const completed = status === "completed";

  // Poll the call until it completes.
  useEffect(() => {
    if (!call || completed) return;
    const timer = window.setTimeout(async () => {
      const result = await getTestCall(call.id);
      if (result.ok) {
        failures.current = 0;
        setCall(result.data);
        if (result.data.status === "connected" || result.data.status === "completed") {
          setConnectedAt((at) => at ?? Date.now());
        }
      } else if (++failures.current >= MAX_POLL_FAILURES) {
        setFailed(true);
        setCall(null);
      } else {
        setCall({ ...call });
      }
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [call, completed]);

  // While connected, reveal transcript lines as their time arrives.
  useEffect(() => {
    if (status !== "connected") return;
    const timer = window.setInterval(() => setNow(Date.now()), 300);
    return () => window.clearInterval(timer);
  }, [status]);

  const transcript = call?.transcript ?? [];
  const elapsed = connectedAt && now ? now - connectedAt : 0;
  const visible = completed ? transcript : transcript.filter((line) => line.at_ms <= elapsed);

  function start() {
    setFailed(false);
    setApplied([]);
    setConnectedAt(null);
    setNow(0);
    failures.current = 0;
    startStarting(async () => {
      const result = await startTestCall();
      if (result.ok) setCall(result.data);
      else setFailed(true);
    });
  }

  function submitFix(event: React.FormEvent) {
    event.preventDefault();
    if (!call) return;
    if (!fix.trim()) {
      setFixError(tc("fixRequired"));
      return;
    }
    setFixError(null);
    startFixing(async () => {
      const result = await sendCorrection(call.id, fix.trim());
      if (!result.ok) {
        setFixError(t(`errors.${result.error}`));
        return;
      }
      setApplied((list) => [...list, result.data.applied_to === "knowledge" ? tc("fixKnowledge") : tc("fixBehaviour")]);
      setFix("");
    });
  }

  return (
    <div>
      <section className="rounded-2xl border bg-card p-5 shadow-xs md:p-8">
        <div className="flex flex-col items-center gap-5 text-center">
          <EmployeeAvatar name={employeeName} size="lg" speaking={status === "connected"} />
          {!call ? (
            <Button size="lg" className="h-16 w-full max-w-sm text-[17px]" onClick={start} disabled={starting} aria-busy={starting}>
              <Phone aria-hidden />
              {tc("call", { phone: maskedPhone })}
            </Button>
          ) : (
            <ol className="flex w-full max-w-md items-start justify-between gap-1" aria-label={tc(`status.${call.status}`)}>
              {STATUSES.map((step, index) => {
                const reached = STATUSES.indexOf(call.status) >= index;
                const current = call.status === step;
                return (
                  <li key={step} className="flex flex-1 flex-col items-center gap-1.5">
                    <span
                      aria-hidden
                      className={cn(
                        "inline-flex size-7 items-center justify-center rounded-full border-2 border-border",
                        reached && "border-brand-600 bg-brand-600 text-on-brand",
                        current && step !== "completed" && "border-sky-400 bg-sky-100 text-sky-ink",
                      )}
                    >
                      {current && step === "connected" ? (
                        <LiveDot />
                      ) : reached && (!current || step === "completed") ? (
                        <Check className="size-4" strokeWidth={2.5} />
                      ) : null}
                    </span>
                    <span className={cn("text-xs leading-4 font-medium", current ? "text-foreground" : "text-text-muted")}>
                      {tc(`status.${step}`)}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          <p role="status" aria-live="polite" className="text-lg leading-[26px] font-semibold">
            {call ? tc(`status.${call.status}`) : null}
          </p>
          <p className="flex items-center gap-2 text-sm leading-5 text-text-muted">
            <Info className="size-4 shrink-0" aria-hidden />
            {tc("simulatedNote")}
          </p>
        </div>
      </section>

      {failed && (
        <p role="alert" className="mt-4 rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
          {tc("failed")}
        </p>
      )}

      {visible.length > 0 && (
        <section aria-labelledby="said-title" className="mt-6">
          <h2 id="said-title" className="mb-3 text-[22px] leading-7 font-semibold">
            {tc("whatWasSaid")}
          </h2>
          <ol className="flex flex-col gap-3" aria-live="polite">
            {visible.map((line, index) => {
              const employee = line.speaker === "employee";
              return (
                <li
                  key={`${line.at_ms}-${index}`}
                  className={cn("flex max-w-[85%] flex-col gap-1 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1", employee ? "self-end items-end" : "self-start items-start")}
                >
                  <span className="px-1 text-xs leading-4 font-medium text-text-muted">{employee ? employeeName : tc("you")}</span>
                  <p className={cn("rounded-2xl px-4 py-2.5 leading-6", employee ? "rounded-br-md bg-brand-50" : "rounded-bl-md border bg-surface")}>
                    {line.text}
                  </p>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {completed && call && (
        <>
          {call.summary && (
            <section aria-labelledby="summary-title" className="mt-6 rounded-xl border bg-card p-5 shadow-xs">
              <h2 id="summary-title" className="font-semibold">
                {tc("summary")}
              </h2>
              <p className="mt-1 text-text-muted">{call.summary}</p>
            </section>
          )}
          <form onSubmit={submitFix} noValidate className="mt-4 flex flex-col gap-2 rounded-xl border bg-card p-5 shadow-xs">
            <label htmlFor={fixId} className="font-semibold">
              {tc("fixTitle")}
            </label>
            <p className="text-sm leading-5 text-text-muted">{tc("fixHint", { name: employeeName })}</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id={fixId}
                value={fix}
                onChange={(event) => setFix(event.target.value)}
                placeholder={tc("fixPlaceholder")}
                maxLength={500}
                aria-invalid={fixError ? true : undefined}
                className="sm:flex-1"
              />
              <Button type="submit" variant="secondary" disabled={fixing} aria-busy={fixing}>
                {tc("fixSubmit")}
              </Button>
            </div>
            {fixError && (
              <p role="alert" className="text-sm leading-5 font-medium text-danger-fg">
                {fixError}
              </p>
            )}
            {applied.length > 0 && (
              <ul className="mt-1 flex flex-col gap-1" aria-live="polite">
                {applied.map((note, index) => (
                  <li key={index} className="flex items-center gap-2 text-sm leading-5 font-medium text-success-fg">
                    <Check className="size-4" aria-hidden />
                    {note}
                  </li>
                ))}
              </ul>
            )}
          </form>
        </>
      )}

      <StepFooter backHref="/onboarding?step=voice">
        {completed || failed ? (
          <>
            <Button variant="secondary" onClick={start} disabled={starting}>
              <RotateCcw aria-hidden />
              {tc("testAgain")}
            </Button>
            {completed && (
              <Button asChild size="lg" className="w-full md:w-auto md:min-w-48">
                <Link href="/onboarding?step=go_live">{tc("looksGood")}</Link>
              </Button>
            )}
          </>
        ) : (
          <Button asChild variant="ghost" className="text-text-muted">
            <Link href="/onboarding?step=go_live">{t("skip")}</Link>
          </Button>
        )}
      </StepFooter>
    </div>
  );
}
