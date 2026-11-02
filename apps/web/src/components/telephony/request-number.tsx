"use client";

import { FileUp, Hash } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { requestNumber, submitKyc, type ConnectErrorKey } from "@/app/(app)/more/connect/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { KycDocument, PhoneNumber } from "@/lib/telephony/types";
import { cn } from "@/lib/utils";

const DOCUMENTS: KycDocument[] = ["gst", "shop_establishment", "udyam", "pan", "clinic_registration"];

function ErrorLine({ error }: { error: ConnectErrorKey | null }) {
  const t = useTranslations("connect");
  if (!error) return null;
  return (
    <p role="alert" className="mt-3 rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
      {t(`errors.${error}`)}
    </p>
  );
}

/** Step 1: ask for a city-code number (NUM-01). It waits in "pending KYC" until step 2. */
export function RequestNumberForm({ defaultCity }: { defaultCity: string }) {
  const t = useTranslations("connect");
  const ids = { city: useId(), type: useId() };
  const [city, setCity] = useState(defaultCity);
  const [type, setType] = useState<"local" | "mobile_virtual">("local");
  const [error, setError] = useState<ConnectErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      className="mt-5 flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        startTransition(async () => {
          const res = await requestNumber(city, type);
          if (!res.ok) setError(res.error);
          else toast.success(t("requested"));
        });
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.city}>{t("cityLabel")}</Label>
        <Input id={ids.city} value={city} maxLength={80} required onChange={(e) => setCity(e.target.value)} />
      </div>
      <fieldset>
        <legend className="mb-2 text-sm leading-5 font-medium">{t("typeLabel")}</legend>
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
          {(["local", "mobile_virtual"] as const).map((value) => (
            <label
              key={value}
              className={cn(
                "flex min-h-11 cursor-pointer flex-col items-center justify-center rounded-lg px-2 py-1.5 text-center text-sm font-medium text-text-muted transition-colors motion-fast has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
                type === value && "bg-surface text-foreground shadow-xs",
              )}
            >
              <input type="radio" name={ids.type} value={value} checked={type === value} onChange={() => setType(value)} className="sr-only" />
              {t(`types.${value}`)}
              <span className="text-xs font-normal text-text-muted">{t(`typeHints.${value}`)}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <ErrorLine error={error} />
      <Button type="submit" className="w-full sm:w-fit" disabled={pending} aria-busy={pending}>
        <Hash aria-hidden />
        {t("requestCta")}
      </Button>
    </form>
  );
}

/** Step 2: KYC placeholder. We record the document type and file name; the file stays local. */
export function KycForm({ number }: { number: PhoneNumber }) {
  const t = useTranslations("connect");
  const ids = { doc: useId(), file: useId() };
  const [document, setDocument] = useState<KycDocument>("gst");
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState<ConnectErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      className="mt-4 flex flex-col gap-4 rounded-lg bg-surface-2 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        startTransition(async () => {
          const res = await submitKyc(number.id, document, fileName);
          if (!res.ok) setError(res.error);
          else toast.success(t("kycSubmitted"));
        });
      }}
    >
      <div>
        <p className="font-medium">{t("kycTitle")}</p>
        <p className="text-sm leading-5 text-text-muted">{t("kycDesc")}</p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.doc}>{t("docLabel")}</Label>
        <select
          id={ids.doc}
          value={document}
          onChange={(e) => setDocument(e.target.value as KycDocument)}
          className="h-12 w-full rounded-lg border border-input bg-surface px-4 text-base shadow-xs focus-visible:border-ring md:text-[15px]"
        >
          {DOCUMENTS.map((d) => (
            <option key={d} value={d}>
              {t(`docs.${d}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.file}>{t("fileLabel")}</Label>
        <Input
          id={ids.file}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          required
          onChange={(e) => setFileName(e.target.files?.[0]?.name ?? "")}
          className="pt-2.5"
        />
        <p className="text-xs leading-4 text-text-muted">{t("kycPlaceholder")}</p>
      </div>
      <ErrorLine error={error} />
      <Button type="submit" variant="secondary" className="w-full sm:w-fit" disabled={pending || !fileName} aria-busy={pending}>
        <FileUp aria-hidden />
        {t("kycSubmit")}
      </Button>
    </form>
  );
}
