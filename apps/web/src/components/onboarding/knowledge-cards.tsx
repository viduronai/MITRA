"use client";

import {
  Check,
  Clock,
  IndianRupee,
  ListChecks,
  MapPin,
  MessageCircleQuestion,
  Pencil,
  Phone,
  ScrollText,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Fact, FactCategory, Gap, KnowledgeSource } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const CATEGORY_ORDER: FactCategory[] = ["services", "prices", "timings", "location", "contact", "faq", "policy"];

const categoryIcons: Record<FactCategory, LucideIcon> = {
  services: ListChecks,
  prices: IndianRupee,
  timings: Clock,
  location: MapPin,
  contact: Phone,
  faq: MessageCircleQuestion,
  policy: ScrollText,
};

interface FactRowProps {
  fact: Fact;
  sourceType?: KnowledgeSource["type"];
  busy: boolean;
  onConfirm: () => void;
  onSave: (value: string) => Promise<boolean>;
  onRemove: () => void;
}

function FactRow({ fact, sourceType, busy, onConfirm, onSave, onRemove }: FactRowProps) {
  const t = useTranslations("onboarding.teach");
  const inputId = useId();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact.value);
  const suggested = fact.status === "suggested";

  if (editing) {
    return (
      <li className="py-3">
        <form
          className="flex flex-col gap-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (draft.trim() && (await onSave(draft.trim()))) setEditing(false);
          }}
        >
          <label htmlFor={inputId} className="text-sm leading-5 font-medium text-text-muted">
            {fact.key}
          </label>
          <Input id={inputId} value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={1000} autoFocus />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy || !draft.trim()}>
              {t("save")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
              {t("cancel")}
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:gap-3">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-x-2 text-sm leading-5 text-text-muted">
          <span>{fact.key}</span>
          {sourceType && (
            <span className="text-text-subtle">· {sourceType === "url" ? t("fromLink") : t("fromNotes")}</span>
          )}
        </p>
        <p className="leading-6 font-medium break-words">{fact.value}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {suggested ? (
          <Button size="sm" variant="secondary" onClick={onConfirm} disabled={busy} aria-label={t("confirmFact", { key: fact.key })}>
            <Check aria-hidden />
            {t("confirm")}
          </Button>
        ) : (
          <span className="inline-flex h-10 items-center gap-1.5 px-2 text-sm font-medium text-success-fg">
            <Check className="size-4" aria-hidden />
            {t("confirmed")}
          </span>
        )}
        <Button size="icon" variant="ghost" className="text-text-muted" onClick={() => setEditing(true)} aria-label={t("editFact", { key: fact.key })}>
          <Pencil className="size-[18px]" aria-hidden />
        </Button>
        <Button size="icon" variant="ghost" className="text-text-muted" onClick={onRemove} disabled={busy} aria-label={t("removeFact", { key: fact.key })}>
          <Trash2 className="size-[18px]" aria-hidden />
        </Button>
      </div>
    </li>
  );
}

interface KnowledgeCardsProps {
  facts: Fact[];
  sources: KnowledgeSource[];
  busyId: string | null;
  onConfirm: (fact: Fact) => void;
  onSave: (fact: Fact, value: string) => Promise<boolean>;
  onRemove: (fact: Fact) => void;
}

/** "What they know": one card per category (docs/06 §8 Knowledge card). */
export function KnowledgeCards({ facts, sources, busyId, onConfirm, onSave, onRemove }: KnowledgeCardsProps) {
  const t = useTranslations("onboarding.teach");
  const sourceType = (id: string | null) => sources.find((source) => source.id === id)?.type;
  const groups = CATEGORY_ORDER.map((category) => ({ category, facts: facts.filter((fact) => fact.category === category) })).filter(
    (group) => group.facts.length > 0,
  );

  return (
    <div className="grid grid-cols-1 gap-3 md:gap-4">
      {groups.map(({ category, facts: items }) => {
        const Icon = categoryIcons[category];
        const toCheck = items.filter((fact) => fact.status === "suggested").length;
        return (
          <section key={category} aria-labelledby={`cat-${category}`} className="rounded-xl border bg-card px-5 pt-4 pb-2 shadow-xs">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700" aria-hidden>
                <Icon className="size-[18px]" strokeWidth={1.75} />
              </span>
              <h3 id={`cat-${category}`} className="flex-1 font-semibold">
                {t(`categories.${category}`)}
              </h3>
              {toCheck > 0 && (
                <span className="inline-flex h-6 items-center rounded-full bg-warning/12 px-2.5 text-xs font-medium text-warning-fg">
                  {t("suggested")}
                </span>
              )}
            </div>
            <ul className="divide-y">
              {items.map((fact) => (
                <FactRow
                  key={fact.id}
                  fact={fact}
                  sourceType={sourceType(fact.source_id)}
                  busy={busyId === fact.id}
                  onConfirm={() => onConfirm(fact)}
                  onSave={(value) => onSave(fact, value)}
                  onRemove={() => onRemove(fact)}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function GapRow({ gap, onAnswer }: { gap: Gap; onAnswer: (value: string) => Promise<boolean> }) {
  const t = useTranslations("onboarding.teach");
  const inputId = useId();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <li>
      <form
        className="flex flex-col gap-2 rounded-xl border border-dashed bg-card p-4 md:p-5"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!value.trim()) return;
          setBusy(true);
          const saved = await onAnswer(value.trim());
          setBusy(false);
          if (saved) setValue("");
        }}
      >
        <label htmlFor={inputId} className="font-medium">
          {gap.question}
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id={inputId}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={t("answerPlaceholder")}
            maxLength={1000}
            className="sm:flex-1"
          />
          <Button type="submit" variant="secondary" disabled={busy || !value.trim()} className={cn("sm:w-auto")}>
            {t("saveAnswer")}
          </Button>
        </div>
      </form>
    </li>
  );
}

export function GapQuestions({ gaps, onAnswer }: { gaps: Gap[]; onAnswer: (gap: Gap, value: string) => Promise<boolean> }) {
  const t = useTranslations("onboarding.teach");
  if (gaps.length === 0) return null;

  return (
    <section aria-labelledby="gaps-title" className="mt-8">
      <h2 id="gaps-title" className="text-[22px] leading-7 font-semibold">
        {t("gapsTitle")}
      </h2>
      <p className="mt-1 text-text-muted">{t("gapsSubtitle")}</p>
      <ul className="mt-4 flex flex-col gap-3">
        {gaps.map((gap) => (
          <GapRow key={`${gap.category}:${gap.key}`} gap={gap} onAnswer={(value) => onAnswer(gap, value)} />
        ))}
      </ul>
    </section>
  );
}
