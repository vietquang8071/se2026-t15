FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core openssl \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable && corepack prepare pnpm@11.1.1 --activate
WORKDIR /workspace
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/api/package.json apps/api/package.json
COPY apps/web/package.json apps/web/package.json
COPY packages/database/package.json packages/database/package.json
COPY apps/audio apps/audio
RUN pnpm install --frozen-lockfile --filter @meeting-minutes/audio \
    && pnpm --filter @meeting-minutes/audio build \
    && mkdir -p /data/audio && chown -R node:node /data /workspace/apps/audio
WORKDIR /workspace/apps/audio
ENV AUDIO_HOST=0.0.0.0 AUDIO_PORT=3002 AUDIO_STORAGE_DIR=/data/audio
USER node
EXPOSE 3002
CMD ["sh", "-c", "pnpm db:deploy && node dist/main.js"]
