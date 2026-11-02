"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { rateCall, teachFromCall } from "@/app/(app)/calls/actions";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { CallRating } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const textareaClass =
  "focus-ring min-h-24 w-full rounded-lg border border-input bg-surface px-4 py-3 text-base placeholder:text-text-subtle md:text-[15px]";

/** 👍 / 👎 + optional reason (REP-05). */
export function CallRatingCard({
  callId,
  employeeName,
  initial,
}: {
  callId: string;
  employeeName: string;
  initial: CallRating | null;
}) {
  const t = useTranslations("callDetail");
  const [rating, setRating] = useState<CallRating | null>(initial);
  const [reason, setReason] = useState("");
  const [pending, start] = useTransition();

  const send = (value: CallRating, why?: string) =>
    start(async () => {
      const result = await rateCall(callId, value, why);
      if (!result.ok) {
        toast.error(t("error"));
        return;
      }
      setRating(value);
      if (value === "up" || why) toast.success(t("rated", { name: employeeName }));
    });

  return (
    <section aria-labelledby="rate-title" className="rounded-xl border bg-card p-5 shadow-xs">
      <h2 id="rate-title" className="text-lg leading-[26px] font-semibold">
        {t("rateTitle", { name: employeeName })}
      </h2>
      <div className="mt-3 flex gap-2">
        {(
          [
            ["up", ThumbsUp, t("good")],
            ["down", ThumbsDown, t("bad")],
          ] as const
        ).map(([value, Icon, label]) => (
          <Button
            key={value}
            variant="secondary"
            aria-pressed={rating === value}
            disabled={pending}
            onClick={() => send(value)}
            className={cn(rating === value && "border-brand-600 bg-brand-50 text-brand-700")}
          >
            <Icon aria-hidden />
            {label}
          </Button>
        ))}
      </div>
      {rating === "down" && (
        <form
          className="mt-4 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (reason.trim()) send("down", reason);
          }}
        >
          <Label htmlFor="rating-reason">{t("reasonLabel")}</Label>
          <textarea
            id="rating-reason"
            value={reason}
            maxLength={300}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t("reasonPlaceholder")}
            className={textareaClass}
          />
          <Button type="submit" variant="secondary" disabled={pending || !reason.trim()} className="self-start">
            {t("sendRating")}
          </Button>
        </form>
      )}
    </section>
  );
}

/** "Teach Priya something from this call": saved as a confirmed fact. */
export function TeachFromCall({
  callId,
  employeeName,
  question,
}: {
  callId: string;
  employeeName: string;
  question: string | null;
}) {
  const t = useTranslations("callDetail");
  const [answer, setAnswer] = useState("");
  const [pending, start] = useTransition();

  return (
    <section id="teach" aria-labelledby="teach-title" className="scroll-mt-24 rounded-xl border bg-card p-5 shadow-xs">
      <h2 id="teach-title" className="text-lg leading-[26px] font-semibold">
        {t("teachTitle", { name: employeeName })}
      </h2>
      {question && <p className="mt-1 text-text-muted">“{question}”</p>}
      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          start(async () => {
            const result = await teachFromCall(callId, question, answer);
            if (!result.ok) {
              toast.error(t("error"));
              return;
            }
            setAnswer("");
            toast.success(t("taught", { name: employeeName }));
          });
        }}
      >
        <Label htmlFor="teach-answer">{t("teachLabel", { name: employeeName })}</Label>
        <textarea
          id="teach-answer"
          value={answer}
          maxLength={500}
          onChange={(event) => setAnswer(event.target.value)}
          placeholder={t("teachPlaceholder")}
          className={textareaClass}
        />
        <Button type="submit" disabled={pending || !answer.trim()} className="self-start">
          {t("teachSubmit", { name: employeeName })}
        </Button>
      </form>
    </section>
  );
}
