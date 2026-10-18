"use client";

import { RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

/** Friendly fallback when a step can't load (e.g. the service is down). */
export default function OnboardingError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations("onboarding");

  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center">
      <p className="text-[17px] leading-[26px] text-text-muted">{t("errors.unreachable")}</p>
      <Button className="mt-6" variant="secondary" onClick={reset}>
        <RotateCcw aria-hidden />
        {t("tryAgain")}
      </Button>
    </div>
  );
}
