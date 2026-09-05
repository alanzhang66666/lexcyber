FROM node:22.16.0-alpine AS build
WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmjs.org
COPY package*.json ./
RUN npm config set registry "$NPM_REGISTRY" && npm ci
COPY . .
RUN npm run build

FROM nginx:1.27.2-alpine
COPY --from=build /app/dist /usr/share/nginx/html
