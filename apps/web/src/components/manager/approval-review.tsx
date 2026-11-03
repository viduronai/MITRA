"use client";

import { Check, Save, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatNumber } from "@/lib/format";
import { decideApproval, editApproval, type ManagerErrorKey } from "@/lib/manager/actions";
import type { Approval } from "@/lib/manager/types";

type Primitive = string | number | boolean;

const isPrimitive = (value: unknown): value is Primitive =>
  typeof value === "string" || typeof value === "number" || typeof value === "boolean";

/** Internal ids are never shown (the campaign / request is named elsewhere on the card). */
const isInternal = (key: string) => key === "id" || key.endsWith("_id") || key.endsWith("_ids");
/** Money is stored in paise; owners see and type rupees. */
const isPaise = (key: string) => key.endsWith("_paise");

const textareaClass =
  "focus-ring min-h-20 w-full rounded-lg border border-input bg-surface px-4 py-3 text-base md:text-[15px]";

/** Edit-before-approve (APPR-06). Saving bumps the card version, so older cards stop working. */
export function ApprovalReview({ approval }: { approval: Approval }) {
  const t = useTranslations("approvals");
  const locale = useLocale();
  const router = useRouter();
  const primitives = Object.entries(approval.payload).filter(
    (entry): entry is [string, Primitive] => isPrimitive(entry[1]) && !isInternal(entry[0]),
  );
  // What the owner sees in each input (rupees for paise fields).
  const shown = (key: string, value: Primitive): Primitive =>
    isPaise(key) && typeof value === "number" ? String(value / 100) : value;
  const [fields, setFields] = useState<Record<string, Primitive>>(() =>
    Object.fromEntries(primitives.map(([key, value]) => [key, shown(key, value)])),
  );
  const [summary, setSummary] = useState(approval.summary);
  const [version, setVersion] = useState(approval.version);
  const [note, setNote] = useState("");
  const [pending, start] = useTransition();
  const pendingCard = approval.status === "pending";
  // Kinds with edit rules (list calls, payment links): only those fields change, and the server
  // writes the summary from them.
  const ruled = approval.editable !== null;
  const canEdit = (key: string) => pendingCard && (approval.editable === null || approval.editable.includes(key));

  const localSummary =
    approval.summary_key && t.has(`summaries.${approval.summary_key}` as never)
      ? t(`summaries.${approval.summary_key}` as never, approval.summary_params as never)
      : approval.summary;

  /** Back to the stored shape: rupees -> paise, numbers stay numbers. */
  function toPayload(): Record<string, unknown> | null {
    const out: Record<string, unknown> = { ...approval.payload };
    for (const [key, original] of primitives) {
      const value = fields[key];
      if (!isPaise(key) || typeof original !== "number") {
        out[key] = value;
        continue;
      }
      const rupees = Number(String(value).replace(/[,₹\s]/g, ""));
      if (!Number.isFinite(rupees)) return null;
      out[key] = Math.round(rupees * 100);
    }
    return out;
  }

  /** These can only go down: say so with the limit before asking the server. */
  function tooHigh(payload: Record<string, unknown>): string | null {
    for (const key of approval.editable ?? []) {
      const before = approval.payload[key];
      const after = payload[key];
      if (typeof before === "number" && typeof after === "number" && after > before) {
        return isPaise(key) ? `₹${formatNumber(before / 100, locale)}` : formatNumber(before, locale);
      }
    }
    return null;
  }

  const changed =
    (!ruled && summary.trim() !== approval.summary) ||
    primitives.some(([key, value]) => fields[key] !== shown(key, value));

  const error = (key: ManagerErrorKey) => toast.error(t(`errors.${key}`));

  async function saveEdits(): Promise<number | null> {
    const payload = toPayload();
    if (payload === null) {
      error("invalid");
      return null;
    }
    const max = tooHigh(payload);
    if (max !== null) {
      toast.error(t("errors.too_high", { max }));
      return null;
    }
    // Ruled kinds: the summary is the server's; send it back unchanged.
    const result = await editApproval(approval.id, version, payload, ruled ? approval.summary : summary);
    if (!result.ok) {
      error(result.error);
      return null;
    }
    setVersion(result.data);
    return result.data;
  }

  const save = () =>
    start(async () => {
      if (await saveEdits()) {
        toast.success(t("saved"));
        router.refresh();
      }
    });

  const decide = (action: "approve" | "decline") =>
    start(async () => {
      let current = version;
      if (action === "approve" && changed) {
        const next = await saveEdits();
        if (next === null) return;
        current = next;
      }
      const result = await decideApproval(approval.id, action, current, note || undefined);
      if (!result.ok) {
        error(result.error);
        return;
      }
      toast.success(action === "approve" ? t("approvedToast") : t("declinedToast"));
      router.push("/approvals");
    });

  const label = (key: string) =>
    t.has(`fields.${key}` as never) ? t(`fields.${key}` as never) : key.replaceAll("_", " ");

  return (
    <section aria-labelledby="review-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="review-title" className="text-lg leading-[26px] font-semibold">
        {pendingCard ? t("reviewTitle") : t("detailsTitle")}
      </h2>
      <div className="mt-4 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="approval-summary">{t("summaryLabel")}</Label>
          {ruled ? (
            <>
              <p id="approval-summary" className="rounded-lg bg-surface-2 px-4 py-3 text-base md:text-[15px]">
                {localSummary}
              </p>
              {pendingCard && <p className="text-[13px] text-text-muted">{t("summaryLocked")}</p>}
            </>
          ) : (
            <textarea
              id="approval-summary"
              className={textareaClass}
              value={summary}
              maxLength={500}
              disabled={!pendingCard || pending}
              onChange={(event) => setSummary(event.target.value)}
            />
          )}
        </div>
        {primitives.map(([key, original]) => {
          const value = fields[key];
          return (
            <div key={key} className="flex flex-col gap-1.5">
              <Label htmlFor={`field-${key}`}>{label(key)}</Label>
              {typeof original === "boolean" ? (
                <input
                  id={`field-${key}`}
                  type="checkbox"
                  className="size-5"
                  checked={value === true}
                  disabled={!canEdit(key) || pending}
                  onChange={(event) => setFields((f) => ({ ...f, [key]: event.target.checked }))}
                />
              ) : (
                <Input
                  id={`field-${key}`}
                  inputMode={typeof original === "number" ? "decimal" : undefined}
                  value={String(value)}
                  readOnly={!canEdit(key)}
                  disabled={pending}
                  className={canEdit(key) ? undefined : "bg-surface-2"}
                  onChange={(event) => {
                    const raw = event.target.value;
                    const numeric = typeof original === "number" && !isPaise(key);
                    const next = numeric && raw.trim() !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
                    setFields((f) => ({ ...f, [key]: next }));
                  }}
                />
              )}
            </div>
          );
        })}
        {pendingCard && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="approval-note">{t("noteLabel")}</Label>
              <Input id="approval-note" value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={pending} onClick={() => decide("approve")}>
                <Check aria-hidden />
                {changed ? t("approveEdited") : t("approve")}
              </Button>
              <Button variant="secondary" disabled={pending} onClick={() => decide("decline")}>
                <X aria-hidden />
                {t("decline")}
              </Button>
              {changed && (
                <Button variant="ghost" disabled={pending} onClick={save}>
                  <Save aria-hidden />
                  {t("saveOnly")}
                </Button>
              )}
            </div>
            <p className="text-[13px] text-text-muted">{t("safeNote")}</p>
          </>
        )}
      </div>
    </section>
  );
}
