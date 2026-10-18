import type { Metadata, Viewport } from "next";
import {
  Doto,
  Geist_Mono,
  Host_Grotesk,
  Instrument_Serif,
  Noto_Sans_Devanagari,
  Noto_Sans_Telugu,
} from "next/font/google";
import { SmoothScroll } from "@/components/SmoothScroll";
import { copy } from "@/content";
import "./globals.css";

// Fonts follow viduronai.in (landing-direction §1.1). Only the hero faces are
// preloaded; the rest load when a glyph on the page needs them.
const host = Host_Grotesk({
  variable: "--font-host",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const instrument = Instrument_Serif({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: "400",
  style: "italic",
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  preload: false,
});

const doto = Doto({
  variable: "--font-doto",
  subsets: ["latin", "latin-ext"],
  weight: "700",
  display: "swap",
  preload: false,
});

const notoTelugu = Noto_Sans_Telugu({
  variable: "--font-noto-telugu",
  subsets: ["telugu"],
  weight: "500",
  display: "swap",
  preload: false,
});

const notoDevanagari = Noto_Sans_Devanagari({
  variable: "--font-noto-devanagari",
  subsets: ["devanagari"],
  weight: "500",
  display: "swap",
  preload: false,
});

// TODO(launch): set NEXT_PUBLIC_SITE_URL to the production domain.
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3100";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: copy.meta.title,
  description: copy.meta.description,
  applicationName: "Mitra",
  openGraph: {
    type: "website",
    siteName: "Mitra",
    title: copy.meta.title,
    description: copy.meta.description,
    locale: "en_IN",
    url: "/",
  },
  twitter: {
    card: "summary_large_image",
    title: copy.meta.title,
    description: copy.meta.description,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#01061A",
};

// Runs before first paint: marks JS as available and arms the hero entrance
// (Vexel). If the entrance has not started within 3.5s the class is removed so
// the hero can never stay hidden.
const bootScript = `(function(){var d=document.documentElement;d.classList.add('js');try{if(!matchMedia('(prefers-reduced-motion: reduce)').matches&&typeof d.animate==='function'){d.classList.add('intro');setTimeout(function(){if(!d.getAttribute('data-intro'))d.classList.remove('intro')},3500)}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const fonts = [host, instrument, geistMono, doto, notoTelugu, notoDevanagari].map((f) => f.variable).join(" ");
  return (
    <html lang="en-IN" className={fonts} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: bootScript }} />
        <link rel="preconnect" href="https://d8j0ntlcm91z4.cloudfront.net" crossOrigin="anonymous" />
      </head>
      <body>
        <a className="skip-link" href="#main">
          {copy.nav.skip}
        </a>
        {children}
        <SmoothScroll />
      </body>
    </html>
  );
}
