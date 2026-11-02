import type { Metadata } from "next";
import { PricingPage } from "@/components/pricing/PricingPage";
import { pricingContent } from "@/content/pricing";
import { pageMetadata } from "@/lib/seo";

const t = pricingContent.te;

export const metadata: Metadata = pageMetadata({
  title: t.meta.title,
  description: t.meta.description,
  path: "/te/pricing",
  locale: "te",
  localised: "/pricing",
});

export default function Page() {
  return <PricingPage locale="te" />;
}
