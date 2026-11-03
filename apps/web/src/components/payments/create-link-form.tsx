"use client";

import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { createPaymentLink, type PaymentsErrorKey } from "@/app/(app)/payments/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface CreateLinkFormProps {
  /** Sending to a known customer (from their page): no phone field. */
  contact?: { id: string; name: string | null };
}

function newKey(): string {
  return crypto.randomUUID();
}

/** "Send a payment link": who, how much, for what, by when (ACT-05). */
export function CreateLinkForm({ contact }: CreateLinkFormProps) {
  const t = useTranslations("payments");
  const id = useId();
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [rupees, setRupees] = useState("");
  const [purpose, setPurpose] = useState("");
  const [due, setDue] = useState("");
  // One key per filled-in form: a double tap sends one link.
  const [key, setKey] = useState(newKey);
  const [error, setError] = useState<PaymentsErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        const amount = Number(rupees);
        if (!rupees || !Number.isFinite(amount) || amount < 1 || !purpose.trim()) return setError("invalid");
        startTransition(async () => {
          const result = await createPaymentLink({
            contactId: contact?.id,
            phone: contact ? undefined : phone,
            name: contact ? undefined : name,
            rupees: amount,
            purpose,
            dueDate: due || undefined,
            key,
          });
          if (result.ok) {
            toast.success(t("created"));
            setRupees("");
            setPurpose("");
            setDue("");
            if (!contact) {
              setPhone("");
              setName("");
            }
            setKey(newKey());
          } else setError(result.error);
        });
      }}
    >
      {contact ? (
        <p className="text-sm text-text-muted sm:col-span-2">{t("toCustomer", { name: contact.name ?? t("thisCustomer") })}</p>
      ) : (
        <>
          <div>
            <Label htmlFor={`${id}-phone`}>{t("phone")}</Label>
            <Input
              id={`${id}-phone`}
              inputMode="tel"
              autoComplete="off"
              className="mt-1.5"
              placeholder="98765 43210"
              value={phone}
              onChange={(event) => setPhone(event.target.value.slice(0, 20))}
              required
            />
          </div>
          <div>
            <Label htmlFor={`${id}-name`}>{t("name")}</Label>
            <Input id={`${id}-name`} className="mt-1.5" value={name} onChange={(event) => setName(event.target.value.slice(0, 120))} />
          </div>
        </>
      )}
      <div>
        <Label htmlFor={`${id}-amount`}>{t("amount")}</Label>
        <Input
          id={`${id}-amount`}
          inputMode="decimal"
          className="mt-1.5 tabular-nums"
          placeholder="2000"
          value={rupees}
          onChange={(event) => setRupees(event.target.value.replace(/[^\d.]/g, "").slice(0, 10))}
          required
        />
      </div>
      <div>
        <Label htmlFor={`${id}-purpose`}>{t("purpose")}</Label>
        <Input
          id={`${id}-purpose`}
          className="mt-1.5"
          placeholder={t("purposePlaceholder")}
          value={purpose}
          onChange={(event) => setPurpose(event.target.value.slice(0, 200))}
          required
        />
      </div>
      <div>
        <Label htmlFor={`${id}-due`}>{t("due")}</Label>
        <Input id={`${id}-due`} type="date" className="mt-1.5" value={due} onChange={(event) => setDue(event.target.value)} />
        <p className="mt-1 text-[13px] text-text-muted">{t("dueHint")}</p>
      </div>
      <div className="flex items-end">
        <Button type="submit" disabled={pending} className="w-full sm:w-auto">
          {t("send")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger-fg sm:col-span-2">
          {t(`errors.${error}`)}
        </p>
      )}
    </form>
  );
}
