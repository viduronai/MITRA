"use client";

import { BadgeCheck, Lightbulb, Pencil, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { confirmMemory, deleteMemory, forgetCustomer, updateMemory } from "@/app/(app)/customers/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { MemoryFact } from "@/lib/api/types";

function humanKey(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function MemoryItem({ customerId, fact }: { customerId: string; fact: MemoryFact }) {
  const t = useTranslations("customer");
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(fact.value);
  const [pending, start] = useTransition();
  const confirmed = fact.status === "confirmed";

  const run = (action: () => Promise<{ ok: boolean }>, after?: () => void) =>
    start(async () => {
      const result = await action();
      if (!result.ok) toast.error(t("error"));
      else after?.();
    });

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-5 text-text-muted">{humanKey(fact.key)}</p>
          {editing ? (
            <form
              className="mt-1 flex flex-col gap-2 sm:flex-row"
              onSubmit={(event) => {
                event.preventDefault();
                run(() => updateMemory(customerId, fact.id, value), () => setEditing(false));
              }}
            >
              <Input
                value={value}
                maxLength={300}
                aria-label={t("memoryLabel")}
                onChange={(event) => setValue(event.target.value)}
                autoFocus
              />
              <div className="flex gap-2">
                <Button type="submit" disabled={pending || !value.trim()}>
                  {t("save")}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                  {t("cancel")}
                </Button>
              </div>
            </form>
          ) : (
            <p className="leading-6 font-medium">{fact.value}</p>
          )}
        </div>
        <span
          className={
            confirmed
              ? "inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-success/12 px-2 text-[12px] font-medium text-success-fg"
              : "inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-warning/15 px-2 text-[12px] font-medium text-warning-fg"
          }
        >
          {confirmed ? <BadgeCheck className="size-3.5" aria-hidden /> : <Lightbulb className="size-3.5" aria-hidden />}
          {confirmed ? t("confirmed") : t("guessed")}
        </span>
      </div>
      {!editing && (
        <div className="-ml-2 flex flex-wrap gap-1">
          <Button variant="ghost" size="xs" onClick={() => setEditing(true)} disabled={pending}>
            <Pencil aria-hidden />
            {t("edit")}
          </Button>
          {!confirmed && (
            <Button variant="ghost" size="xs" onClick={() => run(() => confirmMemory(customerId, fact.id))} disabled={pending}>
              <BadgeCheck aria-hidden />
              {t("markConfirmed")}
            </Button>
          )}
          <Button variant="ghost" size="xs" onClick={() => run(() => deleteMemory(customerId, fact.id))} disabled={pending}>
            <Trash2 aria-hidden />
            {t("delete")}
          </Button>
        </div>
      )}
    </li>
  );
}

/** Memory with confirmed / guessed badges, edit and delete (MEM-03, MEM-04). */
export function MemoryList({ customerId, memory }: { customerId: string; memory: MemoryFact[] }) {
  const t = useTranslations("customer");
  if (memory.length === 0) return <p className="text-text-muted">{t("noMemory")}</p>;
  return (
    <ul className="flex flex-col divide-y">
      {memory.map((fact) => (
        <MemoryItem key={`${fact.id}:${fact.updated_at}`} customerId={customerId} fact={fact} />
      ))}
    </ul>
  );
}

/** "Forget this customer" with a confirmation dialog (DPDP erasure). */
export function ForgetCustomer({
  customerId,
  customerName,
  employeeName,
}: {
  customerId: string;
  customerName: string;
  employeeName: string;
}) {
  const t = useTranslations("customer");
  const [pending, start] = useTransition();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" className="text-danger-fg">
          <Trash2 aria-hidden />
          {t("forget")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{t("forgetTitle", { customer: customerName })}</DialogTitle>
        <DialogDescription>{t("forgetBody", { name: employeeName })}</DialogDescription>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">{t("cancel")}</Button>
          </DialogClose>
          <Button
            variant="destructive"
            disabled={pending}
            onClick={() =>
              start(async () => {
                const result = await forgetCustomer(customerId);
                if (result && !result.ok) toast.error(t("error"));
              })
            }
          >
            {t("forgetConfirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
