# WorkPilot v2 — Nginx + Frontend
#
# Multi-stage build:
#   Stage 1 (builder) : npm ci + npm run build → Vite dist
#   Stage 2 (nginx)   : copies dist + nginx.conf → serves everything
#
# Build context must be the project root (v2/), so both
# ./frontend/ and ./nginx/ are accessible.

# ── Stage 1: Build React app ─────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /build

COPY frontend/package*.json ./
RUN npm ci --silent

COPY frontend/ .
RUN npm run build

# ── Stage 2: Nginx ───────────────────────────────────────────────
FROM nginx:1.27-alpine

# Remove default nginx placeholder
RUN rm -rf /usr/share/nginx/html/*

# Copy Vite dist output
COPY --from=builder /build/dist /usr/share/nginx/html

# nginx.conf is mounted as a volume in docker-compose.yml —
# we do NOT bake it into the image so it can be changed without rebuilding.

EXPOSE 80
