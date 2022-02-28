FROM node:14-alpine AS respa_admin
WORKDIR /srv/app
COPY respa_admin/ .
RUN npm install
RUN npm run-script build




FROM python:3.8 as respa_setup

RUN adduser --disabled-login --no-create-home --gecos '' respa
WORKDIR /srv/app
COPY . .
COPY --from=respa_admin --chown=respa:respa /srv/app/node_modules respa_admin/node_modules/
COPY --from=respa_admin --chown=respa:respa /srv/app/package.json /srv/app/package-lock.json respa_admin/

RUN apt-get update
RUN apt-get install netcat gettext python-dev libpq-dev gdal-bin -y


RUN pip install --upgrade pip && pip install wheel uwsgi -r requirements.txt

ENTRYPOINT ["./docker-entrypoint.sh"]

RUN python manage.py compilemessages

FROM respa_setup as development
ENV PRODUCTION=0
ENV STATIC_ROOT /var/www/static/
ENV MEDIA_ROOT /var/www/media/
COPY --chown=respa:respa . .
RUN python manage.py collectstatic --no-input

FROM respa_setup as production
ENV PRODUCTION=1
ENV STATIC_ROOT /var/www/static/
ENV MEDIA_ROOT /var/www/media/
COPY --chown=respa:respa . .
RUN python manage.py collectstatic --no-input
USER respa
EXPOSE 8000/tcp