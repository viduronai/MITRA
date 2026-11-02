import {
  Doto,
  Geist_Mono,
  Host_Grotesk,
  Instrument_Serif,
  Noto_Sans_Devanagari,
  Noto_Sans_Telugu,
} from "next/font/google";

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
  weight: ["400", "500"],
  display: "swap",
  preload: false,
});

const notoDevanagari = Noto_Sans_Devanagari({
  variable: "--font-noto-devanagari",
  subsets: ["devanagari"],
  weight: ["400", "500"],
  display: "swap",
  preload: false,
});

export const fontVariables = [host, instrument, geistMono, doto, notoTelugu, notoDevanagari]
  .map((f) => f.variable)
  .join(" ");
