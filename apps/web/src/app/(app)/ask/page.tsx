import { CloudOff } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";
import { AskThread } from "@/components/manager/ask-thread";
import { EmptyState } from "@/components/mitra/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api";
import { managerApi } from "@/lib/manager/api";
import type { ThreadMessage } from "@/lib/manager/types";
import { requireSession } from "@/lib/session";

export async function generateMetadata() {
  const t = await getTranslations("ask");
  return { title: t("title") };
}

export default async function AskPage() {
  const [t, { token }] = await Promise.all([getTranslations("ask"), requireSession()]);
  let thread: ThreadMessage[] | null = null;
  try {
    thread = await managerApi.thread(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
  }
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {thread ? (
        <AskThread initial={thread} />
      ) : (
        <EmptyState icon={CloudOff} description={t("errors.unreachable")} />
      )}
    </>
  );
}
