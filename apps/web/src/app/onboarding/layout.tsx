import { LogOut } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { MinimalHeader } from "@/components/shell/minimal-header";
import { Button } from "@/components/ui/button";
import { signOut } from "./actions";

export async function generateMetadata() {
  const t = await getTranslations("onboarding");
  return { title: t("metaTitle") };
}

export default async function OnboardingLayout({ children }: LayoutProps<"/onboarding">) {
  const [t, tNav] = await Promise.all([getTranslations("onboarding"), getTranslations("nav")]);

  return (
    <div className="flex min-h-dvh flex-col">
      <MinimalHeader homeHref="/" homeLabel={tNav("brand")}>
        <form action={signOut}>
          <Button type="submit" variant="ghost" size="icon" className="text-text-muted" aria-label={t("signOut")}>
            <LogOut aria-hidden />
          </Button>
        </form>
      </MinimalHeader>
      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 pt-6 pb-10 md:px-8 md:pt-10 md:pb-16">
        {children}
      </main>
    </div>
  );
}
