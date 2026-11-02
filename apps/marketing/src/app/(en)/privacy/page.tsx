import type { Metadata } from "next";
import { LegalPage } from "@/components/page/LegalPage";
import { privacy as t } from "@/content/pages/legal";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({ ...t.meta, path: "/privacy", noindex: true });

export default function Page() {
  return <LegalPage t={t} path="/privacy" />;
}
