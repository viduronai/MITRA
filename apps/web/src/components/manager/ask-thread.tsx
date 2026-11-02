"use client";

import { ArrowUp, Check, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { askMitra, decideApproval, type ManagerErrorKey } from "@/lib/manager/actions";
import type { ConfirmCard, ThreadMessage } from "@/lib/manager/types";
import { cn } from "@/lib/utils";

function isConfirm(card: ThreadMessage["card"]): card is ConfirmCard {
  return !!card && "type" in card && card.type === "confirm";
}

/** MGR-08: the same Manager as WhatsApp, inside the app. */
export function AskThread({ initial }: { initial: ThreadMessage[] }) {
  const t = useTranslations("ask");
  const [messages, setMessages] = useState(initial);
  const [draft, setDraft] = useState("");
  const [pending, start] = useTransition();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  const errorText = (key: ManagerErrorKey) => t(`errors.${key}`);

  const send = (text: string) => {
    const said = text.trim();
    if (!said || pending) return;
    start(async () => {
      const result = await askMitra(said);
      if (!result.ok) {
        toast.error(errorText(result.error));
        return;
      }
      setDraft("");
      setMessages((list) => [...list, ...result.data]);
    });
  };

  const decide = (message: ThreadMessage, card: ConfirmCard, action: "approve" | "decline") =>
    start(async () => {
      const result = await decideApproval(card.approval_id, action, card.version);
      if (!result.ok) {
        toast.error(errorText(result.error));
        return;
      }
      const status = action === "approve" ? "approved" : "declined";
      setMessages((list) => list.map((m) => (m.id === message.id ? { ...m, card: { ...card, status } } : m)));
      toast.success(action === "approve" ? t("done") : t("cancelled"));
    });

  const openers = [t("openerWeek"), t("openerAttention")];

  return (
    <div className="flex min-h-[60dvh] flex-col rounded-xl border bg-card shadow-xs">
      <ol aria-live="polite" className="flex flex-1 flex-col gap-3 p-4 md:p-5">
        {messages.length === 0 && (
          <li className="flex flex-col items-center gap-3 py-10 text-center">
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              <Sparkles className="size-6" strokeWidth={1.75} aria-hidden />
            </span>
            <p className="max-w-sm text-text-muted">{t("empty")}</p>
          </li>
        )}
        {messages.map((m) => {
          const card = m.card;
          return (
            <li key={m.id} className={cn("flex", m.role === "owner" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-6 whitespace-pre-line",
                  m.role === "owner" ? "bg-brand-600 text-on-brand" : "bg-surface-2 text-foreground",
                )}
              >
                {m.channel === "whatsapp" && <span className="mb-0.5 block text-[11px] opacity-70">{t("viaWhatsapp")}</span>}
                {m.text}
                {isConfirm(card) && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {card.status === "pending" || card.status === undefined ? (
                      <>
                        <Button size="sm" disabled={pending} onClick={() => decide(m, card, "approve")}>
                          <Check aria-hidden />
                          {t("confirm")}
                        </Button>
                        <Button size="sm" variant="secondary" disabled={pending} onClick={() => decide(m, card, "decline")}>
                          <X aria-hidden />
                          {t("cancel")}
                        </Button>
                      </>
                    ) : (
                      <span className="rounded-full bg-card px-2.5 py-0.5 text-[13px] font-medium text-text-muted">
                        {t(`status.${card.status}`)}
                      </span>
                    )}
                    {card.apply_error && <span className="text-[13px] text-danger-fg">{t("applyError")}</span>}
                  </div>
                )}
                {card && "links" in card && card.links.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                    {card.links.slice(0, 3).map((link) => (
                      <Link key={link.href} href={link.href} className="focus-ring text-[13px] font-medium text-brand-700 underline">
                        {t("open")}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </li>
          );
        })}
        <div ref={endRef} />
      </ol>

      <div className="border-t p-3 md:p-4">
        <div className="mb-3 flex flex-wrap gap-2">
          {openers.map((opener) => (
            <button
              key={opener}
              type="button"
              disabled={pending}
              onClick={() => send(opener)}
              className="focus-ring rounded-full border bg-surface px-3 py-1.5 text-[13px] font-medium text-text-muted transition-colors motion-fast hover:bg-surface-2 hover:text-foreground"
            >
              {opener}
            </button>
          ))}
        </div>
        <form
          className="flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            send(draft);
          }}
        >
          <label htmlFor="ask-input" className="sr-only">
            {t("placeholder")}
          </label>
          <textarea
            id="ask-input"
            value={draft}
            maxLength={1000}
            rows={1}
            placeholder={t("placeholder")}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send(draft);
              }
            }}
            className="focus-ring max-h-40 min-h-11 flex-1 resize-none rounded-lg border border-input bg-surface px-4 py-2.5 text-base placeholder:text-text-subtle md:text-[15px]"
          />
          <Button type="submit" size="icon" disabled={pending || !draft.trim()} aria-label={t("send")}>
            <ArrowUp aria-hidden />
          </Button>
        </form>
        <p className="mt-2 text-[12px] text-text-subtle">{t("hint")}</p>
      </div>
    </div>
  );
}
