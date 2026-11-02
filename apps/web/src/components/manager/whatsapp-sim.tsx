"use client";

import { ArrowUp, Mic } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { simReply } from "@/lib/manager/actions";
import type { WaMessage } from "@/lib/manager/types";
import { cn } from "@/lib/utils";

/** Dev-only phone: every WhatsApp message Mitra "sent", plus replies as the logged-in owner. */
export function WhatsAppSim({ messages }: { messages: WaMessage[] }) {
  const t = useTranslations("waSim");
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [pending, start] = useTransition();

  const reply = (input: Parameters<typeof simReply>[0]) =>
    start(async () => {
      const result = await simReply(input);
      if (!result.ok) {
        toast.error(t("error"));
        return;
      }
      setDraft("");
      if (result.data !== "answered" && result.data !== "decided") toast.message(t.has(`outcome.${result.data}` as never) ? t(`outcome.${result.data}` as never) : result.data);
      router.refresh();
    });

  return (
    <div className="mx-auto flex w-full max-w-md flex-col overflow-hidden rounded-[28px] border-8 border-foreground/85 bg-surface-2 shadow-md">
      <ol className="flex max-h-[65dvh] min-h-[50dvh] flex-col gap-2 overflow-y-auto p-3">
        {messages.length === 0 && <li className="py-10 text-center text-text-muted">{t("empty")}</li>}
        {messages.map((m) => (
          <li key={m.id} className={cn("flex", m.direction === "in" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-xl px-3 py-2 text-[14px] leading-5 whitespace-pre-line shadow-xs",
                m.direction === "in" ? "bg-success/15" : "bg-card",
              )}
            >
              <span className="mb-0.5 block text-[11px] text-text-subtle">
                {t.has(`purpose.${m.purpose}` as never) ? t(`purpose.${m.purpose}` as never) : m.purpose} · …{m.phone_last4}
                {m.kind === "voice" && ` · ${t("voiceNote")}`}
              </span>
              {m.body}
              {m.buttons.length > 0 && (
                <div className="mt-2 flex flex-col gap-1 border-t pt-2">
                  {m.buttons.map((b) => (
                    <button
                      key={b.id}
                      type="button"
                      disabled={pending || !m.provider_message_id}
                      onClick={() => reply({ kind: "button_reply", button_id: b.id, context_id: m.provider_message_id ?? "" })}
                      className="focus-ring rounded-md py-1 text-[14px] font-medium text-info-fg hover:bg-surface-2"
                    >
                      {b.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
      <form
        className="flex items-end gap-2 border-t bg-card p-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (draft.trim()) reply({ kind: "text", text: draft });
        }}
      >
        <label htmlFor="sim-input" className="sr-only">
          {t("placeholder")}
        </label>
        <input
          id="sim-input"
          value={draft}
          maxLength={1000}
          placeholder={t("placeholder")}
          onChange={(event) => setDraft(event.target.value)}
          className="focus-ring h-11 flex-1 rounded-full border border-input bg-surface px-4 text-[15px]"
        />
        <Button
          type="button"
          size="icon"
          variant="secondary"
          disabled={pending || !draft.trim()}
          aria-label={t("sendVoice")}
          title={t("sendVoice")}
          onClick={() => reply({ kind: "voice", text: draft })}
        >
          <Mic aria-hidden />
        </Button>
        <Button type="submit" size="icon" disabled={pending || !draft.trim()} aria-label={t("send")}>
          <ArrowUp aria-hidden />
        </Button>
      </form>
    </div>
  );
}
