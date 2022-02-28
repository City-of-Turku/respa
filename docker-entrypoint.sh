#!/bin/bash

set -e

if [ -n "$DATABASE_HOST" ]; then
  until nc -z -v -w30 "$DATABASE_HOST" 5432
  do
    echo "Waiting for postgres database connection..."
    sleep 1
  done
  echo "Database is up!"
fi

python manage.py migrate

if [[ ! -z "$@" ]]; then
    "$@"
elif [[ "$PRODUCTION" = "1" ]]; then
    uwsgi --http :8000 --wsgi-file deploy/wsgi.py --check-static /srv/www
else
    python ./manage.py runserver 0.0.0.0:8000
fi