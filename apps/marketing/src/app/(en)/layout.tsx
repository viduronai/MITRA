import type { Metadata, Viewport } from "next";
import { RootShell } from "@/components/RootShell";
import { content } from "@/content";
import { rootMetadata } from "@/lib/seo";

const t = content.en;

export const metadata: Metadata = rootMetadata("en", t.meta.title, t.meta.description);

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#01061A",
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <RootShell lang={t.htmlLang} skip={t.nav.skip}>
      {children}
    </RootShell>
  );
}
