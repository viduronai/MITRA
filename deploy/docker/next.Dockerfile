# Owner app (APP=web) or marketing site (APP=marketing). Build from the repo root:
#   docker build -f deploy/docker/next.Dockerfile --build-arg APP=web -t mitra-web .
# NEXT_PUBLIC_* values are baked in at build time, so each environment builds its own image.
ARG NODE=node:24-bookworm-slim

FROM ${NODE} AS build
ARG APP
ARG NEXT_PUBLIC_SITE_URL=""
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=standalone \
    NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL} NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
WORKDIR /repo
COPY package.json package-lock.json ./
# Every workspace manifest, so npm ci finds all the lockfile's workspaces; only APP's
# dependencies are installed.
COPY apps/web/package.json apps/web/
COPY apps/marketing/package.json apps/marketing/
RUN npm ci --workspace apps/${APP} --include-workspace-root=false
COPY apps/${APP} apps/${APP}
RUN npm run build --workspace apps/${APP}

FROM ${NODE}
ARG APP
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /srv
# Standalone output keeps the monorepo layout: server.js sits under apps/<app>/.
COPY --from=build --chown=node:node /repo/apps/${APP}/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/${APP}/.next/static ./apps/${APP}/.next/static
COPY --from=build --chown=node:node /repo/apps/${APP}/public ./apps/${APP}/public
RUN ln -s /srv/apps/${APP}/server.js /srv/server.js
USER node
EXPOSE 3000
CMD ["node", "/srv/server.js"]
