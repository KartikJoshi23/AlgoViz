# AlgoViz Frontend - Docker Configuration
# Build: multi-stage for production, dev server via volume mount

FROM node:20-slim AS base

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source
COPY . .

EXPOSE 3000

# Development mode with hot-reload
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
