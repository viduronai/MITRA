import { ImageResponse } from "next/og";
import { copy } from "@/content";

export const alt = copy.meta.ogAlt;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Night-sky card with the hero line and the mitra mark. Uses the built-in
// font so the image renders without fetching anything at build time.
export default function OpengraphImage() {
  const bars = [16, 30, 52, 30, 16];
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "72px 80px",
        background: "linear-gradient(180deg, #01061a 0%, #021034 62%, #0b3b7a 100%)",
        color: "#ffffff",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div
          style={{
            width: 64,
            height: 64,
            borderRadius: 16,
            background: "#05070d",
            border: "1px solid rgba(56,198,244,.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 5,
          }}
        >
          {bars.map((h, i) => (
            <div key={i} style={{ width: 5, height: h * 0.8, borderRadius: 3, background: "#38c6f4" }} />
          ))}
        </div>
        <div style={{ fontSize: 40, letterSpacing: -1.5 }}>mitra</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", fontSize: 84, letterSpacing: -3, lineHeight: 1 }}>
        <div>{copy.hero.line1}</div>
        <div style={{ color: "#9fe3fa" }}>Mitra says hello.</div>
      </div>
      <div style={{ fontSize: 28, color: "rgba(226,233,255,.74)" }}>
        AI employees for Indian businesses · Telugu · Hindi · English
      </div>
    </div>,
    size,
  );
}
