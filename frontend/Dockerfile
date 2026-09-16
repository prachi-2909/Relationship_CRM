# Multi-stage build: compile the Vite app, then serve the static bundle with
# nginx, proxying /api to the backend service so the SPA's relative
# fetch("/api/v1/...") calls keep working exactly as they do in dev.
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O - http://localhost/ >/dev/null || exit 1
