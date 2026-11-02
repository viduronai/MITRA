import type { Metadata } from "next";
import { HomePage } from "@/components/HomePage";
import { content } from "@/content";
import { pageMetadata } from "@/lib/seo";

const t = content.en;

export const metadata: Metadata = pageMetadata({
  title: t.meta.title,
  description: t.meta.description,
  path: "/",
  locale: "en",
  localised: "/",
  absolute: true,
});

export default function Page() {
  return <HomePage locale="en" />;
}
