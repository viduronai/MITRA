"use client";

import { Link2, LoaderCircle, Mic, PenLine, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useId, useState, useTransition } from "react";
import { toast } from "sonner";
import {
  addSource,
  answerGap,
  confirmFact,
  editFact,
  finishTeach,
  getTeachState,
  removeFact,
  type StepErrorKey,
  type TeachState,
} from "@/app/onboarding/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Fact, Gap } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { GapQuestions, KnowledgeCards } from "./knowledge-cards";
import { StepFooter } from "./step-footer";

type Mode = "url" | "text";
const POLL_MS = 1500;

function OptionCard({
  icon: Icon,
  title,
  hint,
  selected,
  disabled,
  badge,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  hint: string;
  selected?: boolean;
  disabled?: boolean;
  badge?: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={disabled ? undefined : selected}
      className={cn(
        "focus-ring flex min-h-32 flex-col items-start gap-2 rounded-xl border bg-card p-4 text-left shadow-xs transition-[border-color,background-color] motion-fast hover:border-brand-500/50 md:p-5",
        selected && "border-brand-500 bg-brand-50 hover:border-brand-500",
        disabled && "cursor-not-allowed opacity-70 hover:border-border",
      )}
    >
      <span className="flex w-full items-start justify-between gap-2">
        <span
          aria-hidden
          className={cn(
            "inline-flex size-11 items-center justify-center rounded-full",
            selected ? "bg-brand-600 text-on-brand" : "bg-surface-2 text-text-muted",
          )}
        >
          <Icon className="size-5" strokeWidth={1.75} />
        </span>
        {badge && (
          <span className="inline-flex h-6 items-center rounded-full bg-sky-100 px-2.5 text-xs font-medium whitespace-nowrap text-sky-ink">
            {badge}
          </span>
        )}
      </span>
      <span className="font-semibold">{title}</span>
      <span className="text-sm leading-5 text-text-muted">{hint}</span>
    </button>
  );
}

export function TeachStep({ initial }: { initial: TeachState }) {
  const t = useTranslations("onboarding");
  const tt = useTranslations("onboarding.teach");
  const inputId = useId();
  const [state, setState] = useState(initial);
  const [mode, setMode] = useState<Mode | null>(initial.facts.length ? null : "url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [error, setError] = useState<StepErrorKey | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [adding, startAdding] = useTransition();
  const [finishing, startFinishing] = useTransition();

  const processing = state.sources.find((source) => source.status === "processing");
  const failed = state.sources.at(-1)?.status === "failed";

  const refresh = useCallback(async () => {
    const result = await getTeachState();
    if (result.ok) setState(result.data);
    return result;
  }, []);

  // Poll while a link or note is being read.
  useEffect(() => {
    if (!processing) return;
    const timer = window.setTimeout(refresh, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [processing, state, refresh]);

  function submitSource(event: React.FormEvent) {
    event.preventDefault();
    setInputError(null);
    setError(null);
    if (mode === "url" && !/^https?:\/\/\S+\.\S+/i.test(url.trim())) {
      setInputError(tt("urlInvalid"));
      return;
    }
    if (mode === "text" && !text.trim()) {
      setInputError(tt("textRequired"));
      return;
    }
    startAdding(async () => {
      const result = await addSource(mode === "url" ? { type: "url", url: url.trim() } : { type: "text", text: text.trim() });
      if (!result.ok) {
        if (result.error === "invalid") setInputError(mode === "url" ? tt("urlInvalid") : tt("textRequired"));
        else setError(result.error);
        return;
      }
      setUrl("");
      setText("");
      await refresh();
    });
  }

  async function withFact<T>(fact: Fact, action: () => Promise<{ ok: true; data: T } | { ok: false; error: StepErrorKey }>) {
    setBusyId(fact.id);
    const result = await action();
    setBusyId(null);
    if (!result.ok) toast.error(t(`errors.${result.error}`));
    return result;
  }

  const replaceFact = (fact: Fact) => setState((s) => ({ ...s, facts: s.facts.map((f) => (f.id === fact.id ? fact : f)) }));

  const onConfirm = async (fact: Fact) => {
    const result = await withFact(fact, () => confirmFact(fact.id));
    if (result.ok) replaceFact(result.data);
  };
  const onSave = async (fact: Fact, value: string) => {
    const result = await withFact(fact, () => editFact(fact.id, value));
    if (result.ok) replaceFact(result.data);
    return result.ok;
  };
  const onRemove = async (fact: Fact) => {
    const result = await withFact(fact, () => removeFact(fact.id));
    if (result.ok) {
      setState((s) => ({ ...s, facts: s.facts.filter((f) => f.id !== fact.id) }));
      toast.success(tt("removed"));
      void refresh();
    }
  };
  const onAnswer = async (gap: Gap, value: string) => {
    const result = await answerGap(gap.category, gap.key, value);
    if (!result.ok) {
      toast.error(t(`errors.${result.error}`));
      return false;
    }
    toast.success(tt("saved"));
    await refresh();
    return true;
  };

  const hasFacts = state.facts.length > 0;
  const toCheck = state.facts.filter((fact) => fact.status === "suggested").length;

  return (
    <div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <OptionCard icon={Link2} title={tt("link")} hint={tt("linkHint")} selected={mode === "url"} onClick={() => setMode("url")} />
        <OptionCard icon={PenLine} title={tt("type")} hint={tt("typeHint")} selected={mode === "text"} onClick={() => setMode("text")} />
        <OptionCard icon={Mic} title={tt("speak")} hint={tt("speakHint")} disabled badge={tt("comingSoon")} />
      </div>

      {mode && (
        <form onSubmit={submitSource} noValidate className="mt-4 flex flex-col gap-2 rounded-xl border bg-card p-4 shadow-xs md:p-5">
          <label htmlFor={inputId} className="text-sm leading-5 font-medium">
            {mode === "url" ? tt("urlLabel") : tt("textLabel")}
          </label>
          {mode === "url" ? (
            <Input
              id={inputId}
              type="url"
              inputMode="url"
              autoComplete="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder={tt("urlPlaceholder")}
              aria-invalid={inputError ? true : undefined}
              maxLength={2000}
            />
          ) : (
            <textarea
              id={inputId}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={tt("textPlaceholder")}
              aria-invalid={inputError ? true : undefined}
              maxLength={5000}
              rows={5}
              className="w-full rounded-lg border border-input bg-surface px-4 py-3 text-base shadow-xs transition-[border-color] motion-fast placeholder:text-text-subtle hover:border-text-subtle/60 focus-visible:border-ring aria-invalid:border-destructive md:text-[15px]"
            />
          )}
          {inputError && (
            <p role="alert" className="text-sm leading-5 font-medium text-danger-fg">
              {inputError}
            </p>
          )}
          <Button type="submit" variant="secondary" className="mt-1 w-full sm:w-fit" disabled={adding || Boolean(processing)}>
            {mode === "url" ? tt("read") : tt("addDetails")}
          </Button>
        </form>
      )}

      <div aria-live="polite">
        {processing && (
          <p className="mt-4 flex items-center gap-3 rounded-xl bg-sky-100 px-4 py-3 font-medium text-sky-ink">
            <LoaderCircle className="size-5 shrink-0 motion-safe:animate-spin" aria-hidden />
            {processing.type === "url" ? tt("processingLink") : tt("processingText")}
          </p>
        )}
        {!processing && failed && (
          <p role="alert" className="mt-4 rounded-xl bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
            {tt("failed")}
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}

      <section aria-labelledby="knows-title" className="mt-10">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="knows-title" className="text-[22px] leading-7 font-semibold">
            {tt("knowsTitle")}
          </h2>
          {toCheck > 0 && <p className="text-sm font-medium text-text-muted">{tt("checkThese", { count: toCheck })}</p>}
        </div>
        {hasFacts ? (
          <KnowledgeCards facts={state.facts} sources={state.sources} busyId={busyId} onConfirm={onConfirm} onSave={onSave} onRemove={onRemove} />
        ) : (
          <p className="rounded-xl border border-dashed px-5 py-8 text-center text-text-muted">{tt("knowsEmpty")}</p>
        )}
      </section>

      <GapQuestions gaps={state.gaps} onAnswer={onAnswer} />

      <StepFooter backHref="/onboarding?step=role">
        {!hasFacts && (
          <Button asChild variant="ghost" className="text-text-muted">
            <Link href="/onboarding?step=voice">{t("skip")}</Link>
          </Button>
        )}
        <Button
          size="lg"
          className="w-full md:w-auto md:min-w-48"
          disabled={!hasFacts || finishing || Boolean(processing)}
          aria-busy={finishing}
          aria-describedby={!hasFacts ? "teach-need-one" : undefined}
          onClick={() =>
            startFinishing(async () => {
              const result = await finishTeach();
              if (result && !result.ok) setError(result.error);
            })
          }
        >
          {finishing ? t("saving") : tt("confirmAll")}
        </Button>
        {!hasFacts && (
          <p id="teach-need-one" className="sr-only">
            {tt("needOne")}
          </p>
        )}
      </StepFooter>
    </div>
  );
}
