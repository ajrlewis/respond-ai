# Use a Bun version compatible with the Vitest setup in this repo.
FROM oven/bun:1.2.23-alpine AS base
WORKDIR /app

# API proxy target used by next.config rewrites during build.
ARG API_BASE_URL=http://localhost:8000
ENV API_BASE_URL=${API_BASE_URL}

# 1. Install dependencies only when package.json or bun.lockb changes
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile

# 2. Copy the rest of the source code
COPY . .

# 3. Build the Next.js application
# Bun can run the 'next build' command directly
RUN bun run build

# 4. Production Environment
FROM oven/bun:1.2.23-alpine AS release
WORKDIR /app

# Copy the built app plus source/tests so `docker compose run --rm web bun run test`
# can execute in this image as well.
COPY --from=base /app /app

EXPOSE 3000

# Use Bun to start the production server
CMD ["bun", "run", "start"]
