# Use the official Bun image (Alpine version for smaller size)
FROM oven/bun:1.1-alpine AS base
WORKDIR /app

# 1. Install dependencies only when package.json or bun.lockb changes
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile

# 2. Copy the rest of the source code
COPY . .

# 3. Build the Next.js application
# Bun can run the 'next build' command directly
RUN bun run build

# 4. Production Environment
FROM oven/bun:1.1-alpine AS release
WORKDIR /app

# Copy only the necessary build artifacts from the base stage
COPY --from=base /app/.next ./.next
COPY --from=base /app/public ./public
COPY --from=base /app/package.json ./package.json
COPY --from=base /app/node_modules ./node_modules

EXPOSE 3000

# Use Bun to start the production server
CMD ["bun", "run", "start"]