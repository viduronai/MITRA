import type { Metadata, Viewport } from "next";
import { Geist_Mono, Host_Grotesk, Noto_Sans_Devanagari, Noto_Sans_Telugu } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";
import { AppProviders } from "@/components/providers/app-providers";
import { themeInitScript } from "@/components/theme/theme-script";
import "./globals.css";

// v2 fonts follow viduronai.in: Host Grotesk for text and display,
// Geist Mono for small uppercase labels.
const hostGrotesk = Host_Grotesk({
  variable: "--font-host-grotesk",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

// Indic fonts aren't preloaded: the browser fetches them only when a page
// actually contains Telugu or Devanagari text (unicode-range).
const notoTelugu = Noto_Sans_Telugu({
  variable: "--font-noto-telugu",
  subsets: ["telugu"],
  display: "swap",
  preload: false,
});

const notoDevanagari = Noto_Sans_Devanagari({
  variable: "--font-noto-devanagari",
  subsets: ["devanagari"],
  display: "swap",
  preload: false,
});

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    title: { default: t("title"), template: `%s · ${t("title")}` },
    description: t("description"),
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F4F3EF" },
    { media: "(prefers-color-scheme: dark)", color: "#05070D" },
  ],
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const locale = await getLocale();
  const fontVariables = [hostGrotesk, geistMono, notoTelugu, notoDevanagari]
    .map((font) => font.variable)
    .join(" ");

  return (
    // data-theme is set before paint by themeInitScript, hence the warning opt-out.
    <html lang={locale} className={`${fontVariables} antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-dvh">
        <NextIntlClientProvider>
          <AppProviders>{children}</AppProviders>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
