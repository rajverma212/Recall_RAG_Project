# Build context is the repo root (see docker-compose.yml) so we can COPY both
# the frontend source and docker/nginx.conf.

# ----- build -----
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# ----- serve -----
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
