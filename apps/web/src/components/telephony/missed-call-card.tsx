"use client";

import { Ban, Check, Copy, Printer } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { blockMissedCaller, setMissedCallNumber, unblockCaller } from "@/app/(app)/more/connect/actions";
import { Button } from "@/components/ui/button";
import type { MissedCallSetup, PhoneNumber } from "@/lib/telephony/types";

const LANGS = ["en", "hi", "te"] as const;

function PosterLine({ lang, text }: { lang: (typeof LANGS)[number]; text: string }) {
  const t = useTranslations("missedCall");
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-start gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-5 text-text-muted">{t(`lang.${lang}`)}</p>
        <p lang={lang} className="leading-6">
          {text}
        </p>
      </div>
      <Button
        variant="secondary"
        size="sm"
        aria-label={t("copyLine", { lang: t(`lang.${lang}`) })}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            toast.success(t("copied"));
            window.setTimeout(() => setCopied(false), 2000);
          } catch {
            // Clipboard can be blocked; the line stays visible to copy by hand.
          }
        }}
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        <span aria-hidden>{copied ? t("copied") : t("copy")}</span>
      </Button>
    </div>
  );
}

/** CALL-20: choose the missed-call number, share the poster line and QR card, see results. */
export function MissedCallCard({ setup, numbers }: { setup: MissedCallSetup; numbers: PhoneNumber[] }) {
  const t = useTranslations("missedCall");
  const selectId = useId();
  const [pending, start] = useTransition();
  const eligible = numbers.filter((n) => n.type === "local" || n.type === "mobile_virtual" || n.type === "byo_sip");

  const choose = (id: string | null) =>
    start(async () => {
      const result = await setMissedCallNumber(id);
      if (result.ok) toast.success(id ? t("saved") : t("turnedOff"));
      else toast.error(t(`errors.${result.error}`));
    });
  const block = (id: string) =>
    start(async () => {
      const result = await blockMissedCaller(id);
      if (result.ok) toast.success(t("blocked"));
      else toast.error(t(result.error === "conflict" ? "alreadyBlocked" : `errors.${result.error}`));
    });
  const unblock = (id: string) =>
    start(async () => {
      const result = await unblockCaller(id);
      if (result.ok) toast.success(t("unblocked"));
      else toast.error(t(`errors.${result.error}`));
    });

  const stats = [
    { key: "missed", value: setup.stats.missed },
    { key: "calledBack", value: setup.stats.called_back },
    { key: "answered", value: setup.stats.answered },
  ] as const;

  return (
    <div className="mt-5 flex flex-col gap-5">
      {eligible.length === 0 ? (
        <p className="text-sm leading-5 text-text-muted">{t("needNumber")}</p>
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <label htmlFor={selectId} className="text-sm font-medium">
              {t("numberLabel")}
            </label>
            <select
              id={selectId}
              className="focus-ring h-11 rounded-lg border bg-background px-3"
              value={setup.phone_number_id ?? ""}
              disabled={pending}
              onChange={(e) => choose(e.target.value || null)}
            >
              <option value="">{t("off")}</option>
              {eligible.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.display ?? t("pendingNumber", { city: n.city ?? "" })}
                  {n.label ? ` · ${n.label}` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {setup.phone_number_id && !setup.live && <p className="rounded-lg bg-surface-2 px-4 py-3 text-sm leading-5">{t("notLive")}</p>}

      {setup.poster && (
        <div>
          <h3 className="font-medium">{t("posterTitle")}</h3>
          <div className="divide-y">
            {LANGS.map((lang) => (
              <PosterLine key={lang} lang={lang} text={setup.poster![lang]} />
            ))}
          </div>
          <Button asChild variant="secondary" className="mt-2 w-full sm:w-fit">
            <Link href="/missed-call-card">
              <Printer aria-hidden /> {t("printCard")}
            </Link>
          </Button>
        </div>
      )}

      {setup.phone_number_id && (
        <div>
          <h3 className="font-medium">{t("statsTitle", { days: setup.stats.days })}</h3>
          <dl className="mt-2 grid grid-cols-3 gap-2">
            {stats.map((s) => (
              <div key={s.key} className="rounded-lg bg-surface-2 px-3 py-2.5">
                <dt className="text-[13px] leading-5 text-text-muted">{t(`stats.${s.key}`)}</dt>
                <dd className="text-2xl font-semibold tabular-nums">{s.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {setup.recent.length > 0 && (
        <div>
          <h3 className="font-medium">{t("recentTitle")}</h3>
          <ul className="mt-1 divide-y">
            {setup.recent.map((m) => (
              <li key={m.id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="tabular-nums">{m.phone_masked}</p>
                  <p className="text-sm leading-5 text-text-muted">
                    {t(`status.${m.status}`)}
                    {m.outcome ? ` · ${m.outcome.replace("_", " ")}` : ""}
                  </p>
                </div>
                {m.status !== "blocked" && (
                  <Button variant="ghost" size="sm" disabled={pending} onClick={() => block(m.id)}>
                    <Ban aria-hidden /> {t("block")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {setup.blocks.length > 0 && (
        <div>
          <h3 className="font-medium">{t("blocksTitle")}</h3>
          <ul className="mt-1 divide-y">
            {setup.blocks.map((b) => (
              <li key={b.id} className="flex items-center gap-3 py-2.5">
                <p className="min-w-0 flex-1 tabular-nums">
                  {b.phone_masked}
                  {b.reason ? <span className="text-sm text-text-muted"> · {b.reason}</span> : null}
                </p>
                <Button variant="ghost" size="sm" disabled={pending} onClick={() => unblock(b.id)}>
                  {t("unblock")}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
