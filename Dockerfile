# Docker image for Respa
FROM node:20-alpine AS nodebase
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
# ENV STATIC_ROOT /var/www/static/
# ENV MEDIA_ROOT /var/www/media/

RUN adduser --disabled-login --no-create-home --gecos '' respa
WORKDIR /srv/app
COPY --from=respa_admin_builder /app/static /srv/app/respa_admin/static
COPY . .
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential netcat gettext python-dev libpq-dev gdal-bin dialog openssh-server cron \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip --no-cache-dir \
    && pip install -r deploy/requirements.txt --no-cache-dir

RUN mkdir -p /srv/logs && chown respa:respa /srv/logs

RUN python manage.py compilemessages
RUN python manage.py collectstatic --no-input

# Enable SSH
RUN echo "root:Docker!" | chpasswd
COPY sshd_config /etc/ssh/

# Add cron tasks


# Send daily qualitytool stats
RUN echo '30 0 * * * su -s /bin/bash -c "source /etc/profile; /srv/app/manage.py sftp_daily_utilization tuotanto/laatutyokalut/Varaamo_$(date --date=yesterday "+\%Y-\%m-\%d").csv --date $(date --date=yesterday "+\%Y-\%m-\%d")" respa >> /proc/1/fd/1 2>&1' >> /root/crontab

# Expire unpaid orders every 6 minutes
RUN echo '*/6 * * * * su -s /bin/bash -c "source /etc/profile; /srv/app/manage.py expire_too_old_unpaid_orders" respa >> /proc/1/fd/1 2>&1' >> /root/crontab

# Check for SMS reminders every 5 minutes
RUN echo '*/5 * * * * su -s /bin/bash -c "source /etc/profile; /srv/app/manage.py handle_reminders" respa >> /proc/1/fd/1 2>&1' >> /root/crontab

# Sync Abloy pin-codes every 4 minutes
RUN echo '*/4 * * * * su -s /bin/bash -c "source /etc/profile; /srv/app/manage.py sync_kulkunen" respa >> /proc/1/fd/1 2>&1' >> /root/crontab

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the command on container startup
# CMD cron && tail -f /var/log/cron.log

RUN chmod u+x ./docker-entrypoint.sh
RUN chmod uo+x ./manage.py

RUN printenv > /etc/environment

ENTRYPOINT ["./docker-entrypoint.sh"]

FROM respa_setup AS development
ENV PRODUCTION=0
ENV DEBUG=True

FROM respa_setup AS production
ENV PRODUCTION=1
ENV DEBUG=False
EXPOSE 8000/tcp
