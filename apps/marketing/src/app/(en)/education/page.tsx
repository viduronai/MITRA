import type { Metadata } from "next";
import { IndustryPage } from "@/components/page/IndustryPage";
import { industryPages } from "@/content/pages/industries";
import { pageMetadata } from "@/lib/seo";

const t = industryPages["education"];

export const metadata: Metadata = pageMetadata({ title: t.meta.title, description: t.meta.description, path: "/education" });

export default function Page() {
  return <IndustryPage slug="education" />;
}
