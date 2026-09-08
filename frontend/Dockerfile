# ── Stage 1: build ───────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (cached layer)
COPY package*.json ./
RUN npm ci --silent

# Build production bundle
COPY . .
RUN npm run build

# ── Stage 2: serve via nginx ──────────────────────────────────────
FROM nginx:1.27-alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy Vite build output
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config is provided by the main nginx service via volume mount;
# this image only needs to serve static files.
# (The main nginx container mounts its own nginx.conf)

EXPOSE 80
