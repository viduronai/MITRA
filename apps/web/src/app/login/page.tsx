import { getTranslations } from "next-intl/server";
import { LoginFlow } from "@/components/auth/login-flow";
import { MinimalHeader } from "@/components/shell/minimal-header";

export async function generateMetadata() {
  const t = await getTranslations("auth");
  return { title: t("title") };
}

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const [t, params] = await Promise.all([getTranslations("nav"), searchParams]);

  return (
    <div className="flex min-h-dvh flex-col">
      <MinimalHeader homeHref="/login" homeLabel={t("brand")} />
      <main id="main" className="flex flex-1 items-start justify-center px-4 py-10 md:items-center md:py-16">
        <div className="w-full max-w-md rounded-2xl border bg-card p-6 shadow-sm md:p-8">
          <LoginFlow signedOut={"expired" in params} />
        </div>
      </main>
    </div>
  );
}
