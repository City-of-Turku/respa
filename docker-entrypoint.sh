#!/bin/bash

set -e

# Enable SSH and give it access to app setting env variables
if [[ "$ENABLE_SSH" = "true" ]]; then
    service ssh start
    eval $(printenv | sed -n "/^PWD=/!s/^\([^=]\+\)=\(.*\)$/export \1=\2/p" | sed 's/"/\\\"/g' | sed '/=/s//="/' | sed 's/$/"/' >> /etc/profile)
fi

function _log(){
  echo $(date "+%F_%T %Z"): $@
}

if [ -n "$DATABASE_HOST" ]; then
  until nc -z -v -w30 "$DATABASE_HOST" 5432
  do
    _log "Waiting for postgres database connection..."
    sleep 1
  done
  _log "Database is up!"
fi

# Only load and start cron if crontab file exists (e.g. in full production image)
if [ -f /root/crontab ] && command -v crontab >/dev/null 2>&1; then
  _log "Loading crontab and starting cron..."
  crontab /root/crontab
  service cron start
else
  _log "Skipping cron (no /root/crontab or crontab not installed)."
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
  uwsgi --ini deploy/uwsgi.ini --check-static /fileshare
fi

_log "Respa entrypoint completed..."