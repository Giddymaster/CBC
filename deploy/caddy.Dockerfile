# Builds the React app and bakes it into a Caddy image alongside the Caddyfile.
# Build context is the repository root.
FROM node:22-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv/site
COPY deploy/Caddyfile /etc/caddy/Caddyfile
