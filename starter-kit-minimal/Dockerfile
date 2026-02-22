ARG SOURCE_DATE_EPOCH=0

FROM node:22-slim@sha256:773413f36941ce1e4baf74b4a6110c03dcc4f968daffc389d4caef3f01412d2a

ARG SOURCE_DATE_EPOCH
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV npm_config_cache=/tmp/npm-cache

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci --omit=dev --ignore-scripts && \
    rm -rf /tmp/npm-cache /tmp/node-compile-cache && \
    find /app -exec touch -d "@${SOURCE_DATE_EPOCH}" {} + 2>/dev/null || true

COPY app.js ./
RUN touch -d "@${SOURCE_DATE_EPOCH}" /app/app.js

CMD ["node", "app.js"]
