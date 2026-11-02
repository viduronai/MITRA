"use client";

import { PhoneCall, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";
import { takeOver, whisper } from "@/app/(app)/live/actions";
import { LiveDot } from "@/components/mitra/live-dot";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { LiveDetail } from "@/lib/team/types";
import { cn } from "@/lib/utils";

const POLL_MS = 1500;

/** Refresh the server-rendered list of live calls every few seconds. */
export function AutoRefresh({ everyMs = 5000 }: { everyMs?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), everyMs);
    return () => clearInterval(id);
  }, [router, everyMs]);
  return null;
}

/** CALL-13/18: streaming transcript, private whisper, take over to my phone. */
export function LiveCallView({ initial }: { initial: LiveDetail }) {
  const t = useTranslations("live");
  const [turns, setTurns] = useState(initial.turns);
  const [whispers, setWhispers] = useState(initial.whispers);
  const [live, setLive] = useState(initial.live);
  const [text, setText] = useState("");
  const [pending, start] = useTransition();
  const next = useRef(initial.turns.length ? initial.turns[initial.turns.length - 1].seq + 1 : 0);
  const id = initial.call.id;

  useEffect(() => {
    if (!live) return;
    let stopped = false;
    const tick = async () => {
      try {
        const res = await fetch(`/live/${id}/poll?after=${next.current}`, { cache: "no-store" });
        if (!res.ok || stopped) return;
        const data = (await res.json()) as LiveDetail;
        if (data.turns.length) {
          next.current = data.turns[data.turns.length - 1].seq + 1;
          setTurns((cur) => [...cur, ...data.turns]);
        }
        setWhispers(data.whispers);
        setLive(data.live);
      } catch {
        // Network blip: the next tick tries again.
      }
    };
    const timer = setInterval(tick, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [id, live]);

  const sendWhisper = () =>
    start(async () => {
      const res = await whisper(id, text);
      if (res.ok) {
        setText("");
        toast.success(t("whisperSent"));
      } else toast.error(t(res.error === "ended" ? "ended" : "error"));
    });

  const takeover = () =>
    start(async () => {
      const res = await takeOver(id);
      if (res.ok) toast.success(t("connecting", { last4: res.data.to_last4 }));
      else toast.error(t(res.error === "ended" ? "ended" : "error"));
    });

  return (
    <div className="flex flex-col gap-4">
      <p className="flex items-center gap-2 text-sm text-text-muted" aria-live="polite">
        {live ? (
          <>
            <LiveDot /> {t("liveNow")}
          </>
        ) : (
          t("ended")
        )}
      </p>
      <ol className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto rounded-xl border bg-card p-4" aria-live="polite">
        {turns.map((turn) => (
          <li
            key={turn.seq}
            className={cn(
              "max-w-[85%] rounded-xl px-3 py-2",
              turn.role === "user" ? "self-start bg-surface-2" : "self-end bg-brand-50 text-brand-900",
            )}
          >
            <span className="block text-xs text-text-muted">
              {turn.role === "user" ? t("caller") : (initial.call.employee_name ?? t("employee"))}
            </span>
            {turn.text}
          </li>
        ))}
        {turns.length === 0 && <li className="text-text-muted">{t("waiting")}</li>}
      </ol>
      {whispers.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-text-muted">
          {whispers.map((w) => (
            <li key={w.at}>
              {w.kind === "takeover" ? t("takeoverLog") : t("whisperLog", { text: w.text ?? "" })} ·{" "}
              {w.delivered ? t("delivered") : t("pendingDelivery")}
            </li>
          ))}
        </ul>
      )}
      {live && (
        <div className="flex flex-col gap-2 rounded-xl border bg-card p-4">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) sendWhisper();
            }}
          >
            <Input
              aria-label={t("whisperLabel")}
              placeholder={t("whisperPlaceholder")}
              value={text}
              maxLength={300}
              onChange={(e) => setText(e.target.value)}
            />
            <Button type="submit" disabled={pending || !text.trim()}>
              <Send aria-hidden />
              {t("whisper")}
            </Button>
          </form>
          <p className="text-xs text-text-muted">{t("whisperHint")}</p>
          <Button variant="secondary" disabled={pending} onClick={takeover} className="self-start">
            <PhoneCall aria-hidden />
            {t("takeOver")}
          </Button>
        </div>
      )}
    </div>
  );
}
