import { copy } from "@/content";
import { ogSize, renderOgImage } from "@/lib/og";

export const alt = copy.meta.ogAlt;
export const size = ogSize;
export const contentType = "image/png";

export default function OpengraphImage() {
  return renderOgImage();
}
