import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Netlify sets NEXT_OUTPUT=export for a static frontend; Docker sets it to
  // standalone for a self-contained server. Unset locally for `next start`.
  output:
    process.env.NEXT_OUTPUT === "export"
      ? "export"
      : process.env.NEXT_OUTPUT === "standalone"
        ? "standalone"
        : undefined,
  // The landing page is mostly first-time visitors: inline the CSS so the
  // first paint needs no extra round trip.
  experimental: {
    inlineCss: true,
    // Three root layouts (en / te / hi, each with its own <html lang>), so
    // unmatched URLs need app/global-not-found.tsx.
    globalNotFound: true,
  },
  turbopack: {
    rules: {
      // Tailwind only processes the global sheet; scene CSS modules stay
      // plain CSS modules (their :global() selectors need the module parser).
      "*.css": {
        condition: { path: /src\/app\/globals\.css$/ },
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
