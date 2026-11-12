export const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? process.env.URL ?? "http://localhost:3100";

/**
 * Core API base for browser calls (POST /v1/demo-calls). Empty means same
 * origin: deployed environments put the API behind the site's own domain.
 */
export const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
