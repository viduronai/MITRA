"use client";

import { Languages } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { setLocale } from "@/i18n/actions";
import { localeLabels, locales } from "@/i18n/config";
import { cn } from "@/lib/utils";

/** EN / తెలుగు / हिंदी — stored in a cookie, so URLs never change. */
export function LanguageSwitcher({ className }: { className?: string }) {
  const t = useTranslations("language");
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function change(next: string) {
    if (next === locale) return;
    startTransition(async () => {
      await setLocale(next);
      router.refresh();
    });
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className={cn("h-11 gap-1.5 px-2.5 text-text-muted sm:px-3", className)}
          aria-label={t("change")}
          aria-busy={pending}
        >
          <Languages className="size-5" aria-hidden />
          {/* Phones get a one-glyph code so the header line keeps its room. */}
          <span className="text-sm font-medium sm:hidden" lang={locale}>
            {localeLabels[locale].abbr}
          </span>
          <span className="hidden text-sm font-medium sm:inline" lang={locale}>
            {localeLabels[locale].short}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={locale} onValueChange={change}>
          {locales.map((code) => (
            <DropdownMenuRadioItem key={code} value={code} lang={code}>
              {localeLabels[code].name}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
