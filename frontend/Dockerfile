FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

# Prepare the unprivileged runtime. The image already runs nginx as uid 101 and
# owns /etc/nginx (group-writable), so template rendering into /etc/nginx/conf.d
# and reading the mounted Basic Auth file both work without root at runtime.
USER root
RUN mkdir -p /etc/nginx/auth \
    && chown -R 101:0 /etc/nginx/auth \
    && chmod -R 750 /etc/nginx/auth \
    && rm -f /etc/nginx/conf.d/default.conf

# The image ships envsubst and runs /docker-entrypoint.d/20-envsubst-on-templates.sh
# from its inherited entrypoint, rendering this template at start with only the
# defined environment variables substituted.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint-guard.sh /docker-entrypoint-guard.sh
RUN chmod 755 /docker-entrypoint-guard.sh
USER 101

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint-guard.sh"]
CMD ["nginx", "-g", "daemon off;"]
