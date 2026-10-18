import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

/**
 * Back + the step's one primary action. Sticks to the bottom on phones so the
 * main button stays under the thumb.
 */
export function StepFooter({ backHref, children }: { backHref?: string; children: React.ReactNode }) {
  const t = useTranslations("onboarding");

  return (
    <div data-step-footer className="sticky bottom-0 z-20 -mx-4 mt-8 border-t bg-bg/95 px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))] backdrop-blur-md md:static md:mx-0 md:mt-10 md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none">
      <div className="flex flex-col-reverse gap-2 md:flex-row md:items-center md:justify-between">
        {backHref ? (
          <Button asChild variant="ghost" className="text-text-muted md:-ml-3">
            <Link href={backHref}>
              <ArrowLeft aria-hidden />
              {t("back")}
            </Link>
          </Button>
        ) : (
          <span className="hidden md:block" />
        )}
        <div className="flex flex-col gap-2 md:flex-row md:items-center">{children}</div>
      </div>
    </div>
  );
}
