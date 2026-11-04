import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker images (deploy/) set NEXT_OUTPUT=standalone: a self-contained server.js with only
  // the node_modules it needs. Unset locally so `next start` behaves as before.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
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
