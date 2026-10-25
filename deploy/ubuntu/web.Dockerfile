FROM node:22-bookworm-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-bookworm
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80 443
