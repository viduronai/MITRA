import type { Metadata } from "next";
import { IndustryPage } from "@/components/page/IndustryPage";
import { industryPages } from "@/content/pages/industries";
import { pageMetadata } from "@/lib/seo";

const t = industryPages["clinics"];

export const metadata: Metadata = pageMetadata({ title: t.meta.title, description: t.meta.description, path: "/clinics" });

export default function Page() {
  return <IndustryPage slug="clinics" />;
}
