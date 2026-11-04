import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Docker images (deploy/) set NEXT_OUTPUT=standalone: a self-contained server.js with only
  // the node_modules it needs. Unset locally so `next start` behaves as before.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // Cache Components is off: the locale cookie is read in the root layout
  // (for <html lang>), and every app screen is per-business dynamic data.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default withNextIntl(nextConfig);
