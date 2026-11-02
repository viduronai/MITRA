"use client";

import { Download, FileUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

const MAX_BYTES = 2_000_000;

/** Paste rows from a sheet, or pick a CSV file (read in the browser; only its text is sent). */
export function ListInput({
  value,
  onChange,
  onTooBig,
}: {
  value: string;
  onChange: (text: string) => void;
  onTooBig: () => void;
}) {
  const t = useTranslations("campaigns.list");
  const id = useId();
  const file = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{t("pasteLabel")}</Label>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={7}
        spellCheck={false}
        placeholder={t("pastePlaceholder")}
        className="focus-ring min-h-40 w-full rounded-lg border border-input bg-surface px-3 py-2.5 font-mono text-[13px] leading-5"
      />
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={file}
          type="file"
          accept=".csv,text/csv,text/plain,.tsv"
          className="sr-only"
          tabIndex={-1}
          onChange={async (e) => {
            const picked = e.target.files?.[0];
            e.target.value = "";
            if (!picked) return;
            if (picked.size > MAX_BYTES) return onTooBig();
            onChange(await picked.text());
          }}
        />
        <Button type="button" variant="secondary" size="sm" onClick={() => file.current?.click()}>
          <FileUp aria-hidden />
          {t("upload")}
        </Button>
        <Button asChild variant="ghost" size="sm">
          <a href="/campaigns/sample" download>
            <Download aria-hidden />
            {t("sample")}
          </a>
        </Button>
      </div>
      <p className="text-[13px] leading-5 text-text-muted">{t("hint")}</p>
    </div>
  );
}
