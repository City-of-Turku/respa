# Docker image for Respa
FROM node:18-alpine AS nodebase
FROM python:3.9-slim-bullseye AS pythonbase

FROM nodebase AS respa_admin_deps
WORKDIR /srv/app
#WORKDIR /app #Test env?
COPY respa_admin/package.json respa_admin/package-lock.json ./
RUN npm ci && npm cache clean --force

FROM nodebase AS respa_admin_builder
WORKDIR /srv/app
#WORKDIR /app #Test env?
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
# 30 0 * * * docker exec -u 0 $(docker ps -aqf "name=app-api-1") python manage.py post_daily_utilization --date $(date --date yesterday "+\%Y-\%m-\%d")
# RUN echo '30 0 * * * respa python /srv/app/manage.py sftp_daily_utilization tuotanto/laatutyokalut/Varaamo_$(date --date yesterday "+%Y-%m-%d").csv --date $(date --date yesterday "+%Y-%m-%d")' >> /etc/crontab

#Test environment
# RUN echo '30 0 * * * respa python /srv/app/manage.py sftp_daily_utilization testi/laatutyokalut/Varaamo_$(date --date yesterday "+%Y-%m-%d").csv --date $(date --date yesterday "+%Y-%m-%d")' >> /etc/crontab
#Prod environment
RUN echo '30 0 * * * respa python /srv/app/manage.py sftp_daily_utilization tuotanto/laatutyokalut/Varaamo_$(date --date yesterday "+\%Y-\%m-\%d").csv --date $(date --date yesterday "+\%Y-\%m-\%d")' >> /etc/crontab
# RUN echo "30 0 * * * respa python manage.py sftp_daily_utilization tuotanto/laatutyokalut/Varaamo_$(date --date yesterday "+\%Y-\%m-\%d").csv --date yesterday "+\%Y-\%m-\%d") > /tmp/cron1.txt"

# Expire unpaid orders, and release the time slots for future reservations once every 6 minutes.
RUN echo "*/6 * * * * respa python /srv/app/manage.py expire_too_old_unpaid_orders" >> /etc/crontab

# Check for SMS reminders once every 5 minutes.
RUN echo "*/5 * * * * respa python /srv/app/manage.py handle_reminders" >> /etc/crontab

# Sync Abloy pin-codes once every 4 minutes.
RUN echo "*/4 * * * * respa python /srv/app/manage.py sync_kulkunen" >> /etc/crontab

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