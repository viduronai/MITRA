"use client";

import { Check, Save, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { decideApproval, editApproval, type ManagerErrorKey } from "@/lib/manager/actions";
import type { Approval } from "@/lib/manager/types";

type Primitive = string | number | boolean;

const isPrimitive = (value: unknown): value is Primitive =>
  typeof value === "string" || typeof value === "number" || typeof value === "boolean";

const textareaClass =
  "focus-ring min-h-20 w-full rounded-lg border border-input bg-surface px-4 py-3 text-base md:text-[15px]";

/** Edit-before-approve (APPR-06): simple fields are editable; saving bumps the card version. */
export function ApprovalReview({ approval }: { approval: Approval }) {
  const t = useTranslations("approvals");
  const router = useRouter();
  const [summary, setSummary] = useState(approval.summary);
  const [fields, setFields] = useState<Record<string, Primitive>>(() =>
    Object.fromEntries(Object.entries(approval.payload).filter(([, v]) => isPrimitive(v))) as Record<string, Primitive>,
  );
  const [version, setVersion] = useState(approval.version);
  const [note, setNote] = useState("");
  const [pending, start] = useTransition();
  const pendingCard = approval.status === "pending";
  // The server refuses edits to other fields (e.g. a list call can only call fewer people).
  const canEdit = (key: string) => pendingCard && (approval.editable === null || approval.editable.includes(key));

  const changed =
    summary.trim() !== approval.summary ||
    Object.entries(fields).some(([key, value]) => approval.payload[key] !== value);

  const error = (key: ManagerErrorKey) => toast.error(t(`errors.${key}`));

  async function saveEdits(): Promise<number | null> {
    const payload = { ...approval.payload, ...fields };
    const result = await editApproval(approval.id, version, payload, summary);
    if (!result.ok) {
      error(result.error);
      return null;
    }
    setVersion(result.data);
    return result.data;
  }

  const save = () =>
    start(async () => {
      if (await saveEdits()) toast.success(t("saved"));
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

  return (
    <section aria-labelledby="review-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id="review-title" className="text-lg leading-[26px] font-semibold">
        {pendingCard ? t("reviewTitle") : t("detailsTitle")}
      </h2>
      <div className="mt-4 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="approval-summary">{t("summaryLabel")}</Label>
          <textarea
            id="approval-summary"
            className={textareaClass}
            value={summary}
            maxLength={500}
            disabled={!pendingCard || pending}
            onChange={(event) => setSummary(event.target.value)}
          />
        </div>
        {Object.entries(fields).map(([key, value]) => (
          <div key={key} className="flex flex-col gap-1.5">
            <Label htmlFor={`field-${key}`}>
              {t.has(`fields.${key}` as never) ? t(`fields.${key}` as never) : key.replaceAll("_", " ")}
            </Label>
            {typeof value === "boolean" ? (
              <input
                id={`field-${key}`}
                type="checkbox"
                className="size-5"
                checked={value}
                disabled={!canEdit(key) || pending}
                onChange={(event) => setFields((f) => ({ ...f, [key]: event.target.checked }))}
              />
            ) : (
              <Input
                id={`field-${key}`}
                inputMode={typeof value === "number" ? "decimal" : undefined}
                value={String(value)}
                disabled={!canEdit(key) || pending}
                onChange={(event) => {
                  const raw = event.target.value;
                  const next = typeof value === "number" && raw.trim() !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
                  setFields((f) => ({ ...f, [key]: next }));
                }}
              />
            )}
          </div>
        ))}
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
