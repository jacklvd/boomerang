# syntax=docker/dockerfile:1
FROM oven/bun:1 AS deps
WORKDIR /app
COPY package.json bun.lock ./
# --ignore-scripts: husky's prepare hook has no .git inside the image.
RUN bun install --frozen-lockfile --ignore-scripts

FROM oven/bun:1 AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN bun run build

# Runtime: only the standalone output. Node, not Bun — Next targets Node.
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
