"use client";

import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { setChannels } from "@/app/(app)/campaigns/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Calls at the same time (CALL-09): more channels finish a list faster. */
export function ChannelsForm({ channels, canManage }: { channels: number; canManage: boolean }) {
  const t = useTranslations("campaigns.channels");
  const tErr = useTranslations("campaigns.errors");
  const id = useId();
  const [value, setValue] = useState(channels);
  const [pending, startTransition] = useTransition();
  return (
    <form
      className="flex flex-col gap-2 rounded-xl border bg-card p-4 shadow-xs sm:flex-row sm:items-end sm:justify-between md:p-5"
      onSubmit={(e) => {
        e.preventDefault();
        startTransition(async () => {
          const res = await setChannels(value);
          if (res.ok) toast.success(t("saved", { count: res.data.channels }));
          else toast.error(tErr(res.error));
        });
      }}
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor={id}>{t("label")}</Label>
        <p className="text-[13px] leading-5 text-text-muted">{t("hint")}</p>
      </div>
      <div className="flex gap-2">
        <Input
          id={id}
          type="number"
          min={1}
          max={50}
          value={value}
          disabled={!canManage}
          onChange={(e) => setValue(Math.min(50, Math.max(1, Number(e.target.value) || 1)))}
          className="w-24"
        />
        {canManage && (
          <Button type="submit" variant="secondary" disabled={pending || value === channels}>
            {t("save")}
          </Button>
        )}
      </div>
    </form>
  );
}
