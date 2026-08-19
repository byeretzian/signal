FROM node:22-alpine
WORKDIR /app
COPY package.json ./
COPY package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --fetch-retries=5 --fetch-retry-maxtimeout=120000
COPY apps/web ./apps/web
WORKDIR /app/apps/web
EXPOSE 3000
CMD ["npm", "run", "dev"]
