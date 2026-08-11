FROM node:20-alpine as base
WORKDIR /app

FROM base as deps
COPY package*.json ./
RUN npm ci

FROM base as builder
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM base as runner
ENV NODE_ENV=production
WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["npm", "start"]