"use client";

import { PhoneForwarded, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { addStaff, removeStaff, resolveCard } from "@/app/(app)/team/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatTime } from "@/lib/format";
import type { HandoffCard, Staff } from "@/lib/team/types";
import { selectClass } from "./rule-editor";

/** CALL-19 / TEAM-04: who takes transfers, in order, and who gets WhatsApp briefs. */
export function StaffLadder({ staff }: { staff: Staff[] }) {
  const t = useTranslations("teamMap");
  const [pending, start] = useTransition();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("+91");
  const [role, setRole] = useState("");
  const [ladder, setLadder] = useState<string>(String(Math.min(9, staff.length + 1)));
  const [owner, setOwner] = useState(false);

  return (
    <section aria-labelledby="staff-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="staff-title" className="text-lg font-semibold">
        {t("staffTitle")}
      </h2>
      <p className="mt-1 text-sm text-text-muted">{t("staffHint")}</p>
      <ol className="mt-4 flex flex-col divide-y">
        {staff.map((s) => (
          <li key={s.id} className="flex items-center gap-3 py-3">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-2 text-sm font-semibold tabular-nums">
              {s.ladder_position ?? "–"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">
                {s.name}
                {s.is_owner && <span className="ms-2 text-xs text-text-muted">{t("owner")}</span>}
              </p>
              <p className="text-sm text-text-muted">
                {[s.role_label, `…${s.phone_e164.slice(-4)}`, t("rings", { n: s.ring_timeout_s })].filter(Boolean).join(" · ")}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              disabled={pending}
              aria-label={t("removeStaff", { name: s.name })}
              onClick={() =>
                start(async () => {
                  const res = await removeStaff(s.id);
                  if (!res.ok) toast.error(t("error"));
                })
              }
            >
              <Trash2 aria-hidden />
            </Button>
          </li>
        ))}
        {staff.length === 0 && <li className="py-3 text-text-muted">{t("noStaff")}</li>}
      </ol>
      <form
        className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          start(async () => {
            const res = await addStaff({ name, phone, role, ladder: ladder ? Number(ladder) : null, owner });
            if (!res.ok) {
              toast.error(t(res.error === "invalid" ? "staffInvalid" : "error"));
              return;
            }
            setName("");
            setPhone("+91");
            setRole("");
            toast.success(t("staffAdded"));
          });
        }}
      >
        <Input aria-label={t("staffName")} placeholder={t("staffName")} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
        <Input aria-label={t("staffPhone")} inputMode="tel" value={phone} maxLength={16} onChange={(e) => setPhone(e.target.value)} />
        <Input aria-label={t("staffRole")} placeholder={t("staffRole")} value={role} maxLength={60} onChange={(e) => setRole(e.target.value)} />
        <select aria-label={t("ladderLabel")} className={selectClass} value={ladder} onChange={(e) => setLadder(e.target.value)}>
          <option value="">{t("notOnLadder")}</option>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {t("ladderPosition", { n })}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-5 accent-brand-600" checked={owner} onChange={(e) => setOwner(e.target.checked)} />
          {t("isOwner")}
        </label>
        <Button type="submit" disabled={pending || !name.trim()}>
          {t("addStaff")}
        </Button>
      </form>
    </section>
  );
}

/** CALL-19: messages taken when nobody could pick up a transfer. */
export function HandoffCards({ cards }: { cards: HandoffCard[] }) {
  const t = useTranslations("teamMap");
  const locale = useLocale();
  const [pending, start] = useTransition();
  if (cards.length === 0) return null;
  return (
    <section aria-labelledby="cards-title" className="rounded-xl border border-amber-300 bg-card p-5 shadow-xs md:p-6">
      <h2 id="cards-title" className="flex items-center gap-2 text-lg font-semibold">
        <PhoneForwarded className="size-5" aria-hidden />
        {t("cardsTitle", { n: cards.length })}
      </h2>
      <ul className="mt-3 flex flex-col divide-y">
        {cards.map((card) => (
          <li key={card.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
            <div className="flex-1">
              <p className="font-medium">
                {t("cardWho", { last4: card.caller_last4 ?? "????" })} · {card.reason}
              </p>
              <p className="text-text-muted">“{card.message}”</p>
              {card.callback_by && (
                <p className="text-sm text-text-muted">
                  {t("promisedBy", { time: formatTime(new Date(card.callback_by), locale) })}
                </p>
              )}
            </div>
            <Button
              variant="secondary"
              disabled={pending}
              onClick={() =>
                start(async () => {
                  const res = await resolveCard(card.id);
                  if (!res.ok) toast.error(t("error"));
                })
              }
            >
              {t("calledBack")}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
