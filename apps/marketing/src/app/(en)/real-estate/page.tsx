import type { Metadata } from "next";
import { IndustryPage } from "@/components/page/IndustryPage";
import { industryPages } from "@/content/pages/industries";
import { pageMetadata } from "@/lib/seo";

const t = industryPages["real-estate"];

export const metadata: Metadata = pageMetadata({ title: t.meta.title, description: t.meta.description, path: "/real-estate" });

export default function Page() {
  return <IndustryPage slug="real-estate" />;
}
