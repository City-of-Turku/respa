#!/bin/bash

set -e

function _log(){
  echo $(date "+%F_%T %Z"): $@
}

if [ -n "$DATABASE_HOST" ]; then
  until nc -z -v -w30 "$DATABASE_HOST" 5432
  do
    echo "Waiting for postgres database connection..."
    sleep 1
  done
  echo "Database is up!"
fi

_log "Running Respa entrypoint..."

if [ "$1" = "dev_server" ]; then
  _log "Starting dev server..."
  python ./manage.py runserver 0.0.0.0:8000

elif [ "$1" = "apply_migrations" ]; then
  _log "Applying database migrations..."
  python manage.py migrate

elif [ "$1" = "run_tests" ]; then
  _log "Running tests..."
  pytest --cov . --doctest-modules

elif [ "$1" = "e" ]; then
  shift
  _log "Executing $@"
  exec "$@"

else
  _log "Starting the uwsgi web server"
  uwsgi --ini deploy/uwsgi.ini --check-static /var/www
fi

_log "Respa entrypoint completed..."