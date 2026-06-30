# CRMWolf Frontend Dockerfile
# Multi-stage build: Node build -> Nginx serve

# Stage 1: Build
FROM node:20-alpine as builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (use legacy-peer-deps for compatibility)
RUN npm ci --legacy-peer-deps

# Copy source code
COPY . .

# Build argument for API URL (leave empty to use nginx proxy)
ARG API_URL=
ENV VITE_API_BASE_URL=${API_URL}

# Build the application (direct vite build, skip type check)
RUN npx vite build

# Stage 2: Production
FROM nginx:alpine as production

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]