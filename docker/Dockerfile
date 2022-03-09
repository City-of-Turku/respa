# Docker image for Respa
FROM node:14-alpine AS nodebase
FROM python:3.9-slim-bullseye AS pythonbase

FROM nodebase AS respa_admin_deps
WORKDIR /app
COPY respa_admin/package.json respa_admin/package-lock.json ./
RUN npm ci && npm cache clean --force

FROM nodebase AS respa_admin_builder
WORKDIR /app
COPY --from=respa_admin_deps app/node_modules /app/node_modules
COPY --from=respa_admin_deps /app/package.json /app/package-lock.json ./
COPY respa_admin/ .
RUN npm run-script build

FROM pythonbase AS respa_setup

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV STATIC_ROOT /var/www/static/
ENV MEDIA_ROOT /var/www/media/

RUN adduser --disabled-login --no-create-home --gecos '' respa
WORKDIR /srv/app
COPY --from=respa_admin_builder /app/static /srv/app/respa_admin/static
COPY . .
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential netcat gettext python-dev libpq-dev gdal-bin \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip --no-cache-dir \
    && pip install -r deploy/requirements.txt --no-cache-dir

RUN mkdir -p /srv/logs && chown respa:respa /srv/logs

RUN python manage.py compilemessages
RUN python manage.py collectstatic --no-input

ENTRYPOINT ["./docker-entrypoint.sh"]

FROM respa_setup AS development
ENV PRODUCTION=0
ENV DEBUG=True

FROM respa_setup AS production
ENV PRODUCTION=1
ENV DEBUG=False
USER respa
EXPOSE 8000/tcp